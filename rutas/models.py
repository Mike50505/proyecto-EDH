from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Client(models.Model):
    name = models.CharField(max_length=160, unique=True)

    def __str__(self):
        return self.name


class SourceBook(models.Model):
    filename = models.CharField(max_length=255)
    sha256 = models.CharField(max_length=64, unique=True)
    classification = models.CharField(max_length=32)
    imported_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.filename


class ImportRun(models.Model):
    source = models.ForeignKey(SourceBook, null=True, blank=True, on_delete=models.PROTECT)
    filename = models.CharField(max_length=255)
    sha256 = models.CharField(max_length=64)
    dry_run = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    summary = models.JSONField(default=dict)


class ImportIssue(models.Model):
    run = models.ForeignKey(ImportRun, on_delete=models.CASCADE, related_name="issues")
    sheet = models.CharField(max_length=80)
    row = models.PositiveIntegerField()
    code = models.CharField(max_length=160, blank=True)
    kind = models.CharField(max_length=64)
    detail = models.TextField()
    resolved = models.BooleanField(default=False)
    resolution_note = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)


class Part(models.Model):
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    code = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    part_type = models.CharField(max_length=16, blank=True)
    bom_revision = models.CharField(max_length=80, blank=True)
    drawing_revision = models.CharField(max_length=80, blank=True)
    drawing_number = models.CharField(max_length=160, blank=True)
    od_raw = models.CharField(max_length=80, blank=True)
    wall_raw = models.CharField(max_length=80, blank=True)
    development_raw = models.CharField(max_length=80, blank=True)
    development_formula = models.CharField(max_length=160, blank=True)
    comments = models.TextField(blank=True)
    phase = models.CharField(max_length=80, blank=True)
    source = models.ForeignKey(SourceBook, null=True, on_delete=models.PROTECT)
    source_row = models.PositiveIntegerField(null=True, blank=True)
    source_values = models.JSONField(default=dict)
    needs_review = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=["client", "code"])]
        constraints = [models.UniqueConstraint(fields=["source", "source_row"], name="unique_part_origin")]

    def __str__(self):
        return self.code


class BOMItem(models.Model):
    parent = models.ForeignKey(Part, on_delete=models.CASCADE, related_name="components")
    component = models.ForeignKey(Part, on_delete=models.PROTECT, related_name="used_in")
    quantity_per = models.DecimalField(max_digits=14, decimal_places=4, validators=[MinValueValidator(0)])
    position = models.PositiveIntegerField()
    source_raw_quantity = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ["position", "id"]
        constraints = [models.UniqueConstraint(fields=["parent", "position"], name="unique_bom_position")]


class Route(models.Model):
    REVIEW = "review"
    ACTIVE = "active"
    ARCHIVED = "archived"
    STATUS = [(REVIEW, "Por revisar"), (ACTIVE, "Activa"), (ARCHIVED, "Archivada")]
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    part = models.ForeignKey(Part, null=True, blank=True, on_delete=models.PROTECT)
    code = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    classification = models.CharField(max_length=32, blank=True)
    revision = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=16, choices=STATUS, default=REVIEW)
    version = models.PositiveIntegerField(default=1)
    source = models.ForeignKey(SourceBook, null=True, blank=True, on_delete=models.PROTECT)
    source_sheet = models.CharField(max_length=80, blank=True)
    source_row = models.PositiveIntegerField(null=True, blank=True)
    source_code = models.CharField(max_length=160, blank=True)
    source_values = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["client", "code"]), models.Index(fields=["status", "code"])]
        constraints = [models.UniqueConstraint(fields=["source", "source_sheet", "source_row"], name="unique_route_origin")]

    def __str__(self):
        return f"{self.code} · {self.classification}"


class Operation(models.Model):
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="operations")
    position = models.PositiveIntegerField()
    source_sequence = models.CharField(max_length=40, blank=True)
    name = models.CharField(max_length=160)
    tooling = models.TextField(blank=True)
    inspection = models.TextField(blank=True)
    machine = models.TextField(blank=True)
    source_group = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["position", "id"]
        constraints = [models.UniqueConstraint(fields=["route", "position"], name="unique_operation_position")]


class RouteChange(models.Model):
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="history")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    changed_at = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=32)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)


class Schedule(models.Model):
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    week = models.CharField(max_length=40)
    line = models.CharField(max_length=100, blank=True)
    planner = models.CharField(max_length=100, blank=True)
    responsible = models.CharField(max_length=100, blank=True)
    issue_date = models.DateField(default=timezone.localdate)
    ship_date = models.DateField(null=True, blank=True)
    copies = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(20)])
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)


class ScheduleLine(models.Model):
    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE, related_name="lines")
    route = models.ForeignKey(Route, on_delete=models.PROTECT)
    shop_order = models.CharField(max_length=100)
    quantity = models.DecimalField(max_digits=14, decimal_places=4, validators=[MinValueValidator(0.0001)])
    position = models.PositiveIntegerField()

    class Meta:
        ordering = ["position", "id"]


class IssuedDocument(models.Model):
    schedule = models.ForeignKey(Schedule, null=True, blank=True, on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(default=timezone.now)
    downloaded_at = models.DateTimeField(null=True, blank=True)
    template_key = models.CharField(max_length=80)
    snapshot = models.JSONField()
    pdf = models.FileField(upload_to="documents/%Y/%m")
    sha256 = models.CharField(max_length=64)

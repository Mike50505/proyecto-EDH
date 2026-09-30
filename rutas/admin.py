from django.contrib import admin
from rutas.models import BOMItem, Client, ImportIssue, ImportRun, IssuedDocument, Operation, Part, Route, RouteChange, Schedule, ScheduleLine, SourceBook


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ("code", "client", "classification", "revision", "status", "updated_at")
    list_filter = ("client", "classification", "status")
    search_fields = ("code", "description")
    readonly_fields = ("source", "source_sheet", "source_row", "source_code", "source_values", "version")


@admin.register(SourceBook)
class SourceBookAdmin(admin.ModelAdmin):
    list_display = ("filename", "client", "classification", "print_approved", "imported_at")
    list_filter = ("client", "classification", "print_approved")
    readonly_fields = ("filename", "client", "classification", "sha256", "imported_at")


@admin.register(Part)
class PartAdmin(admin.ModelAdmin):
    list_display = ("code", "client", "part_type", "source", "source_row", "needs_review")
    search_fields = ("code", "description")
    list_filter = ("client", "part_type", "needs_review")


for model in (BOMItem, Client, ImportIssue, ImportRun, IssuedDocument, Operation, RouteChange, Schedule, ScheduleLine):
    admin.site.register(model)

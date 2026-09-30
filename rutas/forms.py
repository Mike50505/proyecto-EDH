from django import forms
from django.forms import inlineformset_factory
from django.forms.models import BaseInlineFormSet
from rutas.models import ImportIssue, Route, Operation, Part, Schedule, ScheduleLine
from rutas.services.source_catalog import CLIENT_VARIANTS, validate_source


class PartSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        part = getattr(value, "instance", None)
        if part is not None:
            option["attrs"]["data-client-id"] = str(part.client_id)
            option["attrs"]["data-part-code"] = part.code
        return option


class RouteForm(forms.ModelForm):
    version = forms.IntegerField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = Route
        fields = ["client", "part", "code", "description", "classification", "revision", "status"]
        labels = {"client": "Cliente", "part": "Pieza vinculada", "code": "Código", "description": "Descripción",
                  "classification": "Origen", "revision": "Revisión", "status": "Estado"}
        widgets = {"part": PartSelect(), "description": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["part"].queryset = Part.objects.select_related("source").order_by("client__name", "code", "source_row", "id")
        self.fields["part"].label_from_instance = lambda part: (
            f"{part.code} · {part.source.classification if part.source_id else 'Manual'}"
            f"{f' · fila {part.source_row}' if part.source_row else ''}"
        )
        if self.instance.pk:
            self.fields["version"].initial = self.instance.version

    def clean(self):
        data = super().clean()
        if data.get("part") and data.get("client") and data["part"].client_id != data["client"].pk:
            self.add_error("part", "La pieza debe pertenecer al cliente seleccionado.")
        if data.get("status") == Route.ACTIVE and self.instance.source_id and ImportIssue.objects.filter(
            run__source_id=self.instance.source_id, sheet="Ruta", row=self.instance.source_row, resolved=False
        ).exists():
            self.add_error("status", "Resuelva las incidencias de origen antes de activar esta ruta.")
        if data.get("status") == Route.ACTIVE and self.instance.source_id and not self.instance.source.print_approved:
            self.add_error("status", "Valide primero el formato de impresión de este libro de origen.")
        return data


class OrderedOperationFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        positions = [form.cleaned_data.get("position") for form in self.forms
                     if hasattr(form, "cleaned_data") and form.cleaned_data and not form.cleaned_data.get("DELETE")]
        positions = [p for p in positions if p is not None]
        if len(positions) != len(set(positions)):
            raise forms.ValidationError("Cada operación debe tener una posición diferente.")


OperationFormSet = inlineformset_factory(
    Route, Operation, fields=["position", "source_sequence", "name", "machine", "tooling", "inspection"],
    extra=1, max_num=200, validate_max=True, can_delete=True, formset=OrderedOperationFormSet,
    labels={"position": "Posición", "source_sequence": "Secuencia", "name": "Proceso", "machine": "Máquina",
            "tooling": "Herramental", "inspection": "Inspección"},
    widgets={"tooling": forms.TextInput(), "inspection": forms.TextInput(), "machine": forms.TextInput()}
)


class ScheduleForm(forms.ModelForm):
    class Meta:
        model = Schedule
        fields = ["client", "week", "line", "planner", "responsible", "issue_date", "ship_date", "copies"]
        labels = {"client": "CLIENTE", "week": "SEMANA", "line": "LINEA", "planner": "PLANNER",
                  "responsible": "RESPONSABLE", "issue_date": "FECHA DE EMISIÓN",
                  "ship_date": "FECHA DE EMBARQUE", "copies": "COPIAS DEL PDF"}
        widgets = {"issue_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
                   "ship_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}


class ScheduleLineForm(forms.ModelForm):
    re_count = forms.IntegerField(label="RE (calculado)", required=False, disabled=True,
                                  widget=forms.NumberInput(attrs={"readonly": True, "data-re-count": ""}))

    class Meta:
        model = ScheduleLine
        fields = ["shop_order", "route", "quantity", "re_count", "position"]
        labels = {"shop_order": "SHOP ORDER", "route": "ITEM PADRE / RUTA",
                  "quantity": "CANTIDAD", "position": "Secuencia"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        route_id = self.data.get(f"{self.prefix}-route") if self.is_bound else self.initial.get("route")
        if not route_id and self.instance.pk:
            route_id = self.instance.route_id
        if route_id and str(route_id).isdigit():
            route = Route.objects.filter(pk=route_id).select_related("part").first()
            if route and route.part_id:
                self.fields["re_count"].initial = route.part.components.filter(component__part_type="RM").count()
            else:
                self.fields["re_count"].initial = 0


ScheduleLineFormSet = inlineformset_factory(
    Schedule, ScheduleLine, form=ScheduleLineForm,
    fields=["shop_order", "route", "quantity", "re_count", "position"], extra=2, can_delete=True
)


class ImportForm(forms.Form):
    client_name = forms.ChoiceField(label="Cliente", choices=[(name, name) for name in CLIENT_VARIANTS],
                                    initial="DAIKIN", widget=forms.Select(attrs={"data-import-client": ""}))
    classification = forms.ChoiceField(label="Origen", choices=[(name, name) for name in
        ("Headers", "Individuales", "SLP Headers", "SLP Individuales", "General")],
        initial="Headers", widget=forms.Select(attrs={"data-import-variant": ""}))
    file = forms.FileField(label="Archivo XLSM")
    password = forms.CharField(label="Contraseña de apertura", required=False, widget=forms.PasswordInput(render_value=False))
    dry_run = forms.BooleanField(label="Solo simular", initial=True, required=False)

    def clean_file(self):
        file = self.cleaned_data["file"]
        if not file.name.lower().endswith(".xlsm"):
            raise forms.ValidationError("Seleccione un archivo .xlsm.")
        if file.size > 30 * 1024 * 1024:
            raise forms.ValidationError("El límite es 30 MB.")
        return file

    def clean(self):
        data = super().clean()
        if data.get("client_name") and data.get("classification"):
            try:
                validate_source(data["client_name"], data["classification"])
            except ValueError as exc:
                self.add_error("classification", str(exc))
        return data

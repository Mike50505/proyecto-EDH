from decimal import Decimal

from django import forms
from django.forms import BaseFormSet, formset_factory

from rutas.forms import preset_operation_formset
from rutas.models import BOMItem, Part, Route, RouteChange
from rutas.services.universo import normalize


class ComponentForm(forms.Form):
    route_version = forms.IntegerField(required=False, widget=forms.HiddenInput())
    code = forms.CharField(label="Número de componente", max_length=160)
    description = forms.CharField(label="Descripción", required=False)
    quantity_per = forms.DecimalField(label="Cantidad por padre", min_value=Decimal("0.0001"),
                                     max_digits=14, decimal_places=4, initial=1)
    od_raw = forms.CharField(label="Diámetro", max_length=80, required=False)
    wall_raw = forms.CharField(label="Pared", max_length=80, required=False)
    development_raw = forms.CharField(label="Desarrollo", max_length=80, required=False)


class ComponentSet(BaseFormSet):
    def clean(self):
        super().clean()
        expected = getattr(self, "expected_initial_count", 0)
        if self.initial_form_count() != expected or len(self.forms) < expected:
            raise forms.ValidationError("La lista de componentes cambió. Recarga la ruta antes de guardar.")
        if any(self.errors):
            return
        codes = [normalize(form.cleaned_data["code"]) for form in self.forms
                 if form.cleaned_data and not form.cleaned_data.get("DELETE")]
        if len(codes) != len(set(codes)):
            raise forms.ValidationError("No repitas el mismo número de componente dentro del padre.")


ComponentFormSet = formset_factory(ComponentForm, formset=ComponentSet, extra=0,
                                   can_delete=True, max_num=25, validate_max=True, absolute_max=50)


def fork_part(part):
    values = {field.attname: getattr(part, field.attname) for field in Part._meta.concrete_fields
              if not field.primary_key}
    values.update(source_id=None, source_row=None)
    return Part(**values)


def component_editor(data=None, parent=None):
    from rutas.services.documents import component_route_candidates
    existing = list(parent.part.components.filter(component__part_type="RM").select_related("component", "component_route")) if parent and parent.part_id else []
    child_routes = [bom.component_route or component_route_candidates(parent, bom).order_by("source_row", "id").first()
                    for bom in existing]
    submitted = data is not None and "components-TOTAL_FORMS" in data
    if data is not None and "components-TOTAL_FORMS" not in data:
        if parent:
            data = None  # Older editors can still update the parent without removing its BOM.
        else:
            data = data.copy()
            data.update({"components-TOTAL_FORMS": "0", "components-INITIAL_FORMS": "0"})
    initial = [{"code": bom.component.code, "description": bom.component.description,
                "quantity_per": bom.quantity_per, "od_raw": bom.component.od_raw,
                "wall_raw": bom.component.wall_raw, "development_raw": bom.component.development_raw,
                "route_version": child.version if child else None} for bom, child in zip(existing, child_routes)]
    components = ComponentFormSet(data, prefix="components", initial=initial)
    components.expected_initial_count = len(existing)
    components.max_num = max(25, len(existing))
    components.absolute_max = max(50, len(existing) + 25)
    rows = [{"form": form, "bom": existing[index] if index < len(existing) else None,
            "route": child_routes[index] if index < len(existing) else None,
            "operations": preset_operation_formset(data,
                instance=(child_routes[index] if index < len(existing) else None) or Route(),
                prefix=f"components-{index}-operations")} for index, form in enumerate(components)]
    empty = components.empty_form
    empty.prefix = "components-__component__"
    return {"components": components, "component_rows": rows, "components_submitted": submitted,
            "component_empty": {"form": empty,
                "operations": preset_operation_formset(instance=Route(), prefix="components-__component__-operations")}}


def validate_components(context, parent_code):
    valid = context["components"].is_valid()
    for row in context["component_rows"]:
        form, operations = row["form"], row["operations"]
        if form.cleaned_data.get("DELETE"):
            continue
        operations_valid = operations.is_valid()
        if form.is_valid() and form.cleaned_data:
            if normalize(form.cleaned_data["code"]) == normalize(parent_code):
                form.add_error("code", "El componente debe tener un número diferente al padre.")
            requires_operations = not row.get("bom") or (row.get("route") and row["route"].operations.exists())
            if requires_operations and operations_valid and not any(item.get("name") and not item.get("DELETE")
                                            for item in operations.cleaned_data):
                form.add_error(None, "Agrega al menos una operación para este componente.")
        valid = operations_valid and not form.errors and valid
    return valid


def lock_component_versions(context):
    ids = [row["route"].pk for row in context["component_rows"] if row.get("route")]
    locked = {route.pk: route for route in Route.objects.select_for_update().filter(pk__in=ids).order_by("pk")}
    valid = True
    for row in context["component_rows"]:
        if row.get("route") and not row["form"].cleaned_data.get("DELETE") and row["form"].cleaned_data.get("route_version") != locked[row["route"].pk].version:
            row["form"].add_error(None, "Otra persona modificó las operaciones de este componente. Recarga antes de guardar.")
            valid = False
    return valid


def save_components(context, parent, user, replace_operations):
    for row in context["component_rows"]:
        data = row["form"].cleaned_data
        existing = row.get("bom")
        bom = parent.part.components.filter(position=existing.position).first() if existing else None
        if data.get("DELETE") and bom:
            bom.delete()
        if not data or data.get("DELETE"):
            continue
        if bom and not row["form"].has_changed() and not row["operations"].has_changed():
            if not bom.component_route_id and row.get("route") and row["route"].part_id == bom.component_id:
                bom.component_route = row["route"]
                bom.save(update_fields=["component_route"])
            continue
        part = bom.component if bom else Part(client=parent.client, part_type="RM")
        child = row.get("route")
        # Shared/imported pieces and process routes stay available to other origins.
        fork = bool(child and (not existing.component_route_id or child.source_id or child.parent_bom_items.exclude(pk=existing.pk).exists()))
        if part.pk and (part.source_id or part.used_in.exclude(pk=bom.pk).exists() or fork):
            part = fork_part(part)
        for field in ("description", "od_raw", "wall_raw", "development_raw"):
            setattr(part, field, data[field])
        part.code = data["code"].strip()
        part.save()
        has_operations = any(item.get("name") and not item.get("DELETE") for item in row["operations"].cleaned_data)
        if has_operations or child:
            created = child is None or fork
            if created:
                child = Route(client=parent.client, classification=parent.classification,
                              revision=parent.revision, status=parent.status, universe_auto_link=False)
            else:
                child.version += 1
            child.part, child.code, child.description = part, part.code, part.description
            child.save()
            replace_operations(child, row["operations"])
            RouteChange.objects.create(route=child, user=user, action="create" if created else "edit",
                after={"code": child.code, "parent_route": parent.pk, "quantity_per": str(data["quantity_per"])})
        if bom:
            bom.component, bom.component_route, bom.quantity_per = part, child, data["quantity_per"]
            bom.save()
        else:
            position = max(parent.part.components.values_list("position", flat=True), default=0) + 1
            BOMItem.objects.create(parent=parent.part, component=part, component_route=child,
                quantity_per=data["quantity_per"], position=position)

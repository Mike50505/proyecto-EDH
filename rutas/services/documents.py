"""Immutable print snapshots and the compact two-label production reference."""
import base64
import hashlib
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.template.loader import render_to_string

from rutas.models import ImportIssue, IssuedDocument, Route

ROWS_PER_LABEL = 10  # fifteen writable rows remain on each physical label
WRITABLE_ROWS = 15
CLASSIC_TEMPLATE = "mesa-two-labels-v1"
MODERN_TEMPLATE = "mesa-modern-v1"
PRINT_TEMPLATES = (
    (CLASSIC_TEMPLATE, "Formato clásico"),
    (MODERN_TEMPLATE, "Formato moderno"),
)
TEMPLATE_FILES = {
    CLASSIC_TEMPLATE: "rutas/pdf.html",
    MODERN_TEMPLATE: "rutas/pdf_modern.html",
}


def validate_print_template(template_key):
    if template_key not in TEMPLATE_FILES:
        raise ValueError("Selecciona un diseño de impresión válido.")
    return template_key


def ensure_emittable(route):
    if route.status != Route.ACTIVE:
        raise ValueError(f"La ruta {route.code} requiere revisión antes de emitir.")
    if route.source_id and not route.source.print_approved:
        raise ValueError(f"El formato de impresión de {route.source.filename} sigue pendiente de validar.")
    if route.source_id and ImportIssue.objects.filter(
        run__source_id=route.source_id, sheet="Ruta", row=route.source_row, resolved=False
    ).exists():
        raise ValueError(f"La ruta {route.code} tiene incidencias sin resolver.")


def operation_data(route):
    return [{"position": op.position, "sequence": op.source_sequence, "name": op.name,
             "machine": op.machine, "tooling": op.tooling, "inspection": op.inspection}
            for op in route.operations.all()]


def snapshot_line(line):
    route = Route.objects.select_related("part", "source").prefetch_related("operations", "part__components__component").get(pk=line.route_id)
    ensure_emittable(route)
    part = route.part
    base = {"code": route.code, "description": route.description, "classification": route.classification,
            "revision": route.revision, "source": route.source.filename if route.source else "Captura web",
            "shop_order": line.shop_order, "quantity": str(line.quantity), "position": line.position,
            "operations": operation_data(route)}
    if part:
        base["dimensions"] = {"od": part.od_raw, "wall": part.wall_raw, "development": part.development_raw}
        base["components"] = [{"code": bom.component.code, "description": bom.component.description,
            "type": bom.component.part_type, "quantity_per": str(bom.quantity_per),
            "quantity_to_run": str(line.quantity * bom.quantity_per), "position": bom.position}
            for bom in part.components.all()]
    else:
        base["dimensions"] = {}
        base["components"] = []
    return base


def labels_for_line(line):
    """Etiqueta1: one label per RM, with parent occupying position 1 in N DE M."""
    parent = Route.objects.select_related("part", "source").prefetch_related("operations", "part__components__component").get(pk=line.route_id)
    ensure_emittable(parent)
    rm_items = [item for item in parent.part.components.all() if item.component.part_type == "RM"] if parent.part else []
    if not rm_items:
        part = parent.part
        return [make_label(parent, parent, part, line, line.quantity, 1, 1)]
    labels = []
    for index, bom in enumerate(rm_items, 2):
        candidates = Route.objects.filter(code=bom.component.code, client=parent.client, status=Route.ACTIVE)
        if parent.source_id:
            candidates = candidates.filter(source_id=parent.source_id)
        else:
            candidates = candidates.filter(classification=parent.classification)
        child_routes = list(candidates.prefetch_related("operations")[:2])
        if len(child_routes) != 1:
            raise ValueError(f"El componente {bom.component.code} necesita una ruta activa única en {parent.classification}.")
        child = child_routes[0]
        ensure_emittable(child)
        labels.append(make_label(parent, child, bom.component, line, line.quantity * bom.quantity_per, index, len(rm_items) + 1))
    return labels


def preview_labels_for_line(line):
    """Reproduce la primera coincidencia de la macro para una vista previa no aprobada."""
    parent = Route.objects.select_related("part", "source").prefetch_related(
        "operations", "part__components__component"
    ).get(pk=line.route_id)
    notes = []
    needs_review = parent.status != Route.ACTIVE or (parent.source_id and not parent.source.print_approved) or (
        parent.source_id and ImportIssue.objects.filter(
            run__source_id=parent.source_id, sheet="Ruta", row=parent.source_row, resolved=False
        ).exists()
    )
    rm_items = [item for item in parent.part.components.all() if item.component.part_type == "RM"] if parent.part else []
    if not rm_items:
        labels = [make_label(parent, parent, parent.part, line, line.quantity, 1, 1)]
    else:
        labels = []
        for index, bom in enumerate(rm_items, 2):
            candidates = Route.objects.filter(code=bom.component.code, client=parent.client).exclude(
                status=Route.ARCHIVED
            )
            if parent.source_id:
                candidates = candidates.filter(source_id=parent.source_id)
            else:
                candidates = candidates.filter(classification=parent.classification)
            choices = list(candidates.order_by("source_row", "id").prefetch_related("operations")[:2])
            if not choices:
                raise ValueError(f"El componente {bom.component.code} no tiene ruta en {parent.classification}.")
            child = choices[0]
            if child.status != Route.ACTIVE or len(choices) > 1:
                needs_review = True
            label = make_label(parent, child, bom.component, line, line.quantity * bom.quantity_per,
                               index, len(rm_items) + 1)
            if len(choices) > 1:
                label["preview_note"] = f"Primera coincidencia: Ruta fila {child.source_row}; existe otra fila {choices[1].source_row}."
                notes.append(f"{bom.component.code}: se usó Ruta fila {child.source_row}; también existe fila {choices[1].source_row}.")
            labels.append(label)
    if needs_review:
        for label in labels:
            label["unapproved_preview"] = True
    return labels, notes, needs_review


def make_label(parent, route, component, line, quantity, index, total):
    re_count = total - 1 if total > 1 else (parent.part.components.filter(component__part_type="RM").count() if parent.part_id else 0)
    return {"parent_code": parent.code, "parent_description": parent.description,
            "component_code": component.code if component else route.code,
            "component_description": component.description if component else route.description,
            "dimensions": {"od": component.od_raw, "wall": component.wall_raw, "development": component.development_raw} if component else {},
            "shop_order": line.shop_order, "quantity": format(quantity.normalize(), "f"), "sequence": line.position,
            "label_index": index, "label_total": total, "re_count": re_count, "classification": parent.classification,
            "operations": operation_data(route)}


def paginate_label(label):
    operations = label["operations"]
    chunks = [operations[i:i + ROWS_PER_LABEL] for i in range(0, len(operations), ROWS_PER_LABEL)] or [[]]
    result = []
    for segment, chunk in enumerate(chunks, 1):
        rows = [
            {**operation, "row_number": operation.get("sequence") or operation.get("position") or i + 1}
            for i, operation in enumerate(chunk + [{} for _ in range(WRITABLE_ROWS - len(chunk))])
        ]
        result.append({**label, "operation_rows": rows, "segment": segment, "segments": len(chunks)})
    return result


def print_sheets(snapshot):
    labels = [page for label in snapshot["labels"] for page in paginate_label(label)]
    sheets = []
    for copy_number in range(1, snapshot["copies"] + 1):
        copied = [{**label, "copy_number": copy_number} for label in labels]
        sheets.extend([copied[i:i + 2] for i in range(0, len(copied), 2)])
    return sheets


def render_pdf(snapshot, template_key=CLASSIC_TEMPLATE):
    from weasyprint import HTML

    validate_print_template(template_key)
    logo = Path(settings.BASE_DIR) / "static" / "img" / "mesa.jpg"
    logo_uri = "data:image/jpeg;base64," + base64.b64encode(logo.read_bytes()).decode("ascii")
    html = render_to_string(TEMPLATE_FILES[template_key], {"data": snapshot, "sheets": print_sheets(snapshot), "logo_uri": logo_uri})
    return HTML(string=html).write_pdf()


def issue_schedule(schedule, user, template_key=CLASSIC_TEMPLATE):
    validate_print_template(template_key)
    lines = list(schedule.lines.select_related("route").order_by("position", "id"))
    if not lines:
        raise ValueError("Agregue al menos una partida.")
    snapshot = {"client": schedule.client.name, "week": schedule.week, "line": schedule.line, "copies": schedule.copies,
                "planner": schedule.planner, "responsible": schedule.responsible,
                "issue_date": schedule.issue_date.isoformat(), "ship_date": schedule.ship_date.isoformat() if schedule.ship_date else "",
                "lines": [snapshot_line(line) for line in lines],
                "labels": [label for line in lines for label in labels_for_line(line)],
                "format_status": "Composición cotejada con captura; escala física pendiente"}
    pdf_bytes = render_pdf(snapshot, template_key)
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    document = IssuedDocument(schedule=schedule, created_by=user, template_key=template_key, snapshot=snapshot, sha256=digest)
    document.pdf.save(f"ruta-{schedule.pk}-{digest[:12]}.pdf", ContentFile(pdf_bytes), save=False)
    document.save()
    return document

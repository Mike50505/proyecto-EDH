"""Transient Excel-like order selection. Uploaded rows never reach the database."""
from decimal import Decimal, InvalidOperation
from io import BytesIO
from types import SimpleNamespace

from openpyxl import load_workbook
from django.utils import timezone

from rutas.models import Route
from rutas.services.documents import preview_labels_for_line, render_pdf

HEADERS = ("SHOP ORDER", "ITEM PADRE", "CANTIDAD", "SEMANA", "RE", "SECUENCIA")
OLD_COMMON_HEADERS = ("LINEA", "PLANNER", "RESPONSABLE")
FIELDS = ("shop_order", "parent_code", "quantity", "week", "re", "sequence", "line", "planner", "responsible")
MAX_ROWS = 200


def value_text(value):
    return "" if value is None else str(value).strip()


def blank_rows(count=12):
    return [{field: "" for field in FIELDS} for _ in range(count)]


def read_excel(upload):
    if not upload.name.lower().endswith((".xlsx", ".xlsm")):
        raise ValueError("Carga un archivo Excel .xlsx o .xlsm.")
    if upload.size > 2 * 1024 * 1024:
        raise ValueError("El archivo supera 2 MB. Usa la plantilla solo para seleccionar hasta 200 órdenes.")
    try:
        book = load_workbook(BytesIO(upload.read()), read_only=True, data_only=True)
        sheet = book.active
        headings = tuple(value_text(cell.value).upper() for cell in sheet[1][:9])
        if headings[:6] != HEADERS or (any(headings[6:]) and headings[6:] != OLD_COMMON_HEADERS):
            raise ValueError("La fila 1 debe contener SHOP ORDER, ITEM PADRE, CANTIDAD, SEMANA, RE y Secuencia, en ese orden.")
        rows = []
        for cells in sheet.iter_rows(min_row=2, max_col=9, values_only=True):
            row = {field: value_text(value) for field, value in zip(FIELDS, cells)}
            if any(row.values()):
                rows.append(row)
            if len(rows) > MAX_ROWS:
                raise ValueError("La plantilla admite hasta 200 órdenes por lote.")
        if not rows:
            raise ValueError("La plantilla no contiene órdenes.")
        return rows
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("No se pudo leer el Excel. Descarga la plantilla y verifica que el archivo no esté dañado o cifrado.") from exc


def rows_from_post(post):
    try:
        count = int(post.get("row_count", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("Número de filas inválido.") from exc
    if count < 1 or count > MAX_ROWS:
        raise ValueError("El lote debe tener entre 1 y 200 filas.")
    rows = []
    for index in range(count):
        row = {field: value_text(post.get(f"rows-{index}-{field}")) for field in FIELDS}
        if any(row.get(field) for field in ("shop_order", "parent_code", "quantity", "week", "sequence")):
            rows.append(row)
    if not rows:
        raise ValueError("Agrega al menos una orden.")
    for field in ("line", "planner", "responsible"):
        rows[0][field] = value_text(post.get(f"common_{field}"))
    return rows


def build_pdf(rows, classification, client_name="DAIKIN"):
    """Validate against approved routes and render entirely in memory."""
    first = rows[0]
    defaults = {key: first.get(key, "") for key in ("week", "line", "planner", "responsible")}
    labels = []
    errors = []
    client = None
    has_unapproved_routes = False
    for row_index, row in enumerate(rows, 1):
        display_row = row_index + 1
        effective = {"week": row.get("week") or defaults["week"],
                     "line": defaults["line"], "planner": defaults["planner"],
                     "responsible": defaults["responsible"]}
        for key, title in (("shop_order", "SHOP ORDER"), ("parent_code", "ITEM PADRE")):
            if not row.get(key):
                errors.append(f"Fila {display_row}: falta {title}.")
        if not effective["week"]:
            errors.append(f"Fila {display_row}: falta SEMANA.")
        if row_index == 1:
            for key, title in (("line", "LINEA"), ("planner", "PLANNER"), ("responsible", "RESPONSABLE")):
                if not defaults[key]:
                    errors.append(f"Completa {title} una vez para todo el lote.")
        try:
            quantity = Decimal(row["quantity"])
            if not quantity.is_finite() or quantity <= 0:
                raise InvalidOperation
        except (InvalidOperation, KeyError):
            errors.append(f"Fila {display_row}: CANTIDAD debe ser mayor que cero.")
            continue
        try:
            sequence = int(row["sequence"])
            if sequence <= 0:
                raise ValueError
        except (ValueError, KeyError):
            errors.append(f"Fila {display_row}: Secuencia debe ser un entero positivo.")
            continue
        if not row.get("parent_code"):
            continue
        routes = Route.objects.filter(code__iexact=row["parent_code"], client__name=client_name).exclude(
            status=Route.ARCHIVED).select_related("client", "part", "source")
        if classification:
            routes = routes.filter(classification=classification)
        matches = list(routes.order_by("source_row", "id")[:2])
        if not matches:
            errors.append(f"Fila {display_row}: no se encontró una ruta disponible para {row['parent_code']}.")
            continue
        if not classification and len({route.classification for route in matches}) > 1:
            errors.append(f"Fila {display_row}: {row['parent_code']} existe en varios orígenes. Elige uno en la parte superior.")
            continue
        route = matches[0]
        if client and route.client_id != client.pk:
            errors.append(f"Fila {display_row}: las órdenes del lote deben ser del mismo cliente.")
            continue
        client = route.client
        line = SimpleNamespace(route_id=route.pk, shop_order=row["shop_order"], quantity=quantity, position=sequence)
        try:
            route_labels, _, needs_review = preview_labels_for_line(line)
        except ValueError as exc:
            errors.append(f"Fila {display_row}: {exc}")
            continue
        has_unapproved_routes = has_unapproved_routes or needs_review or len(matches) > 1
        for label in route_labels:
            label.update(effective)
        labels.extend(route_labels)
        row["re"] = str(route_labels[0]["re_count"])
    if errors:
        raise ValueError("\n".join(errors))
    snapshot = {
        "client": client.name, "week": defaults["week"], "line": defaults["line"],
        "planner": defaults["planner"], "responsible": defaults["responsible"],
        "issue_date": timezone.localdate().isoformat(),
        "ship_date": "", "copies": 1, "lines": [], "labels": labels,
        "preview_status": "VISTA PREVIA · RUTAS POR REVISAR · NO APROBADA" if has_unapproved_routes else "SELECCIÓN TEMPORAL · NO GUARDADA",
    }
    return render_pdf(snapshot)

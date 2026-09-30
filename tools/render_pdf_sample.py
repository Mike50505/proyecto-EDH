"""Render the supplied screenshot's two component labels as test data; no DB writes."""
import os
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path.cwd()))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from rutas.models import Part, Route
from rutas.services.documents import make_label, render_pdf

parent_part = Part.objects.get(pk=1)
parent = Route.objects.get(pk=1)
components = list(parent_part.components.filter(component__part_type="RM").select_related("component"))
if len(components) != 2 or parent.code != "4P503730-1":
    raise RuntimeError("La fuente de prueba ya no coincide con la captura.")

line = SimpleNamespace(shop_order="PRUEBA-NO-PRODUCCION", position=1)
labels = []
for number, (bom, route_id) in enumerate(zip(components, (2, 3)), 2):
    child = Route.objects.get(pk=route_id)
    if child.code != bom.component.code:
        raise RuntimeError("La ruta de muestra no coincide con el componente.")
    labels.append(make_label(parent, child, bom.component, line, Decimal("10") * bom.quantity_per, number, 3))

snapshot = {
    "client": parent.client.name,
    "week": "31A",
    "line": "PRUEBA",
    "planner": "PRUEBA",
    "responsible": "PRUEBA",
    "copies": 1,
    "issue_date": "2026-09-29",
    "ship_date": "",
    "lines": [],
    "labels": labels,
}
output = Path("/tmp/sample.pdf")
output.write_bytes(render_pdf(snapshot))
print(output)

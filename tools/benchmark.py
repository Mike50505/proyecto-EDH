"""Small reproducible benchmark against the imported development catalog; no DB writes."""
import os
import sys
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

sys.path.insert(0, str(Path.cwd()))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from django.db.models import Q
from django.template.loader import render_to_string
from weasyprint import HTML
from rutas.models import Operation, Part, Route
from rutas.services.documents import snapshot_line

query = "4P"
t0 = perf_counter()
found = list(Route.objects.filter(Q(code__icontains=query) | Q(description__icontains=query)).order_by("code", "id")[:30])
t1 = perf_counter()
route = Route.objects.filter(status=Route.ACTIVE).first()
detail = Route.objects.select_related("client", "part", "source").prefetch_related("operations").get(pk=route.pk)
list(detail.operations.all())
t2 = perf_counter()
active = list(Route.objects.filter(status=Route.ACTIVE).order_by("id")[:10])
for count in (1, len(active)):
    lines = [snapshot_line(SimpleNamespace(route_id=item.pk, shop_order="PRUEBA", quantity=Decimal("2"), position=i)) for i, item in enumerate(active[:count], 1)]
    data = {"client": route.client.name, "week": "31A", "line": "PRUEBA", "planner": "PRUEBA", "responsible": "PRUEBA", "lines": lines}
    start = perf_counter()
    pdf = HTML(string=render_to_string("rutas/pdf.html", {"data": data})).write_pdf()
    print({"pdf_lines": count, "seconds": round(perf_counter() - start, 3), "bytes": len(pdf)})
print({"search_seconds": round(t1-t0, 4), "detail_seconds": round(t2-t1, 4), "first_page_rows": len(found),
       "routes": Route.objects.count(), "parts": Part.objects.count(), "operations": Operation.objects.count(), "concurrent_users": 1})

"""Smoke-check one temporary PDF for every imported source variant."""
from decimal import Decimal
from io import BytesIO
from time import perf_counter
from types import SimpleNamespace

from django.core.management.base import BaseCommand, CommandError
from pypdf import PdfReader

from rutas.models import Route, SourceBook
from rutas.services.documents import make_label, render_pdf


class Command(BaseCommand):
    help = "Comprueba el PDF provisional y los tiempos de generación para cada fuente importada. No guarda documentos."

    def handle(self, *args, **options):
        sources = SourceBook.objects.select_related("client").order_by("client__name", "classification", "id")
        failures = []
        count = 0
        for source in sources:
            route = (Route.objects.filter(source=source, operations__isnull=False)
                     .select_related("part").prefetch_related("operations").distinct().order_by("pk").first())
            if route is None:
                failures.append(f"{source.client.name}/{source.classification}: no hay ruta con operaciones")
                continue
            line = SimpleNamespace(shop_order="AUDITORIA", position=1)
            label = make_label(route, route, route.part, line, Decimal("1"), 1, 1)
            snapshot = {
                "client": source.client.name, "week": "AUDITORIA", "line": "AUDITORIA",
                "planner": "AUDITORIA", "responsible": "AUDITORIA", "issue_date": "", "ship_date": "",
                "copies": 1, "lines": [], "labels": [label], "preview_status": "AUDITORÍA · NO PRODUCCIÓN",
            }
            started = perf_counter()
            try:
                pdf = render_pdf(snapshot)
                reader = PdfReader(BytesIO(pdf))
                pages = len(reader.pages)
                text = " ".join(page.extract_text() or "" for page in reader.pages)
                if pages < 1 or route.code not in text:
                    raise ValueError("El PDF no contiene una página con el código de ruta")
            except Exception as exc:
                failures.append(f"{source.client.name}/{source.classification}: {exc}")
                continue
            elapsed = (perf_counter() - started) * 1000
            self.stdout.write(f"{source.client.name} / {source.classification}: ruta {route.code}, "
                              f"{pages} página(s), {len(pdf)} bytes, {elapsed:.0f} ms")
            count += 1
        if failures:
            raise CommandError("\n".join(failures))
        if not count:
            raise CommandError("No hay fuentes importadas para comprobar.")
        self.stdout.write(self.style.SUCCESS(f"{count} variantes verificadas; ningún PDF guardado."))

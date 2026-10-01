"""Read-only view benchmark against the populated catalog."""
from concurrent.futures import ThreadPoolExecutor
from statistics import median
from time import perf_counter

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from django.test import RequestFactory

from rutas.models import Route
from rutas.views import route_list


class Command(BaseCommand):
    help = "Mide la vista del catálogo con lecturas concurrentes; no modifica rutas ni documentos."

    def add_arguments(self, parser):
        parser.add_argument("--requests", type=int, default=40)
        parser.add_argument("--workers", type=int, default=4)

    def handle(self, *args, **options):
        total = options["requests"]
        workers = options["workers"]
        if not 1 <= total <= 500 or not 1 <= workers <= 16:
            raise CommandError("Usa entre 1 y 500 solicitudes y entre 1 y 16 trabajadores.")
        user = get_user_model().objects.filter(is_active=True, is_superuser=True).first()
        if user is None:
            raise CommandError("Se necesita un superusuario activo para evaluar la vista.")
        factory = RequestFactory()

        def sample(_):
            close_old_connections()
            try:
                request = factory.get("/", {"client": "", "order": "code"})
                request.user = user
                start = perf_counter()
                response = route_list(request)
                elapsed = (perf_counter() - start) * 1000
                if response.status_code != 200:
                    raise RuntimeError(f"Respuesta HTTP {response.status_code}")
                return elapsed
            finally:
                close_old_connections()

        sample(0)  # warm-up: carga de plantillas y conexiones
        started = perf_counter()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            times = sorted(pool.map(sample, range(total)))
        wall = perf_counter() - started
        p95 = times[max(0, int(0.95 * len(times) + 0.9999) - 1)]
        self.stdout.write(f"Rutas: {Route.objects.count()} · solicitudes: {total} · trabajadores: {workers}")
        self.stdout.write(f"Mediana: {median(times):.0f} ms · p95: {p95:.0f} ms · total: {wall:.2f} s")
        self.stdout.write("Incluye vista, consultas y plantilla; excluye red, proxy y navegador.")

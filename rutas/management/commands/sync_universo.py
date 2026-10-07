import time
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from rutas.services.universo import UniversoError, sync_universo


class Command(BaseCommand):
    help = "Sincroniza el catálogo de Universo Ramos sin modificar el servicio central."

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true", help="Repite la sincronización periódicamente.")

    def handle(self, *args, **options):
        while True:
            try:
                result = sync_universo()
                self.stdout.write(f"Universo: {result['parts']} piezas; {result['linked']} rutas vinculadas.")
            except UniversoError as exc:
                if not options["watch"]:
                    raise CommandError(str(exc)) from None
                self.stderr.write(str(exc))
            if not options["watch"]:
                return
            time.sleep(max(30, settings.UNIVERSO_SYNC_INTERVAL))

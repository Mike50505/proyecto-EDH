from django.core.management.base import BaseCommand
from rutas.services.reconciliation import reconcile_all


class Command(BaseCommand):
    help = "Compara rutas entre libros y reporta FP sin ruta local; no fusiona ni completa datos."

    def handle(self, *args, **options):
        self.stdout.write(str(reconcile_all()))

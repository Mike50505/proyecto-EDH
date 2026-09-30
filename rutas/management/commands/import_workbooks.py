from getpass import getpass
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.core.files import File
from rutas.services.importer import ImportErrorDetailed, import_workbook


class Command(BaseCommand):
    help = "Importa libros XLSM reales. Solicita la contraseña sin eco y no la almacena."

    def add_arguments(self, parser):
        parser.add_argument("files", nargs="+", type=Path)
        parser.add_argument("--commit", action="store_true", help="Escribe catálogo y rutas; sin esta opción solo simula.")

    def handle(self, *args, **options):
        password = getpass("Contraseña de apertura (vacía si no aplica): ")
        for path in options["files"]:
            try:
                with path.open("rb") as stream:
                    run = import_workbook(File(stream, name=path.name), password=password or None, dry_run=not options["commit"])
            except (OSError, ImportErrorDetailed) as exc:
                raise CommandError(f"{path.name}: {exc}") from exc
            self.stdout.write(f"{path.name}: {run.summary}")

"""Read-only source inventory; password is entered without echo and never persisted."""
import getpass
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DJANGO_SECRET_KEY", secrets.token_urlsafe(48))
import django
django.setup()

from django.core.files import File
from rutas.services.importer import scan

password = getpass.getpass("Contraseña de apertura: ")
for path in sorted(Path.cwd().glob("*.xlsm")):
    print(f"Leyendo {path.name}...", flush=True)
    with path.open("rb") as stream:
        result = scan(File(stream, name=path.name), password)
    print({"archivo": path.name, "sha256": result["sha256"], "hojas": result["sheets"], "cliente": result["client"],
           "clasificacion": result["classification"], "familias": len(result["families"]), "rutas": len(result["routes"]),
           "rutas_con_operaciones": sum(bool(x["operations"]) for x in result["routes"]), "grupos": len(result["process_groups"])}, flush=True)

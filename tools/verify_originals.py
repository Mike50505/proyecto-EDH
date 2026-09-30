"""Read-only acceptance checks for the four encrypted originals."""
import getpass
import os
import secrets
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DJANGO_SECRET_KEY", secrets.token_urlsafe(48))
import django
django.setup()

from django.core.files import File
from rutas.services.importer import scan

expected = {
    "Headers": (82, 65, 42, 32),
    "Individuales": (69, 64, 64, 30),
    "SLP Headers": (96, 75, 47, 33),
    "SLP Individuales": (79, 75, 75, 33),
}
password = getpass.getpass("Contraseña de apertura: ")
seen = set()
for path in sorted(Path.cwd().glob("*.xlsm")):
    with path.open("rb") as stream:
        data = scan(File(stream, name=path.name), password)
    classification = data["classification"]
    actual = (len(data["families"]), len(data["routes"]), sum(bool(x["operations"]) for x in data["routes"]), len(data["process_groups"]))
    assert actual == expected[classification], (classification, actual)
    assert data["client"] == "DAIKIN"
    if "Headers" in classification:
        assert [x["row"] for x in data["routes"] if x["code"] == "4PA17856-6"] == [4, 57]
        assert any(x["row"] == 45 and x["code"] == "4P669357-1" and not x["type"] for x in data["families"])
    else:
        assert [x["row"] for x in data["routes"] if x["code"] == "4P663164-1"] == [6, 34]
        assert any(x["row"] == 8 and x["formula"] == "=124-1" and x["development"] == "123" for x in data["families"])
    seen.add(classification)
    print(f"OK {classification}: {actual}", flush=True)
assert seen == set(expected), seen
print("OK: cuatro variantes verificadas sin modificar los originales.")

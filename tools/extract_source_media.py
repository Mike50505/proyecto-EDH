"""Extract source artwork from an encrypted workbook after an unlogged password prompt."""
import getpass
import tempfile
import zipfile
from pathlib import Path

import msoffcrypto

path = next(Path.cwd().glob("*Headers - Ramos*.xlsm"))
password = getpass.getpass("Contraseña de apertura: ")
target = Path("tmp/source_media")
target.mkdir(parents=True, exist_ok=True)
with path.open("rb") as source, tempfile.SpooledTemporaryFile(max_size=16 * 1024 * 1024) as decrypted:
    office = msoffcrypto.OfficeFile(source)
    office.load_key(password=password)
    office.decrypt(decrypted)
    decrypted.seek(0)
    with zipfile.ZipFile(decrypted) as archive:
        for member in archive.namelist():
            if member.startswith("xl/media/") and not member.endswith("/"):
                out = target / Path(member).name
                out.write_bytes(archive.read(member))
                print(out, out.stat().st_size)

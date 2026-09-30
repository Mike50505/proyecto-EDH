"""Inspect stored print settings in encrypted XLSM without loading drawings or running VBA."""
import getpass
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import msoffcrypto

password = getpass.getpass("Contraseña de apertura: ")
ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
for path in sorted(Path.cwd().glob("*.xlsm")):
    print(path.name, flush=True)
    with path.open("rb") as stream, tempfile.SpooledTemporaryFile(max_size=16 * 1024 * 1024) as decrypted:
        office = msoffcrypto.OfficeFile(stream)
        office.load_key(password=password)
        office.decrypt(decrypted)
        decrypted.seek(0)
        with zipfile.ZipFile(decrypted) as archive:
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            areas = [(x.attrib.get("name"), x.text) for x in workbook.findall(".//m:definedName", ns) if "Print" in x.attrib.get("name", "")]
            print("  Áreas:", areas, flush=True)
            sheets = workbook.findall(".//m:sheet", ns)
            for index, sheet in enumerate(sheets, 1):
                if sheet.attrib["name"] not in ("Etiqueta", "Etiqueta1"):
                    continue
                member = f"xl/worksheets/sheet{index}.xml"
                found = {}
                with archive.open(member) as xml:
                    for event, element in ET.iterparse(xml, events=("end",)):
                        tag = element.tag.rsplit("}", 1)[-1]
                        if tag in ("pageSetup", "pageMargins", "printOptions", "sheetPr"):
                            found[tag] = dict(element.attrib)
                        elif tag in ("rowBreaks", "colBreaks"):
                            found[tag] = {"count": element.attrib.get("count")}
                        element.clear()
                print(" ", sheet.attrib["name"], found, flush=True)

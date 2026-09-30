"""Supported clients and workbook variants, independent of workbook filenames."""

CLIENT_VARIANTS = {
    "DAIKIN": ("Headers", "Individuales", "SLP Headers", "SLP Individuales"),
    "LENNOX": ("General",),
    "RHEEM": ("Headers", "Individuales"),
}


def validate_source(client, variant):
    if client not in CLIENT_VARIANTS or variant not in CLIENT_VARIANTS[client]:
        raise ValueError("Selecciona una combinación válida de cliente y origen.")

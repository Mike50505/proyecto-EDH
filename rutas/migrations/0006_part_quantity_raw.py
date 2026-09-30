from django.db import migrations, models


def backfill_quantity(apps, schema_editor):
    Part = apps.get_model("rutas", "Part")
    updates = []
    for part in Part.objects.only("id", "source_values").iterator(chunk_size=500):
        values = part.source_values
        if isinstance(values, list) and len(values) > 6 and values[6] is not None:
            part.quantity_raw = str(values[6])[:80]
            updates.append(part)
    if updates:
        Part.objects.bulk_update(updates, ["quantity_raw"], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [("rutas", "0005_sourcebook_client")]

    operations = [
        migrations.AddField(
            model_name="part",
            name="quantity_raw",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.RunPython(backfill_quantity, migrations.RunPython.noop),
    ]

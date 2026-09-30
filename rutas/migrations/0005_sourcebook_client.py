from django.db import migrations, models
import django.db.models.deletion


def backfill_source_clients(apps, schema_editor):
    SourceBook = apps.get_model("rutas", "SourceBook")
    Client = apps.get_model("rutas", "Client")
    Route = apps.get_model("rutas", "Route")
    Part = apps.get_model("rutas", "Part")
    for source in SourceBook.objects.all():
        client_id = Route.objects.filter(source_id=source.pk).values_list("client_id", flat=True).first()
        if client_id is None:
            client_id = Part.objects.filter(source_id=source.pk).values_list("client_id", flat=True).first()
        if client_id is not None:
            client_name = Client.objects.filter(pk=client_id).values_list("name", flat=True).first()
            SourceBook.objects.filter(pk=source.pk).update(client_id=client_id, print_approved=client_name == "DAIKIN")


class Migration(migrations.Migration):
    dependencies = [("rutas", "0004_schedule_copies")]

    operations = [
        migrations.AddField(
            model_name="sourcebook",
            name="client",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="rutas.client"),
        ),
        migrations.AddField(
            model_name="sourcebook",
            name="print_approved",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(backfill_source_clients, migrations.RunPython.noop),
    ]

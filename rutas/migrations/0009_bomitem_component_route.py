from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("rutas", "0008_route_universe_auto_link")]
    operations = [migrations.AddField(
        model_name="bomitem", name="component_route",
        field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                related_name="parent_bom_items", to="rutas.route"))]

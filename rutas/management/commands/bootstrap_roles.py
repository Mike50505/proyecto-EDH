from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Crea roles de consulta, edición y administración sin asignar usuarios."

    def handle(self, *args, **options):
        role_actions = {
            "Consulta e impresión": {"view_route", "view_part", "view_schedule", "view_issueddocument", "add_schedule", "add_scheduleline", "add_issueddocument"},
            "Edición de rutas": {"view_route", "view_part", "add_route", "change_route", "view_schedule", "add_schedule", "add_scheduleline", "add_issueddocument", "view_issueddocument"},
            "Administración de rutas": {"view_route", "view_part", "add_route", "change_route", "view_schedule", "add_schedule", "add_scheduleline", "add_issueddocument", "view_issueddocument", "add_importrun", "view_importrun", "view_importissue", "change_importissue"},
        }
        for name, codenames in role_actions.items():
            group, _ = Group.objects.get_or_create(name=name)
            group.permissions.set(Permission.objects.filter(content_type__app_label="rutas", codename__in=codenames))
            self.stdout.write(f"{name}: {group.permissions.count()} permisos")

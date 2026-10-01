from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse


class UserManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser("principal", "admin@example.test", "Admin-safe-pass-2026")
        cls.viewer = get_user_model().objects.create_user("lector", "lector@example.test", "Viewer-safe-pass-2026")
        cls.role = Group.objects.create(name="Consulta e impresión")
        cls.editor_role = Group.objects.create(name="Edición de rutas")

    def test_only_superuser_can_access_user_management(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse("rutas:user_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("rutas:user_create")).status_code, 403)
        self.assertEqual(self.client.post(reverse("rutas:user_edit", args=[self.viewer.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("rutas:user_password", args=[self.viewer.pk])).status_code, 403)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("rutas:user_list")), "Nuevo usuario")

    def test_create_edit_deactivate_and_reset_password(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("rutas:user_create"), {
            "username": "operador", "first_name": "Ana", "last_name": "Ramos",
            "email": "ana@example.test", "role": self.role.pk, "is_active": "on",
            "password1": "Strong-pass-2026!", "password2": "Strong-pass-2026!",
        })
        self.assertRedirects(response, reverse("rutas:user_list"))
        user = get_user_model().objects.get(username="operador")
        self.assertTrue(user.check_password("Strong-pass-2026!"))
        self.assertEqual(list(user.groups.values_list("pk", flat=True)), [self.role.pk])
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

        response = self.client.post(reverse("rutas:user_edit", args=[user.pk]), {
            "username": "operador", "first_name": "Ana", "last_name": "Ramos",
            "email": "ana@example.test", "role": self.editor_role.pk,
        })
        self.assertRedirects(response, reverse("rutas:user_list"))
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertEqual(list(user.groups.values_list("pk", flat=True)), [self.editor_role.pk])

        response = self.client.post(reverse("rutas:user_password", args=[user.pk]), {
            "new_password1": "Another-safe-pass-2026!", "new_password2": "Another-safe-pass-2026!",
        })
        self.assertRedirects(response, reverse("rutas:user_edit", args=[user.pk]))
        user.refresh_from_db()
        self.assertTrue(user.check_password("Another-safe-pass-2026!"))

    def test_rejects_weak_password_and_protects_administrative_accounts(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("rutas:user_create"), {
            "username": "newuser", "role": self.role.pk, "is_active": "on",
            "password1": "123", "password2": "123",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username="newuser").exists())
        self.assertEqual(self.client.get(reverse("rutas:user_edit", args=[self.admin.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("rutas:user_password", args=[self.admin.pk])).status_code, 403)

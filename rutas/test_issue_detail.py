from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from rutas.models import Client, ImportIssue, ImportRun, Operation, Route, SourceBook


class IssueComparisonTests(TestCase):
    def setUp(self):
        self.client_name = Client.objects.create(name="DAIKIN")
        other_client = Client.objects.create(name="RHEEM")
        self.source = SourceBook.objects.create(client=self.client_name, filename="uno.xlsm", sha256="a" * 64, classification="Headers")
        second = SourceBook.objects.create(client=self.client_name, filename="dos.xlsm", sha256="b" * 64, classification="SLP Headers")
        foreign = SourceBook.objects.create(client=other_client, filename="otro.xlsm", sha256="c" * 64, classification="Headers")
        run = ImportRun.objects.create(source=self.source, filename="uno.xlsm", sha256="a" * 64, dry_run=False)
        self.issue = ImportIssue.objects.create(run=run, sheet="Ruta", row=4, code="PARTE-1",
                                                kind="diferencia_entre_libros", detail="Operaciones diferentes")
        self.route = Route.objects.create(client=self.client_name, source=self.source, source_sheet="Ruta", source_row=4,
                                          code="PARTE-1", classification="Headers")
        Operation.objects.create(route=self.route, position=1, source_sequence="1", name="CORTE", machine="M-1")
        self.peer = Route.objects.create(client=self.client_name, source=second, source_sheet="Ruta", source_row=8,
                                         code="PARTE-1", classification="SLP Headers")
        Operation.objects.create(route=self.peer, position=1, source_sequence="1", name="DOBLEZ", machine="M-2")
        self.foreign = Route.objects.create(client=other_client, source=foreign, source_sheet="Ruta", source_row=7,
                                            code="PARTE-1", classification="Headers")
        self.admin = get_user_model().objects.create_superuser("admin", "admin@example.test", "Safe-pass-2026")

    def test_comparison_shows_both_variants_without_other_client(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("rutas:issue_detail", args=[self.issue.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CORTE")
        self.assertContains(response, "DOBLEZ")
        self.assertEqual(response.context["selected_peer"].pk, self.peer.pk)
        self.assertNotContains(response, "otro.xlsm")
        response = self.client.get(reverse("rutas:issue_detail", args=[self.issue.pk]), {"peer": self.foreign.pk})
        self.assertEqual(response.context["selected_peer"].pk, self.peer.pk)

    def test_requires_issue_view_permission(self):
        user = get_user_model().objects.create_user("lector", password="Safe-pass-2026")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("rutas:issue_detail", args=[self.issue.pk])).status_code, 403)

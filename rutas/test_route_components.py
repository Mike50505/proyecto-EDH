from decimal import Decimal
from unittest.mock import patch
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from rutas.models import BOMItem, Client, IssuedDocument, Operation, Part, Route, UniversoPart, SourceBook


class IndividualComponentPreviewTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser("component-admin", password="Example-password-482")
        self.client.force_login(user)
        customer = Client.objects.create(name="DAIKIN")
        parent = Part.objects.create(client=customer, code="3P666815-1", part_type="FP")
        child = Part.objects.create(client=customer, code="4P666804-1", part_type="RM")
        BOMItem.objects.create(parent=parent, component=child, quantity_per=Decimal("2"), position=1)
        self.parent = Route.objects.create(client=customer, part=parent, code=parent.code, classification="Headers", status=Route.ACTIVE)
        self.universe = UniversoPart.objects.create(id=uuid.uuid4(), part_number=parent.code,
            normalized_number=parent.code, customer=customer.name)
        self.child = Route.objects.create(client=customer, part=child, code=child.code, classification="Headers", status=Route.ACTIVE)
        Operation.objects.create(route=self.child, position=1, name="CORTE", machine="MAQUINA-1")

    def test_catalog_lists_only_central_parents_and_keeps_child_detail_accessible(self):
        response = self.client.get(reverse("rutas:list"))
        self.assertContains(response, self.parent.code)
        self.assertNotContains(response, self.child.code)
        self.assertEqual(response.context["page"].paginator.count, 1)
        self.assertContains(self.client.get(reverse("rutas:detail", args=[self.child.pk])), "MAQUINA-1")

    def test_select_all_catalog_routes_excludes_children(self):
        response = self.client.post(reverse("rutas:select"), {"scope": "all", "client": "DAIKIN"})
        self.assertEqual(response.status_code, 200)
        selected = [row["parent_code"] for row in response.context["rows"] if row["parent_code"]]
        self.assertEqual(selected, [self.parent.code])
        response = self.client.post(reverse("rutas:select"), {"scope": "page", "route_ids": [self.child.pk]})
        self.assertRedirects(response, reverse("rutas:list"))

    def test_same_parent_number_is_grouped_and_origins_keep_separate_children(self):
        other = Route.objects.create(client=self.parent.client, part=self.parent.part,
            code=self.parent.code, classification="SLP Headers", status=Route.ACTIVE)
        child = Route.objects.create(client=self.child.client, part=self.child.part,
            code=self.child.code, classification="SLP Headers", status=Route.ACTIVE)
        Operation.objects.create(route=child, position=1, name="DOBLEZ SLP", machine="MAQUINA-SLP")
        response = self.client.get(reverse("rutas:list"))
        self.assertEqual(response.context["page"].paginator.count, 1)
        self.assertEqual(response.context["page"].object_list[0].variant_count, 2)
        self.assertContains(response, "Elegir origen")
        response = self.client.get(reverse("rutas:route_group", args=[self.parent.pk]))
        self.assertContains(response, "Headers")
        self.assertContains(response, "SLP Headers")
        self.assertContains(response, "MAQUINA-1")
        self.assertContains(response, "MAQUINA-SLP")
        self.assertEqual([v["route"].pk for v in response.context["variants"]], [self.parent.pk, other.pk])
        self.assertEqual(response.context["variants"][0]["component_labels"][0]["route_id"], self.child.pk)
        self.assertEqual(response.context["variants"][1]["component_labels"][0]["route_id"], child.pk)

    def test_grouped_selection_is_one_row_and_does_not_pick_arbitrary_origin(self):
        Route.objects.create(client=self.parent.client, part=self.parent.part,
            code=self.parent.code, classification="SLP Headers", status=Route.ACTIVE)
        for selection in ({"scope": "all", "client": "DAIKIN"},
                          {"scope": "page", "group_ids": [self.parent.pk]}):
            response = self.client.post(reverse("rutas:select"), selection)
            rows = [r for r in response.context["rows"] if r["parent_code"]]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["parent_code"], self.parent.code)
            self.assertEqual(rows[0]["route_id"], "")
        response = self.client.post(reverse("rutas:select"), {
            "scope": "page", "group_ids": [self.parent.pk], "classification": "Headers"})
        self.assertEqual(response.context["rows"][0]["route_id"], str(self.parent.pk))

    def test_catalog_group_filters_keep_number_unique_and_child_not_a_group(self):
        Route.objects.create(client=self.parent.client, part=self.parent.part,
            code=self.parent.code.lower(), classification="SLP Headers", status=Route.REVIEW)
        response = self.client.get(reverse("rutas:list"), {"q": self.parent.code[:-1], "classification": "SLP Headers"})
        self.assertEqual(response.context["page"].paginator.count, 1)
        self.assertEqual(response.context["page"].object_list[0].variant_count, 1)
        self.assertEqual(self.client.get(reverse("rutas:route_group", args=[self.child.pk])).status_code, 404)

    def test_origin_picker_distinguishes_workbooks_with_same_classification_and_row(self):
        for index, name in enumerate(("EDH Corte LENNOX.xlsm", "Copy of EDH Corte LENNOX.xlsm")):
            source = SourceBook.objects.create(filename=name, sha256=str(index) * 64, classification="General")
            Route.objects.create(client=self.parent.client, code=self.parent.code, source=source,
                classification="General", source_row=2)
        response = self.client.get(reverse("rutas:batch_print"))
        options = response.context["route_catalog"][self.parent.code]
        labels = [o["label"] for o in options]
        self.assertEqual(len(labels), len(set(labels)))
        self.assertTrue(any(" · EDH Corte LENNOX.xlsm · " in label for label in labels))
        self.assertTrue(any(" · Copy of EDH Corte LENNOX.xlsm · " in label for label in labels))

    def test_global_catalog_search_does_not_hide_lennox_by_default_customer(self):
        customer = Client.objects.create(name="LENNOX")
        UniversoPart.objects.create(id=uuid.uuid4(), part_number="626794-01",
            normalized_number="626794-01", customer="LENNOX 1")
        Route.objects.create(client=customer, code="626794-01", classification="General")
        response = self.client.get(reverse("rutas:list"), {"q": "626794-01"})
        self.assertContains(response, "626794-01")
        self.assertEqual(response.context["client_name"], "")
        self.assertEqual(response.context["page"].paginator.count, 1)

    def test_central_uuid_survives_number_change_and_inactive_pieces_leave_catalog(self):
        self.parent.universe_part = self.universe
        self.parent.save()
        self.universe.part_number = "NEW-NUMBER"
        self.universe.normalized_number = "NEW-NUMBER"
        self.universe.save()
        self.assertContains(self.client.get(reverse("rutas:list")), self.parent.code)
        self.universe.active = False
        self.universe.save()
        self.assertNotContains(self.client.get(reverse("rutas:list")), self.parent.code)

    def test_parent_detail_shows_component_operations_without_copying_them(self):
        response = self.client.get(reverse("rutas:detail", args=[self.parent.pk]))
        self.assertContains(response, "Rutas de los componentes")
        self.assertContains(response, "4P666804-1")
        self.assertContains(response, "MAQUINA-1")
        self.assertNotContains(response, "Esta ruta no tiene operaciones.")
        self.assertEqual(self.parent.operations.count(), 0)
        self.assertEqual(self.child.operations.count(), 1)

    @patch("rutas.views.render_pdf", return_value=b"%PDF-test")
    def test_individual_pdf_uses_component_routes_and_keeps_parent_optional(self, render_pdf):
        url = reverse("rutas:route_print", args=[self.parent.pk])
        response = self.client.get(url, {"label_mode":"components_only"})
        self.assertEqual(response.status_code, 200)
        snapshot = render_pdf.call_args.args[0]
        self.assertEqual(len(snapshot["labels"]), 1)
        self.assertEqual(snapshot["labels"][0]["component_code"], "4P666804-1")
        self.assertEqual(snapshot["labels"][0]["operations"][0]["name"], "CORTE")
        self.assertEqual(snapshot["labels"][0]["quantity"], "—")
        self.client.get(url, {"label_mode": "include_parent"})
        labels = render_pdf.call_args.args[0]["labels"]
        self.assertEqual(len(labels), 2)
        self.assertTrue(labels[0]["is_parent"])
        self.assertTrue(labels[0]["parent_operations_missing"])
        self.assertFalse(IssuedDocument.objects.exists())

    def test_missing_component_route_displays_error_instead_of_empty_parent_pdf(self):
        self.child.status = Route.ARCHIVED
        self.child.save()
        response = self.client.get(reverse("rutas:detail", args=[self.parent.pk]))
        self.assertContains(response, "El componente 4P666804-1 no tiene ruta")
        response = self.client.get(reverse("rutas:route_print", args=[self.parent.pk]))
        self.assertRedirects(response, reverse("rutas:detail", args=[self.parent.pk]))

    @patch("rutas.views.render_pdf", return_value=b"%PDF-test")
    def test_parent_process_prints_without_inventing_missing_material_route(self, render_pdf):
        self.child.delete()
        self.parent.source = SourceBook.objects.create(filename="Parent process.xlsm", sha256="a" * 64, classification="Headers")
        self.parent.save(update_fields=["source"])
        Operation.objects.create(route=self.parent, position=1, name="DOBLEZ PADRE")
        response = self.client.get(reverse("rutas:detail", args=[self.parent.pk]))
        self.assertContains(response, "Componentes del padre")
        self.assertContains(response, "4P666804-1")
        self.assertNotContains(response, "no tiene ruta en")
        response = self.client.get(reverse("rutas:route_print", args=[self.parent.pk]))
        self.assertEqual(response.status_code, 200)
        labels = render_pdf.call_args.args[0]["labels"]
        self.assertEqual(len(labels), 1)
        self.assertEqual(labels[0]["component_code"], self.parent.code)
        self.assertEqual(labels[0]["operations"][0]["name"], "DOBLEZ PADRE")
        self.assertFalse(Route.objects.filter(code="4P666804-1").exists())

    def test_partial_component_routes_do_not_silently_print_parent_instead(self):
        from types import SimpleNamespace
        from rutas.services.documents import preview_labels_for_line
        Operation.objects.create(route=self.parent, position=1, name="PADRE")
        missing = Part.objects.create(client=self.parent.client, code="MISSING", part_type="RM")
        BOMItem.objects.create(parent=self.parent.part, component=missing, quantity_per=1, position=2)
        with self.assertRaisesMessage(ValueError, "El componente MISSING no tiene ruta"):
            preview_labels_for_line(SimpleNamespace(route_id=self.parent.pk, shop_order="31", quantity=Decimal("10"), position=1))

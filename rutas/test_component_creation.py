from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from pypdf import PdfReader

from rutas.models import BOMItem, Client, Operation, Part, Route, UniversoPart, SourceBook
from rutas.services.documents import (preview_labels_for_line, labels_for_line, print_sheets,
                                      render_pdf, LABEL_MODE_INCLUDE_PARENT, MODERN_TEMPLATE)


class ComponentCreationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("component-maker", password="Example-password-482")
        self.client.force_login(self.user)
        self.customer = Client.objects.create(name="DAIKIN")
        self.piece = UniversoPart.objects.create(id=uuid.uuid4(), part_number="PARENT-NEW",
            normalized_number="PARENT-NEW", customer="DAIKIN")

    def payload(self):
        data = {"universe_id": str(self.piece.pk), "client": self.customer.pk, "status": "review",
            "family-code": self.piece.part_number, "family-part_type": "FP",
            "operations-TOTAL_FORMS": "0", "operations-INITIAL_FORMS": "0",
            "components-TOTAL_FORMS": "2", "components-INITIAL_FORMS": "0"}
        for index, code in enumerate(("CHILD-A", "CHILD-B")):
            prefix = f"components-{index}"
            data.update({f"{prefix}-code": code, f"{prefix}-description": f"Material {index}",
                f"{prefix}-quantity_per": str(index + 1), f"{prefix}-od_raw": "3/8",
                f"{prefix}-operations-TOTAL_FORMS": "1", f"{prefix}-operations-INITIAL_FORMS": "0",
                f"{prefix}-operations-0-position": "1", f"{prefix}-operations-0-source_sequence": "1",
                f"{prefix}-operations-0-name": f"PROCESS-{index}", f"{prefix}-operations-0-machine": f"M-{index}"})
        return data

    def edit_payload(self, parent):
        response = self.client.get(reverse("rutas:edit", args=[parent.pk]))
        self.assertEqual(response.status_code, 200)
        data = {}

        def fields(form, allowed=None):
            for field in form:
                if field.field.disabled or (allowed and field.name not in allowed):
                    continue
                value = field.value()
                if value is False or value is None:
                    continue
                data[field.html_name] = "on" if value is True else str(value)

        fields(response.context["form"], {"classification", "revision", "status", "version"})
        fields(response.context["family_form"])

        def operations(formset):
            fields(formset.management_form)
            for form in formset:
                fields(form, {"id", "position", "source_sequence", "name", "machine", "tooling", "inspection", "DELETE"})

        operations(response.context["formset"])
        fields(response.context["components"].management_form)
        for row in response.context["component_rows"]:
            fields(row["form"])
            operations(row["operations"])
        return data, response

    def create(self, data=None):
        response = self.client.post(reverse("rutas:create"), data or self.payload())
        self.assertEqual(response.status_code, 302)
        return Route.objects.get(universe_part=self.piece)

    def test_create_parent_with_two_children_and_independent_processes(self):
        parent = self.create()
        self.assertEqual(parent.part.part_type, "FP")
        self.assertEqual(parent.operations.count(), 0)
        items = list(parent.part.components.select_related("component", "component_route"))
        self.assertEqual([i.component.code for i in items], ["CHILD-A", "CHILD-B"])
        self.assertEqual([i.quantity_per for i in items], [Decimal("1"), Decimal("2")])
        for index, item in enumerate(items):
            self.assertEqual(item.component.part_type, "RM")
            self.assertEqual(item.component_route.operations.get().name, f"PROCESS-{index}")
            self.assertFalse(item.component_route.universe_auto_link)
            self.assertIsNone(item.component_route.universe_part_id)
        detail = self.client.get(reverse("rutas:detail", args=[parent.pk]))
        self.assertContains(detail, "CHILD-A")
        self.assertContains(detail, "PROCESS-1")
        child_detail = self.client.get(reverse("rutas:detail", args=[items[0].component_route.pk]))
        self.assertContains(child_detail, "Componente de")
        self.assertContains(child_detail, self.piece.part_number)
        self.assertNotContains(child_detail, "Vincular pieza")

    def test_invalid_child_saves_nothing_and_keeps_all_tables(self):
        data = self.payload()
        data["components-1-operations-0-position"] = "-1"
        response = self.client.post(reverse("rutas:create"), data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Route.objects.exists())
        self.assertFalse(Part.objects.exists())
        self.assertFalse(BOMItem.objects.exists())
        self.assertEqual(len(response.context["component_rows"]), 2)
        self.assertContains(response, 'value="CHILD-B"')

    def test_duplicate_child_or_parent_code_is_rejected(self):
        for code in ("child-a", self.piece.part_number):
            data = self.payload()
            data["components-1-code"] = code
            response = self.client.post(reverse("rutas:create"), data)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(Route.objects.exists())

    def test_deleted_component_is_not_saved_even_with_empty_metadata(self):
        data = self.payload()
        data["components-1-DELETE"] = "on"
        data["components-1-code"] = ""
        del data["components-1-operations-TOTAL_FORMS"]
        parent = self.create(data)
        self.assertEqual(parent.part.components.count(), 1)
        self.assertEqual(Route.objects.count(), 2)

    def test_component_requires_positive_quantity_and_at_least_one_operation(self):
        for field, value in (("quantity_per", "0"), ("operations-TOTAL_FORMS", "0")):
            data = self.payload()
            data[f"components-1-{field}"] = value
            response = self.client.post(reverse("rutas:create"), data)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(Route.objects.exists())

    def test_exact_child_route_prints_correct_quantity_despite_same_number_elsewhere(self):
        parent = self.create()
        wrong = Route.objects.create(client=self.customer, code="CHILD-A", status=Route.ACTIVE)
        Operation.objects.create(route=wrong, position=1, name="WRONG-PROCESS")
        line = SimpleNamespace(route_id=parent.pk, shop_order="31", quantity=Decimal("8"), position=1)
        labels, _, _ = preview_labels_for_line(line)
        self.assertEqual([label["quantity"] for label in labels], ["8", "16"])
        self.assertEqual([label["operations"][0]["name"] for label in labels], ["PROCESS-0", "PROCESS-1"])
        self.assertEqual([label["label_index"] for label in labels], [1, 2])
        Route.objects.filter(pk__in=[parent.pk, *parent.part.components.values_list("component_route_id", flat=True)]).update(status=Route.ACTIVE)
        self.assertEqual([label["quantity"] for label in labels_for_line(line)], ["8", "16"])
        labels, _, _ = preview_labels_for_line(line, LABEL_MODE_INCLUDE_PARENT)
        self.assertEqual(len(labels), 3)
        self.assertTrue(labels[0]["is_parent"])

    def test_long_component_operations_continue_across_print_sheets(self):
        parent = self.create()
        child = parent.part.components.first().component_route
        Operation.objects.bulk_create([Operation(route=child, position=index, name=f"STEP-{index}")
                                      for index in range(2, 27)])
        line = SimpleNamespace(route_id=parent.pk, shop_order="31", quantity=Decimal("8"), position=1)
        labels, _, _ = preview_labels_for_line(line)
        snapshot = {"labels": labels, "copies": 1, "client": "DAIKIN", "week": "31",
                    "line": "", "planner": "", "responsible": "", "issue_date": "", "ship_date": ""}
        self.assertEqual(len(print_sheets(snapshot)), 2)
        pdf = PdfReader(BytesIO(render_pdf(snapshot, MODERN_TEMPLATE)))
        self.assertEqual(len(pdf.pages), 2)
        text = " ".join(page.extract_text() for page in pdf.pages)
        self.assertIn("STEP-26", text)
        self.assertIn("CHILD-B", text)

    def test_editor_renders_dynamic_component_and_operation_templates(self):
        response = self.client.get(reverse("rutas:create"), {"universe_id": str(self.piece.pk)})
        self.assertContains(response, "Agregar componente")
        self.assertContains(response, 'name="components-TOTAL_FORMS"')
        self.assertContains(response, 'name="components-__component__-code"')
        self.assertContains(response, 'data-formset-template="components-__component__-operations"')

    @patch("rutas.views.render_pdf", return_value=b"%PDF-test")
    def test_default_individual_print_includes_parent_and_children(self, render):
        parent = self.create()
        Operation.objects.create(route=parent, position=1, name="PARENT-PROCESS")
        response = self.client.get(reverse("rutas:route_print", args=[parent.pk]))
        self.assertEqual(response.status_code, 200)
        labels = render.call_args.args[0]["labels"]
        self.assertEqual([label["component_code"] for label in labels], [self.piece.part_number, "CHILD-A", "CHILD-B"])
        self.assertTrue(labels[0]["is_parent"])
        self.assertEqual(labels[0]["operations"][0]["name"], "PARENT-PROCESS")

    def test_batch_picker_and_post_only_accept_parents_even_if_child_number_is_central(self):
        from rutas.services.batch_selection import build_pdf
        parent = self.create()
        child = parent.part.components.first().component_route
        UniversoPart.objects.create(id=uuid.uuid4(), part_number=child.code,
            normalized_number=child.code, customer=self.customer.name)
        response = self.client.get(reverse("rutas:batch_print"))
        self.assertIn(parent.code, response.context["route_catalog"])
        self.assertNotIn(child.code, response.context["route_catalog"])
        self.assertEqual(response.context["label_mode"], "include_parent")
        with self.assertRaisesMessage(ValueError, "no se encontró ITEM PADRE"):
            build_pdf([{"parent_code":child.code, "route_id":str(child.pk), "quantity":"1", "week":"31"}])

    @patch("rutas.views.build_pdf", return_value=b"%PDF-test")
    def test_batch_print_defaults_to_parent_and_components(self, render):
        parent = self.create()
        response = self.client.post(reverse("rutas:batch_print"), {
            "action":"print", "row_count":"1", "rows-0-parent_code":parent.code,
            "rows-0-route_id":str(parent.pk), "rows-0-quantity":"3", "rows-0-week":"31"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(render.call_args.args[2], "include_parent")

    def test_default_processes_are_loaded_for_parent_and_new_child(self):
        from rutas.forms import DEFAULT_PROCESSES
        response = self.client.get(reverse("rutas:create"), {"universe_id": str(self.piece.pk)})
        for formset in (response.context["formset"], response.context["component_empty"]["operations"]):
            self.assertEqual(len(formset.forms), 24)
            self.assertEqual([form.initial["name"] for form in formset], list(DEFAULT_PROCESSES))

    def test_only_completed_default_rows_are_saved(self):
        from rutas.forms import DEFAULT_PROCESSES
        data = self.payload()
        data["operations-TOTAL_FORMS"] = "24"
        data["components-0-operations-TOTAL_FORMS"] = "24"
        for prefix in ("operations", "components-0-operations"):
            for index, name in enumerate(DEFAULT_PROCESSES):
                data[f"{prefix}-{index}-position"] = str(index + 1)
                data[f"{prefix}-{index}-name"] = name
                for field in ("source_sequence", "machine", "tooling", "inspection"):
                    data[f"{prefix}-{index}-{field}"] = ""
        data["operations-5-source_sequence"] = "1"
        data["operations-5-machine"] = "M-PERFORACION"
        data["components-0-operations-0-tooling"] = "H-CORTE"
        parent = self.create(data)
        self.assertEqual(list(parent.operations.values_list("name", flat=True)), ["PERFORACION"])
        child = parent.part.components.first().component_route
        self.assertEqual(list(child.operations.values_list("name", flat=True)), ["CORTE"])
        self.assertEqual(child.operations.get().tooling, "H-CORTE")

    def test_untouched_default_child_processes_do_not_make_an_empty_route_valid(self):
        from rutas.forms import DEFAULT_PROCESSES
        data = self.payload()
        prefix = "components-0-operations"
        data[f"{prefix}-TOTAL_FORMS"] = "24"
        for index, name in enumerate(DEFAULT_PROCESSES):
            data[f"{prefix}-{index}-position"] = str(index + 1)
            data[f"{prefix}-{index}-name"] = name
            data[f"{prefix}-{index}-source_sequence"] = ""
            data[f"{prefix}-{index}-machine"] = ""
        response = self.client.post(reverse("rutas:create"), data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Route.objects.exists())

    def test_edit_has_same_family_component_and_preset_editors_as_create(self):
        parent = self.create()
        _, response = self.edit_payload(parent)
        self.assertContains(response, "Agregar componente")
        self.assertContains(response, 'data-family-editor')
        self.assertEqual(len(response.context["component_rows"]), 2)
        child = response.context["component_rows"][0]["operations"]
        self.assertEqual(child.forms[0].initial["name"], "PROCESS-0")
        self.assertEqual(len(child.forms), 25)
        self.assertEqual(len(response.context["formset"].forms), 24)

    def test_edit_updates_family_quantities_and_child_processes_without_duplicate_routes(self):
        parent = self.create()
        child_id = parent.part.components.first().component_route_id
        data, _ = self.edit_payload(parent)
        data["family-drawing_number"] = "NEW-DRAWING"
        data["components-0-quantity_per"] = "3"
        data["components-0-operations-0-machine"] = "NEW-MACHINE"
        response = self.client.post(reverse("rutas:edit", args=[parent.pk]), data)
        self.assertEqual(response.status_code, 302)
        parent.refresh_from_db()
        self.assertEqual(parent.part.drawing_number, "NEW-DRAWING")
        self.assertEqual(parent.part.components.first().quantity_per, Decimal("3"))
        self.assertEqual(Route.objects.count(), 3)
        self.assertEqual(Route.objects.get(pk=child_id).operations.get().machine, "NEW-MACHINE")
        self.assertEqual(parent.operations.count(), 0)

    def test_edit_can_remove_child_and_add_another_with_operations(self):
        parent = self.create()
        data, _ = self.edit_payload(parent)
        data["components-0-DELETE"] = "on"
        data["components-TOTAL_FORMS"] = "3"
        data.update({"components-2-code": "CHILD-C", "components-2-quantity_per": "4",
            "components-2-operations-TOTAL_FORMS": "1", "components-2-operations-INITIAL_FORMS": "0",
            "components-2-operations-0-position": "1", "components-2-operations-0-name": "CORTE",
            "components-2-operations-0-source_sequence": "1"})
        response = self.client.post(reverse("rutas:edit", args=[parent.pk]), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(parent.part.components.values_list("component__code", flat=True)), ["CHILD-B", "CHILD-C"])

    def test_invalid_or_stale_child_edit_preserves_whole_parent(self):
        parent = self.create()
        data, _ = self.edit_payload(parent)
        data["components-0-quantity_per"] = "0"
        response = self.client.post(reverse("rutas:edit", args=[parent.pk]), data)
        self.assertEqual(response.status_code, 200)
        parent.refresh_from_db()
        self.assertEqual(parent.version, 1)
        data, _ = self.edit_payload(parent)
        child = parent.part.components.first().component_route
        child.version += 1
        child.save(update_fields=["version"])
        data["components-0-description"] = "MUST NOT SAVE"
        response = self.client.post(reverse("rutas:edit", args=[parent.pk]), data)
        self.assertEqual(response.status_code, 200)
        parent.refresh_from_db()
        self.assertEqual(parent.version, 1)
        self.assertNotEqual(parent.part.components.first().component.description, "MUST NOT SAVE")

    def test_imported_material_without_child_process_route_remains_a_material(self):
        source = SourceBook.objects.create(filename="Own process.xlsm", sha256="b"*64, classification="General")
        part = Part.objects.create(client=self.customer, code=self.piece.part_number, part_type="FP", source=source, source_row=1)
        material = Part.objects.create(client=self.customer, code="RAW-A", part_type="RM", source=source, source_row=2)
        BOMItem.objects.create(parent=part, component=material, quantity_per=1, position=1)
        parent = Route.objects.create(client=self.customer, part=part, code=part.code, source=source, universe_part=self.piece)
        Operation.objects.create(route=parent, position=1, name="CORTE", machine="OLD")
        data, _ = self.edit_payload(parent)
        response = self.client.post(reverse("rutas:edit", args=[parent.pk]), data)
        self.assertEqual(response.status_code, 302)
        parent.refresh_from_db()
        self.assertEqual(parent.operations.get().machine, "OLD")
        self.assertEqual(parent.part.components.get().component.code, "RAW-A")
        self.assertFalse(Route.objects.filter(code="RAW-A").exists())

    def test_editing_imported_child_forks_process_without_changing_other_assemblies(self):
        parent = self.create()
        bom = parent.part.components.first()
        child = bom.component_route
        bom.component_route = None
        bom.save(update_fields=["component_route"])
        other_part = Part.objects.create(client=self.customer, code="OTHER-PARENT", part_type="FP")
        BOMItem.objects.create(parent=other_part, component=bom.component, quantity_per=1, position=1)
        other = Route.objects.create(client=self.customer, code=other_part.code, part=other_part)
        data, _ = self.edit_payload(parent)
        data["components-0-operations-0-machine"] = "ONLY-THIS-PARENT"
        response = self.client.post(reverse("rutas:edit", args=[parent.pk]), data)
        self.assertEqual(response.status_code, 302)
        changed = parent.part.components.first().component_route
        self.assertNotEqual(changed.pk, child.pk)
        child.refresh_from_db()
        self.assertEqual(child.operations.get().machine, "M-0")
        self.assertEqual(changed.operations.get().machine, "ONLY-THIS-PARENT")
        labels, _, _ = preview_labels_for_line(SimpleNamespace(route_id=other.pk, shop_order="31", quantity=Decimal("1"), position=1))
        self.assertEqual(labels[0]["operations"][0]["machine"], "M-0")

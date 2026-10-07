import uuid
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rutas.models import Client, IssuedDocument, Operation, Route, Schedule, UniversoPart, UniversoSync
from rutas.services.universo import UniversoAPI, UniversoError, link_matching_routes, normalize, sync_universo


def payload(part_id=None, **extra):
    return {"id": str(part_id or uuid.uuid4()), "part_number": "001-A", "customer": "DAIKIN",
            "active": True, "version": 1, "diameter": "3/8", "wall": "0.000", **extra}


@override_settings(UNIVERSO_API_KEY="test-only", UNIVERSO_BASE_URL="https://example.test/api/v1/")
class UniversoTests(TestCase):
    def setUp(self):
        self.customer = Client.objects.create(name="DAIKIN")
        self.admin = get_user_model().objects.create_superuser("universe-admin", password="Example-password-482")
        self.client.force_login(self.admin)

    def piece(self, **extra):
        data = payload(**extra)
        return UniversoPart.objects.create(id=uuid.UUID(data["id"]), part_number=data["part_number"],
            normalized_number=normalize(data["part_number"]), customer=data["customer"],
            active=data["active"], version=data["version"], data=data)

    def test_links_multiple_origins_and_unique_number_despite_customer_name(self):
        piece = self.piece()
        routes = [Route.objects.create(client=self.customer, code=" 001-a ", status=Route.ACTIVE) for _ in range(2)]
        other = Client.objects.create(name="DAIKIN OTHER")
        mismatch = Route.objects.create(client=other, code="001-A")
        operation = Operation.objects.create(route=routes[0], position=1, name="CORTE")
        self.assertEqual(link_matching_routes(), 3)
        self.assertEqual(link_matching_routes(), 0)
        for route in routes:
            route.refresh_from_db()
            self.assertEqual(route.universe_part_id, piece.pk)
            self.assertEqual(route.version, 2)
        mismatch.refresh_from_db()
        self.assertEqual(mismatch.universe_part_id, piece.pk)
        operation.refresh_from_db()
        self.assertEqual(operation.name, "CORTE")
        self.assertFalse(Schedule.objects.exists())
        self.assertFalse(IssuedDocument.objects.exists())

    def test_repeated_central_number_requires_unique_customer_match(self):
        first = self.piece()
        self.piece(customer="LENNOX")
        exact = Route.objects.create(client=self.customer, code="001-A")
        other = Client.objects.create(name="RHEEM")
        ambiguous = Route.objects.create(client=other, code="001-A")
        self.assertEqual(link_matching_routes(), 1)
        exact.refresh_from_db()
        ambiguous.refresh_from_db()
        self.assertEqual(exact.universe_part_id, first.pk)
        self.assertIsNone(ambiguous.universe_part_id)

    def test_unique_number_does_not_relink_manual_exclusions_or_inactive_piece(self):
        self.piece()
        excluded = Route.objects.create(client=self.customer, code="001-A", universe_auto_link=False)
        self.piece(part_number="INACTIVE", active=False)
        inactive = Route.objects.create(client=self.customer, code="INACTIVE")
        self.assertEqual(link_matching_routes(), 0)
        for route in (excluded, inactive):
            route.refresh_from_db()
            self.assertIsNone(route.universe_part_id)

    def test_initial_sync_and_replay_are_idempotent(self):
        data = payload(version=2)
        older = {**data, "version": 1, "part_number": "OLD"}
        replies = [{"customers": []}, {"changes_cursor": "seed"}, {"results": [data], "next": None},
                   {"results": [{"part_id": data["id"], "part": older}], "next_cursor": "done", "has_more": False}]
        with patch.object(UniversoAPI, "get", side_effect=replies):
            sync_universo()
        self.assertEqual(UniversoPart.objects.get().part_number, "001-A")
        self.assertEqual(UniversoSync.objects.get().cursor, "done")
        with patch.object(UniversoAPI, "get", side_effect=[{"customers": []}, {"results": [], "next_cursor": "done", "has_more": False}]):
            sync_universo()
        self.assertEqual(UniversoPart.objects.count(), 1)

    def test_invalid_event_rolls_back_entire_page_and_cursor(self):
        piece = self.piece()
        UniversoSync.objects.create(cursor="previous", initialized=True)
        changed = {**piece.data, "version": 2, "active": False}
        bad = payload(part_number="")
        replies = [{"customers": []}, {"results": [
            {"part_id": changed["id"], "part": changed}, {"part_id": bad["id"], "part": bad}],
            "next_cursor": "unsafe", "has_more": False}]
        with patch.object(UniversoAPI, "get", side_effect=replies):
            with self.assertRaises(UniversoError):
                sync_universo()
        piece.refresh_from_db()
        self.assertTrue(piece.active)
        self.assertEqual(UniversoSync.objects.get().cursor, "previous")
        self.assertIsNone(UniversoSync.objects.get().lease)

    def test_deactivation_preserves_route_link_and_operations(self):
        piece = self.piece()
        route = Route.objects.create(client=self.customer, code="001-A", universe_part=piece)
        Operation.objects.create(route=route, position=1, name="CORTE")
        UniversoSync.objects.create(cursor="previous", initialized=True)
        changed = {**piece.data, "version": 2, "active": False}
        with patch.object(UniversoAPI, "get", side_effect=[{"customers": []}, {
            "results": [{"part_id": changed["id"], "part": changed}], "next_cursor": "done", "has_more": False}]):
            sync_universo()
        piece.refresh_from_db()
        route.refresh_from_db()
        self.assertFalse(piece.active)
        self.assertEqual(route.universe_part_id, piece.pk)
        self.assertEqual(route.operations.get().name, "CORTE")

    def test_coverage_counts_pieces_not_routes_and_manual_unlink_is_respected(self):
        piece = self.piece()
        route = Route.objects.create(client=self.customer, code="001-A", universe_part=piece, status=Route.ACTIVE)
        Route.objects.create(client=self.customer, code="001-A", universe_part=piece, status=Route.ACTIVE)
        self.piece(part_number="NO-ROUTE")
        response = self.client.get(reverse("rutas:universe"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["stats"]["covered"], 1)
        self.assertEqual(response.context["stats"]["missing"], 1)
        self.client.post(reverse("rutas:universe_unlink", args=[route.pk]))
        self.assertEqual(link_matching_routes(), 0)
        route.refresh_from_db()
        self.assertIsNone(route.universe_part_id)

    def test_view_permissions_and_manual_link_confirmation(self):
        piece = self.piece()
        route = Route.objects.create(client=self.customer, code="001-A")
        url = reverse("rutas:universe_link", args=[route.pk])
        self.client.post(url, {"piece_id": str(piece.pk)})
        route.refresh_from_db()
        self.assertIsNone(route.universe_part_id)
        self.client.post(url, {"piece_id": str(piece.pk), "confirm": "yes"})
        route.refresh_from_db()
        self.assertEqual(route.universe_part_id, piece.pk)
        user = get_user_model().objects.create_user("no-permissions", password="Example-password-482")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("rutas:universe")).status_code, 403)
        self.assertEqual(self.client.post(reverse("rutas:universe_sync")).status_code, 403)

    def test_pending_links_only_count_numbers_present_in_active_universe(self):
        self.piece()
        pending = Route.objects.create(client=self.customer, code="001-A", universe_auto_link=False)
        Route.objects.create(client=self.customer, code="RM-CHILD")
        Route.objects.create(client=self.customer, code="OLD-PARENT")
        self.piece(part_number="INACTIVE", active=False)
        Route.objects.create(client=self.customer, code="INACTIVE")
        response = self.client.get(reverse("rutas:universe"))
        self.assertEqual(response.context["unlinked_count"], 1)
        self.assertEqual(response.context["outside_universe_count"], 3)
        self.assertEqual(list(response.context["unlinked"]), [pending])
        response = self.client.get(reverse("rutas:universe"), {"q": "NO-MATCH"})
        self.assertEqual(response.context["unlinked_count"], 0)

    def test_prefill_and_create_linked_route(self):
        piece = self.piece()
        response = self.client.get(reverse("rutas:create"), {"universe_id": str(piece.pk)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["family_form"].initial["code"], "001-A")
        data = {"universe_id": str(piece.pk), "client": self.customer.pk, "status": "review",
            "family-code": "001-A", "family-part_type": "FP", "family-wall_raw": "0.000",
            "operations-TOTAL_FORMS": "1", "operations-INITIAL_FORMS": "0",
            "operations-MIN_NUM_FORMS": "0", "operations-MAX_NUM_FORMS": "200",
            "operations-0-position": "1", "operations-0-name": "CORTE"}
        response = self.client.post(reverse("rutas:create"), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Route.objects.get().universe_part_id, piece.pk)
        self.assertEqual(Route.objects.get().operations.get().name, "CORTE")
        data["family-code"] = "OTHER"
        self.assertEqual(self.client.post(reverse("rutas:create"), data).status_code, 400)
        self.assertEqual(Route.objects.count(), 1)

    def test_new_route_starts_with_only_active_central_pieces_without_any_route(self):
        available = self.piece(part_number="AVAILABLE")
        linked = self.piece(part_number="LINKED")
        Route.objects.create(client=self.customer, code="LINKED", universe_part=linked)
        self.piece(part_number="LEGACY")
        Route.objects.create(client=self.customer, code=" legacy ")
        self.piece(part_number="INACTIVE", active=False)
        response = self.client.get(reverse("rutas:create"))
        self.assertTemplateUsed(response, "rutas/select_new_route.html")
        self.assertEqual(list(response.context["page"]), [available])

    def test_cannot_create_without_central_selection_or_change_part_number(self):
        self.assertEqual(self.client.post(reverse("rutas:create"), {}).status_code, 400)
        piece = self.piece()
        data = {"universe_id":str(piece.pk), "client":self.customer.pk, "status":"review",
            "family-code":"OTHER", "family-part_type":"FP",
            "operations-TOTAL_FORMS":"1", "operations-INITIAL_FORMS":"0",
            "operations-MIN_NUM_FORMS":"0", "operations-MAX_NUM_FORMS":"200",
            "operations-0-position":"1", "operations-0-name":"CORTE"}
        response = self.client.post(reverse("rutas:create"), data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["family_form"].errors)
        self.assertFalse(Route.objects.exists())

    def test_existing_number_cannot_be_created_again_even_if_unlinked_or_archived(self):
        piece = self.piece()
        route = Route.objects.create(client=self.customer, code="001-A", status=Route.ARCHIVED)
        self.assertEqual(self.client.get(reverse("rutas:create"), {"universe_id":str(piece.pk)}).status_code, 400)
        self.assertEqual(self.client.post(reverse("rutas:duplicate", args=[route.pk])).status_code, 400)

    def test_does_not_send_key_to_external_pagination_url(self):
        api = UniversoAPI()
        with patch("rutas.services.universo.build_opener") as opener:
            with self.assertRaises(UniversoError):
                api.get("https://other.test/api/v1/parts/")
            opener.assert_not_called()

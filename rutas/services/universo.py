"""Read-only API consumer. Never changes central parts or existing route content."""
import json
import unicodedata
import uuid
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from rutas.models import Route, RouteChange, UniversoPart, UniversoSync


def normalize(value):
    return unicodedata.normalize("NFKC", value or "").strip().upper()


class UniversoError(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class UniversoAPI:
    def __init__(self):
        self.base = settings.UNIVERSO_BASE_URL.rstrip("/") + "/"
        parsed = urlparse(self.base)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise UniversoError("La dirección de Universo debe utilizar HTTPS.")
        if not settings.UNIVERSO_API_KEY:
            raise UniversoError("Falta configurar la clave de integración de Universo en el servidor.")

    def get(self, path, **params):
        url = urljoin(self.base, path)
        parsed, origin = urlparse(url), urlparse(self.base)
        if (parsed.scheme, parsed.netloc) != (origin.scheme, origin.netloc) or not parsed.path.startswith(origin.path):
            raise UniversoError("Universo devolvió una dirección de paginación no permitida.")
        if params:
            url += ("&" if parsed.query else "?") + urlencode(params)
        request = Request(url, headers={"Authorization": "Bearer " + settings.UNIVERSO_API_KEY,
                                       "Accept": "application/json", "User-Agent": "EDH-Universo/1"})
        try:
            with build_opener(NoRedirect()).open(request, timeout=settings.UNIVERSO_TIMEOUT) as response:
                content = response.read(8 * 1024 * 1024 + 1)
            if len(content) > 8 * 1024 * 1024:
                raise UniversoError("La respuesta de Universo supera el tamaño permitido.")
            result = json.loads(content)
            if not isinstance(result, dict):
                raise UniversoError("Universo devolvió un formato inesperado.")
            return result
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise UniversoError("Universo rechazó la clave o el acceso de integración.") from None
            raise UniversoError(f"Universo respondió con error HTTP {exc.code}.") from None
        except (URLError, TimeoutError, OSError):
            raise UniversoError("No se pudo conectar con Universo. Se conserva el catálogo anterior.") from None
        except (ValueError, UnicodeError):
            raise UniversoError("Universo devolvió una respuesta inválida.") from None


def save_piece(payload, customers):
    try:
        part_id = uuid.UUID(str(payload["id"]))
        number = payload["part_number"]
        version = payload["version"]
        active = payload["active"]
        if not isinstance(number, str) or not number.strip() or len(number) > 160:
            raise ValueError
        if type(version) is not int or version < 1 or type(active) is not bool:
            raise ValueError
        customer = payload.get("customer") or customers.get(str(payload.get("customer_id")))
        if not isinstance(customer, str) or not customer.strip() or len(customer) > 160:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise UniversoError("Una pieza de Universo no tiene identificación, cliente o versión válidos.") from None
    existing = UniversoPart.objects.filter(pk=part_id).first()
    if existing and existing.version > version:
        return
    UniversoPart.objects.update_or_create(pk=part_id, defaults={
        "part_number": number, "normalized_number": normalize(number), "customer": customer,
        "active": active, "version": version, "data": payload, "synced_at": timezone.now()})


@transaction.atomic
def link_matching_routes():
    """Match by exact code/customer, then by a unique central part number."""
    index = {}
    numbers = {}
    for piece in UniversoPart.objects.filter(active=True):
        index.setdefault((piece.normalized_number, normalize(piece.customer)), []).append(piece)
        numbers.setdefault(piece.normalized_number, []).append(piece)
    linked = 0
    for route in Route.objects.filter(universe_part__isnull=True, universe_auto_link=True).exclude(status=Route.ARCHIVED).select_related("client"):
        matches = index.get((normalize(route.code), normalize(route.client.name)), [])
        method = "exact_code_and_customer"
        if not matches:
            matches = numbers.get(normalize(route.code), [])
            method = "unique_part_number"
        if len(matches) == 1:
            # Compare-and-set also protects a simultaneous manual link.
            if Route.objects.filter(pk=route.pk, universe_part__isnull=True, universe_auto_link=True).update(
                    universe_part=matches[0], version=F("version") + 1, updated_at=timezone.now()):
                RouteChange.objects.create(route=route, action="universe_link", after={"universe_part": str(matches[0].pk), "method": method})
                linked += 1
    return linked


def sync_universo():
    api = UniversoAPI()
    token = uuid.uuid4()
    with transaction.atomic():
        UniversoSync.objects.get_or_create(key="catalog")
        state = UniversoSync.objects.select_for_update().get(key="catalog")
        if state.lease_until and state.lease_until > timezone.now():
            raise UniversoError("La sincronización ya está en curso. Inténtalo de nuevo en unos momentos.")
        state.lease, state.lease_until = token, timezone.now() + timedelta(minutes=3)
        state.save(update_fields=["lease", "lease_until"])
    try:
        catalogs = api.get("catalogs/")
        customers = {str(row["id"]): row["name"] for row in catalogs["customers"]}
        if not state.cursor:
            bootstrap = api.get("bootstrap/")
            seed = bootstrap["changes_cursor"]
            if not isinstance(seed, str) or not seed:
                raise UniversoError("Universo no devolvió un cursor inicial válido.")
            page, snapshot, seen = "parts/?page_size=200", [], set()
            while page:
                if page in seen or len(snapshot) > 100000:
                    raise UniversoError("La paginación de Universo no terminó correctamente.")
                seen.add(page)
                result = api.get(page)
                snapshot.extend(result["results"])
                page = result["next"]
                renew_lease(token)
            with transaction.atomic():
                check_lease(token)
                for payload in snapshot:
                    save_piece(payload, customers)
                UniversoSync.objects.filter(pk="catalog").update(cursor=seed)
            state.cursor = seed
        pages = 0
        while True:
            result = api.get("changes/", cursor=state.cursor, limit=200)
            events = result["results"]
            cursor = result["next_cursor"]
            if not isinstance(events, list) or not isinstance(cursor, str) or not cursor:
                raise UniversoError("Universo devolvió cambios o cursor inválidos.")
            # Catalog listings omit inactive customers. Resolve their names through
            # the detail endpoint, without replacing the historical event image.
            for event in events:
                payload = event["part"]
                if str(payload.get("id")) != str(event["part_id"]):
                    raise UniversoError("La identificación del evento no coincide con su pieza.")
                customer_id = str(payload.get("customer_id"))
                if not payload.get("customer") and customer_id not in customers:
                    detail = api.get(f"parts/{uuid.UUID(str(event['part_id']))}/")
                    customers[customer_id] = detail["customer"]
            with transaction.atomic():
                check_lease(token)
                for event in events:
                    save_piece(event["part"], customers)
                UniversoSync.objects.filter(pk="catalog").update(cursor=cursor)
            state.cursor = cursor
            pages += 1
            renew_lease(token)
            if not result["has_more"]:
                break
            if not events or pages >= 1000:
                raise UniversoError("La sincronización alcanzó su límite; continuará desde el último cambio guardado.")
        with transaction.atomic():
            check_lease(token)
            linked = link_matching_routes()
            UniversoSync.objects.filter(pk="catalog", lease=token).update(
                initialized=True, last_success=timezone.now(), last_error="", lease=None, lease_until=None)
        return {"parts": UniversoPart.objects.count(), "linked": linked}
    except Exception as exc:
        message = str(exc) if isinstance(exc, UniversoError) else "No se pudo completar la sincronización; se conserva el último cursor confirmado."
        UniversoSync.objects.filter(pk="catalog", lease=token).update(last_error=message, lease=None, lease_until=None)
        raise UniversoError(message) from None


def check_lease(token):
    state = UniversoSync.objects.select_for_update().get(pk="catalog")
    if state.lease != token:
        raise UniversoError("Otra sincronización tomó el control. Vuelve a intentarlo.")


def renew_lease(token):
    updated = UniversoSync.objects.filter(pk="catalog", lease=token).update(lease_until=timezone.now() + timedelta(minutes=3))
    if not updated:
        raise UniversoError("La sincronización perdió su turno. Vuelve a intentarlo.")

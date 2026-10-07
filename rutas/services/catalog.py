from django.db.models import Exists, OuterRef, Q
from django.db.models.functions import Trim, Upper
from types import SimpleNamespace

from rutas.models import BOMItem, Route, UniversoPart
from rutas.services.universo import normalize


def pieces_without_routes():
    existing = Route.objects.annotate(normalized_code=Upper(Trim("code"))).filter(
        Q(universe_part_id=OuterRef("pk")) | Q(normalized_code=OuterRef("normalized_number")))
    return UniversoPart.objects.filter(active=True).annotate(has_route=Exists(existing)).filter(has_route=False)


def piece_has_route(piece):
    return Route.objects.annotate(normalized_code=Upper(Trim("code"))).filter(
        Q(universe_part=piece) | Q(normalized_code=piece.normalized_number)).exists()


def parent_routes():
    """Show central pieces, including exact codes still awaiting customer mapping.

    Children remain available by ID and to the BOM/printing services. A linked
    UUID keeps its identity if the central number changes.
    """
    central = UniversoPart.objects.filter(active=True, normalized_number=Upper(Trim(OuterRef("code"))))
    component = BOMItem.objects.filter(component_route_id=OuterRef("pk"))
    return Route.objects.annotate(is_universe_number=Exists(central), is_component_route=Exists(component)).filter(
        Q(universe_part__active=True) | Q(universe_part__isnull=True, is_universe_number=True)
    ).filter(is_component_route=False).exclude(part__part_type="RM", part__used_in__isnull=False)


def group_routes(routes):
    groups = {}
    for route in routes:
        key = normalize(route.code)
        groups.setdefault(key, []).append(route)
    result = []
    for key, variants in groups.items():
        first = variants[0]
        result.append(SimpleNamespace(pk=first.pk, code=first.code.strip(), normalized_code=key,
            description=next((r.description for r in variants if r.description), ""),
            clients=" · ".join(sorted({r.client.name for r in variants})),
            origins=" · ".join(sorted({r.classification or "Captura web" for r in variants})),
            variants=variants, variant_count=len(variants),
            active_count=sum(r.status == Route.ACTIVE for r in variants),
            review_count=sum(r.status == Route.REVIEW for r in variants),
            archived_count=sum(r.status == Route.ARCHIVED for r in variants)))
    return result

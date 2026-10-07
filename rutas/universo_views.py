from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from rutas.models import Route, RouteChange, UniversoPart, UniversoSync
from rutas.services.universo import UniversoError, normalize, sync_universo
from rutas.services.catalog import parent_routes, piece_has_route


def coverage_parts():
    return UniversoPart.objects.annotate(
        active_routes=Count("routes", filter=Q(routes__status=Route.ACTIVE)),
        review_routes=Count("routes", filter=Q(routes__status=Route.REVIEW)),
        archived_routes=Count("routes", filter=Q(routes__status=Route.ARCHIVED)))


@login_required
@permission_required("rutas.view_route", raise_exception=True)
def coverage(request):
    pieces = coverage_parts()
    active = pieces.filter(active=True)
    stats = {"total": active.count(), "covered": active.filter(active_routes__gt=0).count(),
             "review": active.filter(active_routes=0, review_routes__gt=0).count(),
             "missing": active.filter(active_routes=0, review_routes=0).count()}
    stats["percent"] = round(stats["covered"] * 100 / stats["total"]) if stats["total"] else 0
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    customer = request.GET.get("customer", "")
    if status == "inactive":
        pieces = pieces.filter(active=False)
    else:
        pieces = pieces.filter(active=True)
        if status == "missing":
            pieces = pieces.filter(active_routes=0, review_routes=0)
        elif status == "review":
            pieces = pieces.filter(active_routes=0, review_routes__gt=0)
        elif status == "available":
            pieces = pieces.filter(Q(active_routes__gt=0) | Q(review_routes__gt=0))
        elif status == "covered":
            pieces = pieces.filter(active_routes__gt=0)
    if query:
        pieces = pieces.filter(Q(part_number__icontains=query) | Q(customer__icontains=query))
    if customer:
        pieces = pieces.filter(customer=customer)
    all_unlinked = Route.objects.filter(universe_part__isnull=True).exclude(status=Route.ARCHIVED)
    unlinked = parent_routes().filter(universe_part__isnull=True).exclude(status=Route.ARCHIVED).select_related("client")
    outside_universe_count = all_unlinked.exclude(pk__in=unlinked.values("pk")).count()
    if query:
        unlinked = unlinked.filter(Q(code__icontains=query) | Q(client__name__icontains=query))
    unlinked_count = unlinked.count()
    unlinked_page = Paginator(unlinked.order_by("code", "id"), 15).get_page(request.GET.get("routes_page"))
    return render(request, "rutas/universo/coverage.html", {
        "page": Paginator(pieces.order_by("part_number", "id"), 30).get_page(request.GET.get("page")),
        "stats": stats, "query": query, "status": status, "customer": customer,
        "customers": UniversoPart.objects.order_by("customer").values_list("customer", flat=True).distinct(),
        "state": UniversoSync.objects.filter(pk="catalog").first(),
        "configured": bool(settings.UNIVERSO_API_KEY), "unlinked": unlinked_page, "unlinked_count": unlinked_count,
        "outside_universe_count": outside_universe_count})


@login_required
@permission_required("rutas.view_route", raise_exception=True)
def piece_detail(request, pk):
    piece = get_object_or_404(UniversoPart, pk=pk)
    candidates = [route for route in Route.objects.filter(universe_part__isnull=True).select_related("client").order_by("code", "id")
                  if normalize(route.code) == piece.normalized_number]
    routes = list(piece.routes.select_related("client").order_by("status", "id"))
    for route in routes:
        route.universe_mismatch = normalize(route.code) != piece.normalized_number or normalize(route.client.name) != normalize(piece.customer)
    return render(request, "rutas/universo/detail.html", {"piece": piece,
        "routes": routes, "candidates": candidates, "can_create_route": piece.active and not piece_has_route(piece)})


@login_required
@permission_required("rutas.change_route", raise_exception=True)
@require_POST
def sync(request):
    try:
        result = sync_universo()
        messages.success(request, f"Catálogo actualizado: {result['parts']} piezas; {result['linked']} rutas vinculadas por código y cliente.")
    except UniversoError as exc:
        messages.error(request, str(exc))
    return redirect("rutas:universe")


@login_required
@permission_required("rutas.change_route", raise_exception=True)
def link_route(request, pk):
    route = get_object_or_404(Route.objects.select_related("client", "universe_part"), pk=pk)
    query = request.GET.get("q", route.code).strip()
    pieces = UniversoPart.objects.filter(active=True)
    if query:
        pieces = pieces.filter(Q(part_number__icontains=query) | Q(customer__icontains=query))
    if request.method == "POST":
        with transaction.atomic():
            route = Route.objects.select_for_update().get(pk=pk)
            piece = get_object_or_404(UniversoPart, pk=request.POST.get("piece_id"), active=True)
            if request.POST.get("confirm") != "yes":
                messages.error(request, "Confirma que la pieza seleccionada corresponde a esta ruta.")
            else:
                previous = str(route.universe_part_id) if route.universe_part_id else None
                route.universe_part = piece
                route.universe_auto_link = True
                route.version += 1
                route.save(update_fields=["universe_part", "universe_auto_link", "version", "updated_at"])
                RouteChange.objects.create(route=route, user=request.user, action="universe_link",
                    before={"universe_part": previous}, after={"universe_part": str(piece.pk), "method": "manual"})
                messages.success(request, "Ruta vinculada. Se conservaron sus datos y operaciones.")
                return redirect("rutas:universe_detail", pk=piece.pk)
    return render(request, "rutas/universo/link.html", {"route": route, "query": query,
        "page": Paginator(pieces, 20).get_page(request.GET.get("page"))})


@login_required
@permission_required("rutas.change_route", raise_exception=True)
@require_POST
def unlink_route(request, pk):
    with transaction.atomic():
        route = get_object_or_404(Route.objects.select_for_update(), pk=pk)
        previous = str(route.universe_part_id) if route.universe_part_id else None
        route.universe_part = None
        route.universe_auto_link = False
        route.version += 1
        route.save(update_fields=["universe_part", "universe_auto_link", "version", "updated_at"])
        RouteChange.objects.create(route=route, user=request.user, action="universe_unlink", before={"universe_part": previous})
    messages.success(request, "Vínculo retirado. La ruta se conserva y no volverá a vincularse automáticamente; puedes elegir su pieza manualmente.")
    return redirect("rutas:detail", pk=pk)

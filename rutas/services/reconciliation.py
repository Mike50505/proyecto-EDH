from collections import defaultdict
from django.db import transaction
from rutas.models import ImportIssue, ImportRun, Part, Route, RouteChange


def operation_signature(route):
    return tuple((op.source_sequence, op.name, op.tooling, op.inspection, op.machine) for op in route.operations.all())


def reconcile_all():
    """Report cross-book differences and missing FP routes without merging data."""
    stats = {"crossbook_conflicts": 0, "missing_fp_routes": 0}
    routes = list(Route.objects.filter(source__isnull=False).select_related("source").prefetch_related("operations"))
    groups = defaultdict(list)
    for route in routes:
        groups[(route.client_id, route.code)].append(route)
    issues = []
    affected = set()
    for (_, code), variants in groups.items():
        if len({route.source_id for route in variants}) < 2:
            continue
        signatures = {operation_signature(route) for route in variants}
        if len(signatures) == 1:
            continue
        for route in variants:
            run = ImportRun.objects.filter(source=route.source, dry_run=False).order_by("id").first()
            if not run or ImportIssue.objects.filter(run=run, sheet="Ruta", row=route.source_row, kind="diferencia_entre_libros").exists():
                continue
            peers = ", ".join(f"{x.source.classification} fila {x.source_row}" for x in variants if x.pk != route.pk)
            issues.append(ImportIssue(run=run, sheet="Ruta", row=route.source_row, code=code, kind="diferencia_entre_libros",
                                      detail=f"El mismo código tiene operaciones o recursos diferentes en {peers}. No se fusionó."))
            affected.add(route.pk)
            stats["crossbook_conflicts"] += 1
    for part in Part.objects.filter(source__isnull=False, part_type="FP").select_related("source"):
        if Route.objects.filter(source=part.source, code=part.code).exists():
            continue
        run = ImportRun.objects.filter(source=part.source, dry_run=False).order_by("id").first()
        if not run or ImportIssue.objects.filter(run=run, sheet="Familias", row=part.source_row, kind="fp_sin_ruta").exists():
            continue
        other = list(Route.objects.filter(code=part.code).exclude(source=part.source).values_list("source__classification", flat=True).distinct())
        detail = "FP sin código equivalente en Ruta del mismo libro."
        if other:
            detail += " Coincide en otra variante: " + ", ".join(other) + ". No se trasladó automáticamente."
        issues.append(ImportIssue(run=run, sheet="Familias", row=part.source_row, code=part.code, kind="fp_sin_ruta", detail=detail))
        stats["missing_fp_routes"] += 1
    with transaction.atomic():
        ImportIssue.objects.bulk_create(issues)
        RouteChange.objects.bulk_create([RouteChange(route_id=route.pk, action="reconcile", before={"status": route.status}, after={"status": Route.REVIEW})
            for route in routes if route.pk in affected and route.status != Route.REVIEW])
        Route.objects.filter(pk__in=affected).update(status=Route.REVIEW)
    return stats

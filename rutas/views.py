import json
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from rutas.forms import FamilyForm, ImportForm, OperationFormSet, RouteForm, ScheduleForm, ScheduleLineFormSet
from rutas.models import Client, ImportIssue, ImportRun, IssuedDocument, Operation, Part, Route, RouteChange, Schedule, ScheduleLine
from rutas.services.documents import issue_schedule, make_label, render_pdf
from rutas.services.batch_selection import blank_rows, build_pdf, read_excel, rows_from_post
from rutas.services.importer import ImportErrorDetailed, import_workbook
from rutas.services.source_catalog import CLIENT_VARIANTS


def route_data(route):
    return {"code": route.code, "description": route.description, "classification": route.classification,
            "revision": route.revision, "status": route.status,
            "operations": list(route.operations.order_by("position").values("position", "source_sequence", "name", "machine", "tooling", "inspection"))}


def replace_operations(route, formset):
    values = [data for data in formset.cleaned_data if data and not data.get("DELETE") and data.get("name")]
    route.operations.all().delete()
    Operation.objects.bulk_create([Operation(route=route, position=data["position"], source_sequence=data.get("source_sequence", ""),
        name=data["name"], machine=data.get("machine", ""), tooling=data.get("tooling", ""), inspection=data.get("inspection", ""))
        for data in values])


@login_required
def route_list(request):
    query = request.GET.get("q", "").strip()
    client_name = request.GET.get("client", "DAIKIN")
    status = request.GET.get("status", "")
    classification = request.GET.get("classification", "")
    if client_name and classification and not Route.objects.filter(client__name=client_name, classification=classification).exists():
        classification = ""
    routes = Route.objects.select_related("client", "part").all()
    if client_name:
        routes = routes.filter(client__name=client_name)
    if query:
        routes = routes.filter(Q(code__icontains=query) | Q(description__icontains=query) | Q(part__drawing_number__icontains=query))
    if status in dict(Route.STATUS):
        routes = routes.filter(status=status)
    if classification:
        routes = routes.filter(classification=classification)
    ordering = request.GET.get("order", "code")
    if ordering not in {"code", "-code", "updated_at", "-updated_at"}:
        ordering = "code"
    page = Paginator(routes.order_by(ordering, "id"), 30).get_page(request.GET.get("page"))
    classes = Route.objects.filter(client__name=client_name) if client_name else Route.objects.all()
    return render(request, "rutas/list.html", {"page": page, "query": query, "status": status,
        "client_name": client_name, "clients": Client.objects.order_by("name"),
        "classification": classification, "order": ordering,
        "classifications": classes.order_by("classification").values_list("classification", flat=True).distinct()})


@login_required
@permission_required("rutas.add_schedule", raise_exception=True)
@require_POST
def route_select(request):
    scope = request.POST.get("scope")
    client_name = request.POST.get("client", "DAIKIN")
    if scope == "all":
        if not client_name:
            messages.error(request, "Elige un cliente antes de llevar todas las rutas del filtro.")
            return redirect("rutas:list")
        routes = Route.objects.filter(status=Route.ACTIVE)
        routes = routes.filter(client__name=client_name)
        query = request.POST.get("q", "").strip()
        classification = request.POST.get("classification", "")
        status = request.POST.get("status", "")
        if status and status != Route.ACTIVE:
            routes = routes.none()
        if query:
            routes = routes.filter(Q(code__icontains=query) | Q(description__icontains=query) | Q(part__drawing_number__icontains=query))
        if classification:
            routes = routes.filter(classification=classification)
        ids = list(routes.order_by("code", "id").values_list("id", flat=True)[:201])
        if len(ids) > 200:
            messages.error(request, "El filtro contiene más de 200 rutas activas. Acota la búsqueda antes de preparar el lote.")
            return redirect("rutas:list")
    else:
        try:
            ids = [int(x) for x in request.POST.getlist("route_ids")]
        except ValueError:
            return HttpResponseBadRequest("Selección inválida")
        valid = set(Route.objects.filter(pk__in=ids, status=Route.ACTIVE).values_list("id", flat=True))
        ids = [pk for pk in ids if pk in valid]
    if not ids:
        messages.error(request, "Selecciona al menos una ruta activa.")
        return redirect("rutas:list")
    if Route.objects.filter(pk__in=ids).values("client_id").distinct().count() != 1:
        messages.error(request, "Selecciona rutas de un solo cliente por programación.")
        return redirect("rutas:list")
    selected = {route.pk: route for route in Route.objects.filter(pk__in=ids).select_related("client", "part")}
    rows = blank_rows(max(12, len(ids)))
    for index, route_id in enumerate(ids):
        route = selected[route_id]
        rows[index].update(parent_code=route.code, sequence=str(index + 1),
                           re=str(route.part.components.filter(component__part_type="RM").count()) if route.part_id else "0")
    origins = {selected[pk].classification for pk in ids}
    return render_batch_page(request, rows, [], origins.pop() if len(origins) == 1 else "", client_name=selected[ids[0]].client.name)


@login_required
def route_detail(request, pk):
    route = get_object_or_404(Route.objects.select_related("client", "part", "source").prefetch_related("operations", "history__user"), pk=pk)
    issues = ImportIssue.objects.filter(run__source=route.source, sheet="Ruta", row=route.source_row) if route.source_id else ImportIssue.objects.none()
    return render(request, "rutas/detail.html", {"route": route, "issues": issues})


@login_required
@permission_required("rutas.view_route", raise_exception=True)
def route_print(request, pk):
    """Printable route preview without creating an issued production document."""
    route = get_object_or_404(Route.objects.select_related("client", "part").prefetch_related("operations"), pk=pk)
    line = SimpleNamespace(shop_order="—", position=1)
    label = make_label(route, route, route.part, line, Decimal("0"), 1, 1)
    label["quantity"] = "—"
    snapshot = {
        "client": route.client.name, "week": "—", "line": "—", "copies": 1,
        "planner": "—", "responsible": "—", "issue_date": timezone.localdate().isoformat(),
        "ship_date": "", "lines": [], "labels": [label],
        "preview_status": "VISTA PREVIA · NO PRODUCCIÓN" if route.status == Route.ACTIVE else "RUTA SIN APROBAR · NO PRODUCCIÓN",
    }
    response = FileResponse(BytesIO(render_pdf(snapshot)), content_type="application/pdf", as_attachment=False,
                            filename=f"ruta-{route.pk}-vista-previa.pdf")
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
@permission_required("rutas.add_schedule", raise_exception=True)
def batch_print(request):
    """Spreadsheet-shaped order selection; neither upload nor PDF creates rows."""
    rows = blank_rows()
    errors = []
    notice = ""
    client_name = request.POST.get("client", "DAIKIN") if request.method == "POST" else request.GET.get("client", "DAIKIN")
    classification = request.POST.get("classification", "") if request.method == "POST" else request.GET.get("classification", "Headers" if client_name == "DAIKIN" else "")
    if not Client.objects.filter(name=client_name).exists():
        errors.append("Selecciona un cliente disponible.")
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "upload":
                if "workbook" not in request.FILES:
                    raise ValueError("Selecciona un archivo Excel.")
                rows = read_excel(request.FILES["workbook"])
                for field in ("line", "planner", "responsible"):
                    rows[0][field] = request.POST.get(f"common_{field}", "").strip() or rows[0][field]
                notice = f"Se cargaron {len(rows)} órdenes en la tabla. Revisa las celdas antes de crear el PDF."
            elif action == "print":
                if not request.user.has_perm("rutas.add_issueddocument"):
                    raise PermissionDenied
                rows = rows_from_post(request.POST)
                if errors:
                    raise ValueError("\n".join(errors))
                pdf = build_pdf(rows, classification, client_name)
                response = FileResponse(BytesIO(pdf), content_type="application/pdf", as_attachment=False,
                                        filename="ordenes-seleccionadas.pdf")
                response["Cache-Control"] = "private, no-store"
                return response
            else:
                raise ValueError("Acción desconocida.")
        except ValueError as exc:
            errors = str(exc).splitlines()
            if action == "print":
                try:
                    submitted_count = min(max(int(request.POST.get("row_count", 0) or 0), 0), 200)
                except (TypeError, ValueError):
                    submitted_count = 0
                rows = [
                    {field: request.POST.get(f"rows-{index}-{field}", "") for field in
                     ("shop_order", "parent_code", "quantity", "week", "re", "sequence", "line", "planner", "responsible")}
                    for index in range(submitted_count)
                ] or blank_rows()
                for index, row in enumerate(rows, 1):
                    row["shop_order"] = row["week"]
                    row["sequence"] = str(index)
                for field in ("line", "planner", "responsible"):
                    rows[0][field] = request.POST.get(f"common_{field}", "").strip()
    return render_batch_page(request, rows, errors, classification, notice, client_name)


def render_batch_page(request, rows, errors, classification, notice="", client_name="DAIKIN"):
    route_catalog = {}
    route_values = Route.objects.exclude(status=Route.ARCHIVED).exclude(code="").annotate(
        rm_count=Count("part__components", filter=Q(part__components__component__part_type="RM"))
    ).order_by("source_row", "id").values_list("client__name", "classification", "code", "rm_count")
    for client, variant, code, count in route_values:
        route_catalog.setdefault(client, {}).setdefault(variant, {}).setdefault(code, count)
    client_routes = route_catalog.get(client_name, {})
    classifications = sorted(variant for variant in client_routes if variant)
    selected_routes = {code: count for codes in client_routes.values() for code, count in codes.items()} if not classification else {
        **client_routes.get("", {}), **client_routes.get(classification, {})}
    parent_codes = sorted(selected_routes, key=str.casefold)
    re_map = {code.upper(): count for code, count in selected_routes.items()}
    warnings = []
    for index, row in enumerate(rows, 1):
        code = row.get("parent_code", "").strip()
        if not code:
            continue
        candidates = Route.objects.filter(code__iexact=code, client__name=client_name)
        if classification:
            candidates = candidates.filter(classification=classification)
        if candidates.exists() and not candidates.filter(status=Route.ACTIVE).exists():
            warnings.append(f"Fila {index + 1}: {code} está Por revisar. El PDF será una vista previa no aprobada.")
    return render(request, "rutas/batch_print.html", {"rows": rows, "errors": errors, "classification": classification,
        "classifications": classifications, "client_name": client_name, "clients": Client.objects.order_by("name"),
        "parent_codes": parent_codes, "route_catalog": route_catalog,
        "re_map": re_map, "notice": notice, "warnings": warnings})


@login_required
@permission_required("rutas.add_schedule", raise_exception=True)
def batch_template(request):
    template = Path(settings.BASE_DIR) / "static" / "templates" / "ordenes_impresion.xlsx"
    return FileResponse(template.open("rb"), as_attachment=True, filename="plantilla_ordenes_impresion.xlsx",
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@login_required
@permission_required("rutas.add_route", raise_exception=True)
def route_create(request):
    route = Route(status=Route.REVIEW)
    route_data_post = request.POST.copy() if request.method == "POST" else None
    if route_data_post is not None:
        route_data_post["code"] = route_data_post.get("family-code", "").strip()
        route_data_post["description"] = route_data_post.get("family-description", "").strip()
        route_data_post["part"] = ""
    form = RouteForm(route_data_post, instance=route)
    family_form = FamilyForm(request.POST or None, prefix="family")
    formset = OperationFormSet(request.POST or None, instance=route)
    if request.method == "POST" and all((form.is_valid(), family_form.is_valid(), formset.is_valid())):
        with transaction.atomic():
            part = family_form.save(commit=False)
            part.client = form.cleaned_data["client"]
            part.save()
            route = form.save(commit=False)
            route.part = part
            route.code = part.code
            route.description = part.description
            route.save()
            replace_operations(route, formset)
            RouteChange.objects.create(route=route, user=request.user, action="create", after=route_data(route))
        messages.success(request, "Ruta creada.")
        return redirect("rutas:detail", pk=route.pk)
    return render(request, "rutas/edit.html", {"form": form, "family_form": family_form,
                                               "formset": formset, "title": "Nueva ruta"})


@login_required
@permission_required("rutas.change_route", raise_exception=True)
def route_edit(request, pk):
    route = get_object_or_404(Route, pk=pk)
    form = RouteForm(request.POST or None, instance=route)
    formset = OperationFormSet(request.POST or None, instance=route)
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            locked = Route.objects.select_for_update().get(pk=pk)
            if form.cleaned_data["version"] != locked.version:
                form.add_error(None, "Otra persona modificó esta ruta. Recargue para revisar los cambios.")
            else:
                before = route_data(locked)
                updated = form.save(commit=False)
                updated.version = locked.version + 1
                updated.save()
                replace_operations(updated, formset)
                RouteChange.objects.create(route=updated, user=request.user, action="edit", before=before, after=route_data(updated))
                messages.success(request, "Ruta actualizada.")
                return redirect("rutas:detail", pk=pk)
    return render(request, "rutas/edit.html", {"form": form, "formset": formset, "route": route, "title": "Editar ruta"})


@login_required
@permission_required("rutas.add_route", raise_exception=True)
@require_POST
def route_duplicate(request, pk):
    original = get_object_or_404(Route.objects.prefetch_related("operations"), pk=pk)
    with transaction.atomic():
        duplicate = Route.objects.create(client=original.client, part=original.part, code=original.code,
            description=original.description, classification=original.classification, revision=original.revision,
            status=Route.REVIEW)
        Operation.objects.bulk_create([Operation(route=duplicate, position=op.position, source_sequence=op.source_sequence,
            name=op.name, machine=op.machine, tooling=op.tooling, inspection=op.inspection)
            for op in original.operations.all()])
        RouteChange.objects.create(route=duplicate, user=request.user, action="duplicate", after=route_data(duplicate))
    return redirect("rutas:edit", pk=duplicate.pk)


@login_required
@permission_required("rutas.change_route", raise_exception=True)
@require_POST
def route_archive(request, pk):
    with transaction.atomic():
        route = get_object_or_404(Route.objects.select_for_update(), pk=pk)
        before = route_data(route)
        route.status = Route.ARCHIVED
        route.version += 1
        route.save()
        RouteChange.objects.create(route=route, user=request.user, action="archive", before=before, after=route_data(route))
    return redirect("rutas:detail", pk=pk)


@login_required
@permission_required("rutas.add_schedule", raise_exception=True)
def schedule_create(request):
    if request.method == "POST" and request.POST.get("action") == "print_all" and not request.user.has_perm("rutas.add_issueddocument"):
        raise PermissionDenied
    schedule = Schedule(created_by=request.user)
    selected = list(Route.objects.filter(pk__in=request.session.get("selected_route_ids", [])).order_by("code", "id")) if request.method == "GET" else []
    form = ScheduleForm(request.POST or None, instance=schedule, initial={"client": selected[0].client_id} if selected else None)
    initial_lines = [{"position": i, "route": route.pk} for i, route in enumerate(selected, 1)]
    formset = ScheduleLineFormSet(request.POST or None, instance=schedule, initial=initial_lines)
    re_counts = dict(Route.objects.annotate(
        rm_count=Count("part__components", filter=Q(part__components__component__part_type="RM"))
    ).values_list("pk", "rm_count"))
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        lines = [data for data in formset.cleaned_data if data and not data.get("DELETE") and data.get("route")]
        if not lines:
            form.add_error(None, "Agregue al menos una partida.")
        elif any(data["route"].client_id != form.cleaned_data["client"].pk for data in lines):
            form.add_error(None, "Todas las rutas deben pertenecer al cliente seleccionado.")
        else:
            with transaction.atomic():
                schedule = form.save()
                for data in lines:
                    schedule.lines.create(route=data["route"], shop_order=data["shop_order"], quantity=data["quantity"], position=data["position"])
            request.session.pop("selected_route_ids", None)
            if request.POST.get("action") == "print_all":
                try:
                    document = issue_schedule(schedule, request.user)
                except ValueError as exc:
                    messages.error(request, str(exc))
                    return redirect("rutas:schedule_detail", pk=schedule.pk)
                return redirect("rutas:document", pk=document.pk)
            return redirect("rutas:schedule_detail", pk=schedule.pk)
    return render(request, "rutas/schedule_edit.html", {"form": form, "formset": formset, "re_counts": re_counts})


@login_required
def schedule_detail(request, pk):
    schedule = get_object_or_404(Schedule.objects.select_related("client").prefetch_related("lines__route", "issueddocument_set"), pk=pk)
    previews = []
    for line in schedule.lines.all():
        components = []
        re_count = 0
        if line.route.part_id:
            components = [(x.component.code, x.quantity_per, line.quantity * x.quantity_per) for x in line.route.part.components.select_related("component")]
            re_count = line.route.part.components.filter(component__part_type="RM").count()
        previews.append((line, components, re_count))
    return render(request, "rutas/schedule_detail.html", {"schedule": schedule, "previews": previews})


@login_required
@permission_required("rutas.add_issueddocument", raise_exception=True)
@require_POST
def schedule_issue(request, pk):
    schedule = get_object_or_404(Schedule, pk=pk)
    try:
        document = issue_schedule(schedule, request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("rutas:schedule_detail", pk=pk)
    return redirect("rutas:document", pk=document.pk)


@login_required
@permission_required("rutas.view_issueddocument", raise_exception=True)
def document_download(request, pk):
    document = get_object_or_404(IssuedDocument, pk=pk)
    if not document.downloaded_at:
        document.downloaded_at = timezone.now()
        document.save(update_fields=["downloaded_at"])
    return FileResponse(document.pdf.open("rb"), content_type="application/pdf", as_attachment=False, filename=f"ruta-{document.pk}.pdf")


@login_required
@permission_required("rutas.add_importrun", raise_exception=True)
def import_page(request):
    form = ImportForm(request.POST or None, request.FILES or None)
    run = None
    if request.method == "POST" and form.is_valid():
        try:
            run = import_workbook(form.cleaned_data["file"], form.cleaned_data["password"], form.cleaned_data["dry_run"],
                                  request.user, form.cleaned_data["client_name"], form.cleaned_data["classification"])
            messages.success(request, "Simulación terminada." if run.dry_run else "Importación terminada.")
        except ImportErrorDetailed as exc:
            form.add_error("file", str(exc))
    return render(request, "rutas/import.html", {"form": form, "run": run, "source_variants": CLIENT_VARIANTS})


@login_required
@permission_required("rutas.view_importrun", raise_exception=True)
def import_report(request, pk):
    run = get_object_or_404(ImportRun.objects.prefetch_related("issues"), pk=pk)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="importacion-{pk}.csv"'
    import csv
    writer = csv.writer(response)
    writer.writerow(["Hoja", "Fila", "Código", "Tipo", "Detalle", "Resuelto", "Decisión", "Fecha de resolución"])
    for issue in run.issues.all():
        writer.writerow([issue.sheet, issue.row, issue.code, issue.kind, issue.detail, issue.resolved, issue.resolution_note, issue.resolved_at])
    return response


@login_required
@permission_required("rutas.view_importissue", raise_exception=True)
def issue_list(request):
    kind = request.GET.get("kind", "")
    client_name = request.GET.get("client", "")
    issues = ImportIssue.objects.filter(resolved=False, run__dry_run=False).select_related("run__source", "run__source__client")
    if client_name:
        issues = issues.filter(Q(run__source__client__name=client_name) | Q(run__summary__client=client_name))
    if kind:
        issues = issues.filter(kind=kind)
    issues = issues.order_by("run__source__classification", "sheet", "row", "id")
    page = Paginator(issues, 30).get_page(request.GET.get("page"))
    keys = [(issue.run.source_id, issue.row) for issue in page if issue.sheet == "Ruta" and issue.run.source_id]
    linked = {(route.source_id, route.source_row): route for route in Route.objects.filter(source_id__in=[x[0] for x in keys], source_row__in=[x[1] for x in keys])}
    for issue in page:
        issue.linked_route = linked.get((issue.run.source_id, issue.row)) if issue.sheet == "Ruta" else None
    kinds = ImportIssue.objects.filter(run__dry_run=False).values_list("kind", flat=True).distinct().order_by("kind")
    return render(request, "rutas/issues.html", {"page": page, "kind": kind, "kinds": kinds,
                                                   "client_name": client_name, "clients": Client.objects.order_by("name")})


def issue_record(record):
    if isinstance(record, Route):
        return {"kind": "Ruta", "source": record.source, "row": record.source_row,
                "fields": [("Código", record.code), ("Descripción", record.description),
                           ("Clasificación", record.classification), ("Revisión", record.revision),
                           ("Estado", record.get_status_display())],
                "operations": list(record.operations.order_by("position", "id"))}
    return {"kind": "Familias", "source": record.source, "row": record.source_row,
            "fields": [("Tipo", record.part_type), ("Parte", record.code),
                       ("Descripción", record.description), ("BOM", record.bom_revision),
                       ("Dibujo rev", record.drawing_revision), ("Número dibujo", record.drawing_number),
                       ("Cantidad", record.quantity_raw), ("OD", record.od_raw),
                       ("Pared", record.wall_raw), ("Desarrollo", record.development_raw),
                       ("Comentario", record.comments), ("Fase", record.phase)], "operations": []}


@login_required
@permission_required("rutas.view_importissue", raise_exception=True)
def issue_detail(request, pk):
    issue = get_object_or_404(ImportIssue.objects.select_related("run__source", "run__source__client", "resolved_by"),
                              pk=pk, run__dry_run=False)
    source = issue.run.source
    record = None
    peers = []
    selected_peer = None
    if source and issue.sheet == "Ruta":
        record = Route.objects.filter(source=source, source_row=issue.row).select_related("source").prefetch_related("operations").first()
        if record:
            peers = list(Route.objects.filter(client=record.client, code=record.code).exclude(pk=record.pk)
                         .select_related("source").prefetch_related("operations").order_by("source__classification", "source_row", "pk"))
    elif source and issue.sheet == "Familias":
        record = Part.objects.filter(source=source, source_row=issue.row).select_related("source").first()
        if record:
            peers = list(Part.objects.filter(client=record.client, code=record.code).exclude(pk=record.pk)
                         .select_related("source").order_by("source__classification", "source_row", "pk"))
    if peers:
        selected_peer = next((peer for peer in peers if str(peer.pk) == request.GET.get("peer")), peers[0])
    return render(request, "rutas/issue_detail.html", {
        "issue": issue, "record": record, "left": issue_record(record) if record else None,
        "peers": peers, "selected_peer": selected_peer,
        "right": issue_record(selected_peer) if selected_peer else None,
    })


@login_required
@permission_required("rutas.change_importissue", raise_exception=True)
@require_POST
def issue_resolve(request, pk):
    note = request.POST.get("resolution_note", "").strip()
    if len(note) < 12:
        messages.error(request, "Describe la decisión con al menos 12 caracteres.")
        return redirect("rutas:issues")
    with transaction.atomic():
        issue = get_object_or_404(ImportIssue.objects.select_for_update(), pk=pk)
        if not issue.resolved:
            issue.resolved = True
            issue.resolution_note = note
            issue.resolved_at = timezone.now()
            issue.resolved_by = request.user
            issue.save(update_fields=["resolved", "resolution_note", "resolved_at", "resolved_by"])
    messages.success(request, "Incidencia resuelta. Revisa la ruta antes de activarla.")
    return redirect("rutas:issues")

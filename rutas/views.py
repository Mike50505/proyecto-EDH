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

from rutas.forms import FamilyForm, ImportForm, OperationFormSet, RouteForm, ScheduleForm, ScheduleLineFormSet, preset_operation_formset
from rutas.models import BOMItem, Client, ImportIssue, ImportRun, IssuedDocument, Operation, Part, Route, RouteChange, Schedule, ScheduleLine, UniversoPart
from rutas.services.documents import CLASSIC_TEMPLATE, LABEL_MODES, LABEL_MODE_COMPONENTS_ONLY, DEFAULT_LABEL_MODE, PRINT_TEMPLATES, issue_schedule, make_label, render_pdf, validate_print_template, preview_labels_for_line, uses_parent_operations
from rutas.services.batch_selection import blank_rows, build_pdf, read_excel, rows_from_post
from rutas.services.importer import ImportErrorDetailed, import_workbook
from rutas.services.source_catalog import CLIENT_VARIANTS
from rutas.services.catalog import parent_routes, group_routes, pieces_without_routes, piece_has_route
from rutas.services.component_editor import component_editor, validate_components, save_components, lock_component_versions, fork_part


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
    client_name = request.GET.get("client", "")
    status = request.GET.get("status", "")
    classification = request.GET.get("classification", "")
    parents = parent_routes()
    if client_name and classification and not parents.filter(client__name=client_name, classification=classification).exists():
        classification = ""
    routes = parents.select_related("client", "part")
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
    grouped = group_routes(routes.order_by(ordering, "id"))
    page = Paginator(grouped, 30).get_page(request.GET.get("page"))
    classes = parents.filter(client__name=client_name) if client_name else parents
    return render(request, "rutas/list.html", {"page": page, "query": query, "status": status,
        "client_name": client_name, "clients": Client.objects.order_by("name"),
        "classification": classification, "order": ordering,
        "classifications": classes.order_by("classification").values_list("classification", flat=True).distinct()})


@login_required
@permission_required("rutas.add_schedule", raise_exception=True)
@require_POST
def route_select(request):
    scope = request.POST.get("scope")
    client_name = request.POST.get("client", "")
    if scope == "all":
        routes = parent_routes().filter(status=Route.ACTIVE)
        if client_name:
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
        selected_groups = group_routes(routes.select_related("client").order_by("code", "id"))
        if len(selected_groups) > 200:
            messages.error(request, "El filtro contiene más de 200 piezas padre. Acota la búsqueda antes de preparar el lote.")
            return redirect("rutas:list")
    elif request.POST.getlist("group_ids"):
        try:
            group_ids = [int(x) for x in request.POST.getlist("group_ids")]
        except ValueError:
            return HttpResponseBadRequest("Selección inválida")
        from rutas.services.universo import normalize
        selected_codes = {normalize(code) for code in parent_routes().filter(pk__in=group_ids).values_list("code", flat=True)}
        routes = parent_routes().filter(status=Route.ACTIVE)
        if client_name:
            routes = routes.filter(client__name=client_name)
        if request.POST.get("classification"):
            routes = routes.filter(classification=request.POST["classification"])
        selected_groups = [group for group in group_routes(routes.select_related("client").order_by("code", "id"))
                           if group.normalized_code in selected_codes]
    else:
        try:
            ids = [int(x) for x in request.POST.getlist("route_ids")]
        except ValueError:
            return HttpResponseBadRequest("Selección inválida")
        valid = set(parent_routes().filter(pk__in=ids, status=Route.ACTIVE).values_list("id", flat=True))
        ids = [pk for pk in ids if pk in valid]
        selected_groups = group_routes(Route.objects.filter(pk__in=ids).select_related("client").order_by("code", "id"))
    if not selected_groups:
        messages.error(request, "Selecciona al menos una ruta activa.")
        return redirect("rutas:list")
    if len(selected_groups) > 200:
        messages.error(request, "Selecciona hasta 200 piezas padre.")
        return redirect("rutas:list")
    rows = blank_rows(max(12, len(selected_groups)))
    for index, group in enumerate(selected_groups):
        # An origin must be chosen explicitly when several active variants exist.
        route_id = str(group.variants[0].pk) if group.variant_count == 1 else ""
        rows[index].update(parent_code=group.code, route_id=route_id, sequence=str(index + 1))
    return render_batch_page(request, rows, [])


def component_context(route):
    labels, notes, error = [], [], ""
    has_components = bool(route.part_id and route.part.components.filter(component__part_type="RM").exists())
    prints_parent_route = uses_parent_operations(route)
    if has_components and not prints_parent_route:
        try:
            labels, notes, _ = preview_labels_for_line(
                SimpleNamespace(route_id=route.pk, shop_order="—", quantity=Decimal("1"), position=1))
        except ValueError as exc:
            error = str(exc)
    return {"has_components": has_components, "prints_parent_route": prints_parent_route,
            "bom_components": list(route.part.components.filter(component__part_type="RM").select_related("component")) if prints_parent_route else [],
            "component_labels": labels, "component_notes": notes, "component_error": error}


@login_required
def route_group(request, pk):
    from rutas.services.universo import normalize
    anchor = get_object_or_404(parent_routes(), pk=pk)
    key = normalize(anchor.code)
    variants = [r for r in parent_routes().select_related("client", "part", "source").prefetch_related("operations").order_by("classification", "source_row", "id")
                if normalize(r.code) == key]
    group = group_routes(variants)[0]
    return render(request, "rutas/route_group.html", {"group": group,
        "variants": [{"route": r, **component_context(r)} for r in variants], "label_modes": LABEL_MODES})


@login_required
def route_detail(request, pk):
    route = get_object_or_404(Route.objects.select_related("client", "part", "source").prefetch_related("operations", "history__user"), pk=pk)
    issues = ImportIssue.objects.filter(run__source=route.source, sheet="Ruta", row=route.source_row) if route.source_id else ImportIssue.objects.none()
    return render(request, "rutas/detail.html", {"route": route, "issues": issues,
        "component_parents": Route.objects.filter(part__components__component_route=route).distinct(),
        **component_context(route), "label_modes": LABEL_MODES})


@login_required
@permission_required("rutas.view_route", raise_exception=True)
def route_print(request, pk):
    """Printable route preview without creating an issued production document."""
    try:
        template_key = validate_print_template(request.GET.get("template_key", CLASSIC_TEMPLATE))
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))
    route = get_object_or_404(Route.objects.select_related("client", "part").prefetch_related("operations"), pk=pk)
    label_mode = request.GET.get("label_mode", DEFAULT_LABEL_MODE)
    line = SimpleNamespace(route_id=route.pk, shop_order="—", quantity=Decimal("1"), position=1)
    try:
        labels, _, needs_review = preview_labels_for_line(line, label_mode)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("rutas:detail", pk=route.pk)
    for label in labels:
        label["quantity"] = "—"
    snapshot = {
        "client": route.client.name, "week": "—", "line": "—", "copies": 1,
        "planner": "—", "responsible": "—", "issue_date": timezone.localdate().isoformat(),
        "ship_date": "", "lines": [], "labels": labels, "label_mode": label_mode,
        "preview_status": "RUTA SIN APROBAR · NO PRODUCCIÓN" if needs_review else "VISTA PREVIA · NO PRODUCCIÓN",
    }
    response = FileResponse(BytesIO(render_pdf(snapshot, template_key)), content_type="application/pdf", as_attachment=False,
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
    template_key = request.POST.get("template_key", CLASSIC_TEMPLATE)
    label_mode = request.POST.get("label_mode", DEFAULT_LABEL_MODE)
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
                pdf = build_pdf(rows, template_key, label_mode)
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
                     ("shop_order", "parent_code", "quantity", "week", "re", "sequence", "line", "planner", "responsible", "route_id")}
                    for index in range(submitted_count)
                ] or blank_rows()
                for index, row in enumerate(rows, 1):
                    row["shop_order"] = row["week"]
                    row["sequence"] = str(index)
                for field in ("line", "planner", "responsible"):
                    rows[0][field] = request.POST.get(f"common_{field}", "").strip()
    return render_batch_page(request, rows, errors, notice, template_key, label_mode)


def render_batch_page(request, rows, errors, notice="", template_key=CLASSIC_TEMPLATE,
                      label_mode=DEFAULT_LABEL_MODE):
    route_catalog = {}
    route_values = parent_routes().exclude(status=Route.ARCHIVED).exclude(code="").annotate(
        rm_count=Count("part__components", filter=Q(part__components__component__part_type="RM"))
    ).order_by("client__name", "classification", "source_row", "id").values_list(
        "id", "client__name", "classification", "code", "source_row", "rm_count", "status", "source__filename")
    for pk, client, variant, code, source_row, count, status, filename in route_values:
        label = f"{client} · {variant or 'Captura web'}"
        if filename:
            label += f" · {filename}"
        if source_row:
            label += f" · fila {source_row}"
        route_catalog.setdefault(code.strip().upper(), []).append({
            "id": pk, "code": code, "label": label, "re": count, "status": status})
    parent_codes = sorted({options[0]["code"] for options in route_catalog.values()}, key=str.casefold)
    warnings = []
    for index, row in enumerate(rows, 1):
        code = row.get("parent_code", "").strip()
        options = route_catalog.get(code.upper(), []) if code else []
        row["route_options"] = options
        chosen = str(row.get("route_id", ""))
        if len(options) == 1:
            chosen = str(options[0]["id"])
        row["route_id"] = chosen
        if len(options) > 1 and not chosen:
            warnings.append(f"Fila {index + 1}: {code} existe en varias rutas. Elige la correcta en esa fila.")
        selected_option = next((option for option in options if str(option["id"]) == chosen), None)
        if settings.ROUTE_REVIEW_VISIBLE and selected_option and selected_option["status"] != Route.ACTIVE:
            warnings.append(f"Fila {index + 1}: {code} está Por revisar. El PDF será una vista previa no aprobada.")
    return render(request, "rutas/batch_print.html", {"rows": rows, "errors": errors,
        "parent_codes": parent_codes, "route_catalog": route_catalog,
        "notice": notice, "warnings": warnings, "print_templates": PRINT_TEMPLATES,
        "template_key": template_key, "label_modes": LABEL_MODES, "label_mode": label_mode})


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
    universe_id = request.POST.get("universe_id") if request.method == "POST" else request.GET.get("universe_id")
    if not universe_id:
        if request.method == "POST":
            return HttpResponseBadRequest("Selecciona primero una pieza activa de Universo Ramos sin ruta.")
        query = request.GET.get("q", "").strip()
        pieces = pieces_without_routes()
        if query:
            pieces = pieces.filter(Q(part_number__icontains=query) | Q(customer__icontains=query))
        return render(request, "rutas/select_new_route.html", {
            "page": Paginator(pieces.order_by("part_number", "id"), 20).get_page(request.GET.get("page")),
            "query": query})
    universe_piece = get_object_or_404(UniversoPart, pk=universe_id, active=True) if universe_id else None
    if piece_has_route(universe_piece):
        return HttpResponseBadRequest("Esta pieza ya tiene una ruta. Abre su detalle para editarla.")
    initial, family_initial = {}, {}
    if universe_piece:
        client, _ = Client.objects.get_or_create(name=universe_piece.customer)
        initial = {"client": client.pk, "status": Route.REVIEW}
        family_initial = {"code": universe_piece.part_number, "part_type": "FP",
            "od_raw": universe_piece.data.get("diameter", ""),
            "wall_raw": universe_piece.data.get("wall") or universe_piece.data.get("wall_note", "")}
    route_data_post = request.POST.copy() if request.method == "POST" else None
    if route_data_post is not None:
        route_data_post["code"] = route_data_post.get("family-code", "").strip()
        route_data_post["description"] = route_data_post.get("family-description", "").strip()
        route_data_post["part"] = ""
    form = RouteForm(route_data_post, instance=route, initial=initial)
    form.fields["client"].disabled = True
    family_form = FamilyForm(request.POST or None, prefix="family", initial=family_initial)
    family_form.fields["code"].widget.attrs["readonly"] = True
    family_form.fields["part_type"].disabled = True
    formset = preset_operation_formset(request.POST or None, instance=route)
    children = component_editor(request.POST if request.method == "POST" else None)
    if request.method == "POST" and all((form.is_valid(), family_form.is_valid(), formset.is_valid(),
            validate_components(children, universe_piece.part_number))):
        if universe_piece:
            from rutas.services.universo import normalize
            if normalize(family_form.cleaned_data["code"]) != universe_piece.normalized_number:
                family_form.add_error("code", "El número de parte debe corresponder a la pieza de Universo seleccionada.")
            if normalize(form.cleaned_data["client"].name) != normalize(universe_piece.customer):
                form.add_error("client", "El cliente debe corresponder a la pieza de Universo seleccionada.")
            if form.errors or family_form.errors:
                return render(request, "rutas/edit.html", {"form": form, "family_form": family_form,
                    "formset": formset, "title": "Nueva ruta", "universe_piece": universe_piece, **children})
        with transaction.atomic():
            universe_piece = UniversoPart.objects.select_for_update().get(pk=universe_piece.pk)
            if not universe_piece.active or piece_has_route(universe_piece):
                form.add_error(None, "La pieza ya tiene ruta o dejó de estar activa en Universo. Selecciona otra pieza.")
                return render(request, "rutas/edit.html", {"form": form, "family_form": family_form,
                    "formset": formset, "title": "Nueva ruta", "universe_piece": universe_piece, **children})
            part = family_form.save(commit=False)
            part.code = universe_piece.part_number
            part.client = form.cleaned_data["client"]
            part.save()
            route = form.save(commit=False)
            route.universe_part = universe_piece
            route.part = part
            route.code = part.code
            route.description = part.description
            route.save()
            replace_operations(route, formset)
            save_components(children, route, request.user, replace_operations)
            RouteChange.objects.create(route=route, user=request.user, action="create", after=route_data(route))
        messages.success(request, "Ruta creada.")
        return redirect("rutas:detail", pk=route.pk)
    return render(request, "rutas/edit.html", {"form": form, "family_form": family_form,
                                               "formset": formset, "title": "Nueva ruta", "universe_piece": universe_piece, **children})


@login_required
@permission_required("rutas.change_route", raise_exception=True)
def route_edit(request, pk):
    route = get_object_or_404(Route.objects.select_related("part", "client"), pk=pk)
    original_code = route.code
    posted = request.POST if request.method == "POST" else None
    family_submitted = posted is not None and "family-code" in posted
    route_data_post = posted.copy() if posted is not None else None
    if family_submitted:
        route_data_post["code"] = posted.get("family-code", "")
        route_data_post["description"] = posted.get("family-description", "")
    form = RouteForm(route_data_post, instance=route)
    form.fields["client"].disabled = True
    form.fields["part"].disabled = True
    family_form = FamilyForm(posted if family_submitted else None, prefix="family",
        instance=route.part or Part(client=route.client, part_type="FP"),
        initial={"code": original_code, "description": route.description})
    family_form.fields["code"].widget.attrs["readonly"] = True
    family_form.fields["part_type"].disabled = True
    formset = preset_operation_formset(posted, instance=route)
    children = component_editor(posted, parent=route)
    context = {"form": form, "family_form": family_form, "formset": formset,
               "route": route, "title": "Editar ruta", **children}
    if request.method == "POST":
        valid = all((form.is_valid(), family_form.is_valid() if family_submitted else True,
            formset.is_valid(), validate_components(children, original_code) if children["components_submitted"] else True))
        if family_submitted and family_form.is_valid():
            from rutas.services.universo import normalize
            if normalize(family_form.cleaned_data["code"]) != normalize(original_code):
                family_form.add_error("code", "El n\u00famero de la pieza no se cambia al editar sus procesos.")
                valid = False
        if valid:
            with transaction.atomic():
                locked = Route.objects.select_for_update().get(pk=pk)
                if form.cleaned_data["version"] != locked.version:
                    form.add_error(None, "Otra persona modific\u00f3 esta ruta. Recarga para revisar los cambios.")
                elif children["components_submitted"] and not lock_component_versions(children):
                    pass
                else:
                    before = route_data(locked)
                    updated = form.save(commit=False)
                    if family_submitted or (children["components_submitted"] and not locked.part_id):
                        part = family_form.save(commit=False) if family_submitted else Part(
                            client=locked.client, code=original_code, description=locked.description, part_type="FP")
                        old_part_id = part.pk
                        if part.pk and (part.source_id or Route.objects.filter(part=part).exclude(pk=pk).exists()):
                            part = fork_part(part)
                        part.client = locked.client
                        part.save()
                        if old_part_id and part.pk != old_part_id:
                            BOMItem.objects.bulk_create([BOMItem(parent=part, component_id=item.component_id,
                                component_route_id=item.component_route_id, position=item.position,
                                quantity_per=item.quantity_per, source_raw_quantity=item.source_raw_quantity)
                                for item in BOMItem.objects.filter(parent_id=old_part_id)])
                        updated.part, updated.code, updated.description = part, part.code, part.description
                    updated.version = locked.version + 1
                    updated.save()
                    replace_operations(updated, formset)
                    if children["components_submitted"]:
                        save_components(children, updated, request.user, replace_operations)
                    RouteChange.objects.create(route=updated, user=request.user, action="edit", before=before, after=route_data(updated))
                    messages.success(request, "Ruta actualizada.")
                    return redirect("rutas:detail", pk=pk)
    return render(request, "rutas/edit.html", context)


@login_required
@permission_required("rutas.add_route", raise_exception=True)
@require_POST
def route_duplicate(request, pk):
    original = get_object_or_404(Route.objects.prefetch_related("operations"), pk=pk)
    return HttpResponseBadRequest("Esta pieza ya tiene una ruta. Edita la existente; las rutas nuevas se crean desde una pieza de Universo sin ruta.")



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
    template_key = request.POST.get("template_key", CLASSIC_TEMPLATE)
    label_mode = request.POST.get("label_mode", DEFAULT_LABEL_MODE)
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
        elif request.POST.get("action") == "print_all" and template_key not in dict(PRINT_TEMPLATES):
            form.add_error(None, "Selecciona un diseño de impresión válido.")
        elif request.POST.get("action") == "print_all" and label_mode not in dict(LABEL_MODES):
            form.add_error(None, "Selecciona una opción de etiquetas válida.")
        else:
            with transaction.atomic():
                schedule = form.save()
                for data in lines:
                    schedule.lines.create(route=data["route"], shop_order=data["shop_order"], quantity=data["quantity"], position=data["position"])
            request.session.pop("selected_route_ids", None)
            if request.POST.get("action") == "print_all":
                try:
                    document = issue_schedule(schedule, request.user, template_key, label_mode)
                except ValueError as exc:
                    messages.error(request, str(exc))
                    return redirect("rutas:schedule_detail", pk=schedule.pk)
                return redirect("rutas:document", pk=document.pk)
            return redirect("rutas:schedule_detail", pk=schedule.pk)
    return render(request, "rutas/schedule_edit.html", {"form": form, "formset": formset,
        "re_counts": re_counts, "print_templates": PRINT_TEMPLATES, "template_key": template_key,
        "label_modes": LABEL_MODES, "label_mode": label_mode})


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
    return render(request, "rutas/schedule_detail.html", {"schedule": schedule, "previews": previews,
        "print_templates": PRINT_TEMPLATES, "label_modes": LABEL_MODES})


@login_required
@permission_required("rutas.add_issueddocument", raise_exception=True)
@require_POST
def schedule_issue(request, pk):
    schedule = get_object_or_404(Schedule, pk=pk)
    try:
        document = issue_schedule(schedule, request.user, request.POST.get("template_key", CLASSIC_TEMPLATE),
                                  request.POST.get("label_mode", DEFAULT_LABEL_MODE))
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

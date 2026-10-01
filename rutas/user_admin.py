from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import SetPasswordForm
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from rutas.user_forms import UserCreateForm, UserEditForm


def superuser_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_active or not request.user.is_superuser:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapped


@superuser_required
def user_list(request):
    query = request.GET.get("q", "").strip()
    users = get_user_model().objects.prefetch_related("groups").order_by("username", "pk")
    if query:
        users = users.filter(Q(username__icontains=query) | Q(first_name__icontains=query) |
                             Q(last_name__icontains=query) | Q(email__icontains=query))
    page = Paginator(users, 25).get_page(request.GET.get("page"))
    return render(request, "rutas/users/list.html", {"page": page, "query": query})


@superuser_required
def user_create(request):
    form = UserCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = form.save()
        messages.success(request, f"Usuario {user.username} creado.")
        return redirect("rutas:user_list")
    return render(request, "rutas/users/form.html", {"form": form, "creating": True})


@superuser_required
def user_edit(request, pk):
    user = get_object_or_404(get_user_model(), pk=pk)
    if user.is_superuser or user.is_staff:
        raise PermissionDenied("Las cuentas administrativas se gestionan desde Django Admin.")
    form = UserEditForm(request.POST or None, instance=user)
    password_form = SetPasswordForm(user)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            form.save()
        messages.success(request, f"Usuario {user.username} actualizado.")
        return redirect("rutas:user_list")
    return render(request, "rutas/users/form.html", {"form": form, "password_form": password_form,
                                                       "managed_user": user, "creating": False})


@superuser_required
@require_POST
def user_password(request, pk):
    user = get_object_or_404(get_user_model(), pk=pk)
    if user.is_superuser or user.is_staff:
        raise PermissionDenied("Las cuentas administrativas se gestionan desde Django Admin.")
    password_form = SetPasswordForm(user, request.POST)
    if password_form.is_valid():
        password_form.save()
        messages.success(request, f"Contraseña de {user.username} actualizada.")
        return redirect("rutas:user_edit", pk=user.pk)
    form = UserEditForm(instance=user)
    return render(request, "rutas/users/form.html", {"form": form, "password_form": password_form,
                                                       "managed_user": user, "creating": False}, status=400)

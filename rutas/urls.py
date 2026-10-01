from django.urls import path
from rutas import user_admin, views

app_name = "rutas"
urlpatterns = [
    path("", views.route_list, name="list"),
    path("usuarios/", user_admin.user_list, name="user_list"),
    path("usuarios/nuevo/", user_admin.user_create, name="user_create"),
    path("usuarios/<int:pk>/editar/", user_admin.user_edit, name="user_edit"),
    path("usuarios/<int:pk>/contrasena/", user_admin.user_password, name="user_password"),
    path("rutas/nueva/", views.route_create, name="create"),
    path("rutas/<int:pk>/", views.route_detail, name="detail"),
    path("rutas/<int:pk>/imprimir/", views.route_print, name="route_print"),
    path("rutas/<int:pk>/editar/", views.route_edit, name="edit"),
    path("rutas/<int:pk>/duplicar/", views.route_duplicate, name="duplicate"),
    path("rutas/<int:pk>/archivar/", views.route_archive, name="archive"),
    path("rutas/seleccionar/", views.route_select, name="select"),
    path("imprimir-lote/", views.batch_print, name="batch_print"),
    path("imprimir-lote/plantilla/", views.batch_template, name="batch_template"),
    path("programacion/nueva/", views.schedule_create, name="schedule_create"),
    path("programacion/<int:pk>/", views.schedule_detail, name="schedule_detail"),
    path("programacion/<int:pk>/emitir/", views.schedule_issue, name="schedule_issue"),
    path("documentos/<int:pk>/", views.document_download, name="document"),
    path("importar/", views.import_page, name="import"),
    path("importar/<int:pk>/informe/", views.import_report, name="import_report"),
    path("incidencias/", views.issue_list, name="issues"),
    path("incidencias/<int:pk>/", views.issue_detail, name="issue_detail"),
    path("incidencias/<int:pk>/resolver/", views.issue_resolve, name="issue_resolve"),
]

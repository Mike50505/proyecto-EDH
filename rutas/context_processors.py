from django.conf import settings


def route_features(request):
    from rutas.forms import DEFAULT_PROCESSES
    return {"route_review_visible": settings.ROUTE_REVIEW_VISIBLE, "default_processes": DEFAULT_PROCESSES}

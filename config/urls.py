"""Rutas principales del proyecto TransCarga Express."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("panel.urls")),
    path("transportistas/", include("transportistas.urls")),
    path("clientes/", include("clientes.urls")),
    path("ofertas/", include("ofertas.urls")),
    path("asignaciones/", include("asignaciones.urls")),
    path("liquidaciones/", include("liquidaciones.urls")),
    path("capacitacion/", include("capacitacion.urls")),
    path("auditoria/", include("auditoria.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

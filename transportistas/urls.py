"""Rutas de la aplicación transportistas."""

from django.urls import path

from . import views, views_incidencias

app_name = "transportistas"

urlpatterns = [
    path("", views.ListaTransportistasView.as_view(), name="lista"),
    path("nuevo/", views.CrearTransportistaView.as_view(), name="crear"),
    path("advertencias/", views.ListaAdvertenciasView.as_view(), name="advertencias"),
    path("incidencias/", views_incidencias.ListaIncidenciasView.as_view(), name="incidencias"),
    path(
        "incidencias/nueva/",
        views_incidencias.CrearIncidenciaView.as_view(),
        name="incidencias_crear",
    ),
    path(
        "incidencias/<int:pk>/",
        views_incidencias.DetalleIncidenciaView.as_view(),
        name="incidencias_detalle",
    ),
    path(
        "incidencias/<int:pk>/revisar/",
        views_incidencias.RevisarIncidenciaView.as_view(),
        name="incidencias_revisar",
    ),
    path(
        "incidencias/<int:pk>/convertir/",
        views_incidencias.ConvertirEnAdvertenciaView.as_view(),
        name="incidencias_convertir",
    ),
    path(
        "incidencias/<int:pk>/vincular/",
        views_incidencias.VincularReemplazoView.as_view(),
        name="incidencias_vincular",
    ),
    path("<int:pk>/", views.DetalleTransportistaView.as_view(), name="detalle"),
    path("<int:pk>/editar/", views.EditarTransportistaView.as_view(), name="editar"),
    path("<int:pk>/estado/", views.CambiarEstadoView.as_view(), name="cambiar_estado"),
    path(
        "<int:pk>/advertencia/",
        views.RegistrarAdvertenciaView.as_view(),
        name="registrar_advertencia",
    ),
    path(
        "<int:pk>/aplicar_baja/",
        views.AplicarBajaDiferidaView.as_view(),
        name="aplicar_baja",
    ),
]

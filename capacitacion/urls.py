"""Rutas del módulo de capacitación."""

from django.urls import path

from . import views

app_name = "capacitacion"

urlpatterns = [
    path("cursos/", views.ListaCursosView.as_view(), name="cursos_lista"),
    path("cursos/nuevo/", views.CrearCursoView.as_view(), name="cursos_crear"),
    path("cursos/<int:pk>/editar/", views.EditarCursoView.as_view(), name="cursos_editar"),
    path("", views.ListaParticipacionesView.as_view(), name="participaciones_lista"),
    path(
        "inscribir/",
        views.InscribirView.as_view(),
        name="participaciones_inscribir",
    ),
    path(
        "<int:pk>/",
        views.DetalleParticipacionView.as_view(),
        name="participacion_detalle",
    ),
    path(
        "<int:pk>/avance/",
        views.AvanzarParticipacionView.as_view(),
        name="participacion_avance",
    ),
    path(
        "<int:pk>/confirmar/",
        views.ConfirmarParticipacionView.as_view(),
        name="participacion_confirmar",
    ),
    path(
        "<int:pk>/constancia/",
        views.DescargarConstanciaView.as_view(),
        name="participacion_constancia",
    ),
]

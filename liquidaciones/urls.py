"""Rutas del módulo de liquidaciones."""

from django.urls import path

from . import views

app_name = "liquidaciones"

urlpatterns = [
    path("formatos/", views.ListaFormatosView.as_view(), name="formatos_lista"),
    path(
        "formatos/generar/<int:asignacion_pk>/",
        views.GenerarFormatosView.as_view(),
        name="formatos_generar",
    ),
    path("formatos/<int:pk>/", views.DetalleFormatoView.as_view(), name="formato_detalle"),
    path(
        "formatos/<int:pk>/firmar/",
        views.FirmarFormatoView.as_view(),
        name="formato_firmar",
    ),
    path(
        "formatos/<int:pk>/liquidar/",
        views.GenerarLiquidacionView.as_view(),
        name="liquidacion_generar",
    ),
    path("", views.ListaLiquidacionesView.as_view(), name="liquidaciones_lista"),
    path(
        "<int:pk>/",
        views.DetalleLiquidacionView.as_view(),
        name="liquidacion_detalle",
    ),
    path(
        "<int:pk>/cerrar/",
        views.CerrarLiquidacionView.as_view(),
        name="liquidacion_cerrar",
    ),
    path("parametros/", views.ConfigurarParametrosView.as_view(), name="parametros"),
]

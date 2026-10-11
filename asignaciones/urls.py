"""Rutas de la aplicación asignaciones."""

from django.urls import path

from . import views

app_name = "asignaciones"

urlpatterns = [
    path("", views.ListaAsignacionesView.as_view(), name="lista"),
    path("nueva/", views.AsignacionCrearView.as_view(), name="nueva"),
    path("confirmar/", views.ConfirmarAsignacionView.as_view(), name="confirmar"),
    path("<int:pk>/", views.DetalleAsignacionView.as_view(), name="detalle"),
    path("<int:pk>/finalizar/", views.FinalizarAsignacionView.as_view(), name="finalizar"),
    path("<int:pk>/cancelar/", views.CancelarAsignacionView.as_view(), name="cancelar"),
]

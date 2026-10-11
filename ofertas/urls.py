"""Rutas de la aplicación ofertas."""

from django.urls import path

from . import views

app_name = "ofertas"

urlpatterns = [
    path("", views.ListaOfertasView.as_view(), name="lista"),
    path("nueva/", views.CrearOfertaView.as_view(), name="crear"),
    path("<int:pk>/", views.DetalleOfertaView.as_view(), name="detalle"),
    path("<int:pk>/editar/", views.EditarOfertaView.as_view(), name="editar"),
    path("<int:pk>/estado/", views.CambiarEstadoOfertaView.as_view(), name="cambiar_estado"),
    path("<int:pk>/asignar/", views.AsignarOfertaView.as_view(), name="asignar"),
]

"""Rutas de la aplicación clientes."""

from django.urls import path

from . import views

app_name = "clientes"

urlpatterns = [
    path("", views.ListaClientesView.as_view(), name="lista"),
    path("nuevo/", views.CrearClienteView.as_view(), name="crear"),
    path("<int:pk>/", views.DetalleClienteView.as_view(), name="detalle"),
    path("<int:pk>/editar/", views.EditarClienteView.as_view(), name="editar"),
]

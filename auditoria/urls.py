"""Rutas de la auditoría de operaciones."""

from django.urls import path

from . import views

app_name = "auditoria"

urlpatterns = [
    path("", views.ListaAuditoriaView.as_view(), name="lista"),
]

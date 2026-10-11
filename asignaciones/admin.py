"""Registro del modelo de asignaciones en el panel de administración."""

from django.contrib import admin

from .models import Asignacion


@admin.register(Asignacion)
class AsignacionAdmin(admin.ModelAdmin):
    list_display = ("oferta", "transportista", "fecha_inicio", "fecha_fin", "estado")
    list_filter = ("estado", "fecha_inicio")
    search_fields = (
        "oferta__codigo",
        "transportista__nombre",
        "transportista__numero_documento",
        "transportista__placa",
    )
    autocomplete_fields = ("transportista",)
    readonly_fields = ("creado", "actualizado")
    date_hierarchy = "fecha_inicio"

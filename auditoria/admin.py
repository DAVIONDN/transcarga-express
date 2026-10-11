"""Registro de auditoría en el panel de administración (solo lectura útil)."""

from django.contrib import admin

from .models import RegistroAuditoria


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    list_display = ("fecha_hora", "usuario", "accion", "entidad", "entidad_id")
    list_filter = ("accion", "entidad")
    search_fields = ("resumen", "usuario__username")
    readonly_fields = ("usuario", "fecha_hora", "accion", "entidad", "entidad_id", "resumen")

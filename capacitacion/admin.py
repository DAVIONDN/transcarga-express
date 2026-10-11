"""Registro del módulo de capacitación en el panel de administración."""

from django.contrib import admin

from .models import Curso, Participacion


@admin.register(Curso)
class CursoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "titulo", "tema", "duracion_horas", "estado")
    list_filter = ("estado",)
    search_fields = ("codigo", "titulo", "tema")
    readonly_fields = ("creado", "actualizado")


@admin.register(Participacion)
class ParticipacionAdmin(admin.ModelAdmin):
    list_display = (
        "transportista",
        "curso",
        "convocatoria",
        "fecha",
        "estado",
        "resultado",
    )
    list_filter = ("estado", "resultado", "curso")
    search_fields = ("transportista__nombre", "curso__codigo", "convocatoria")
    autocomplete_fields = ("transportista",)
    readonly_fields = ("creado", "actualizado")

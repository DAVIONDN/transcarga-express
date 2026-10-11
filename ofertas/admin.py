"""Registro del modelo de ofertas de carga en el panel de administración."""

from django.contrib import admin

from .models import OfertaCarga


@admin.register(OfertaCarga)
class OfertaCargaAdmin(admin.ModelAdmin):
    list_display = (
        "codigo",
        "empresa_cliente",
        "origen",
        "destino",
        "nivel_requerido",
        "tipo_vehiculo_requerido",
        "remuneracion",
        "estado",
    )
    list_filter = ("estado", "nivel_requerido", "tipo_vehiculo_requerido")
    search_fields = ("codigo", "origen", "destino", "empresa_cliente__razon_social", "empresa_cliente__ruc")
    readonly_fields = ("codigo", "creado", "actualizado")
    autocomplete_fields = ("empresa_cliente",)
    date_hierarchy = "creado"

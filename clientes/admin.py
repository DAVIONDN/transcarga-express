"""Registro del modelo de empresas clientes en el panel de administración."""

from django.contrib import admin

from .models import EmpresaCliente


@admin.register(EmpresaCliente)
class EmpresaClienteAdmin(admin.ModelAdmin):
    list_display = ("razon_social", "ruc", "actividad_economica", "direccion")
    list_filter = ("actividad_economica",)
    search_fields = ("razon_social", "ruc")
    readonly_fields = ("creado", "actualizado")
    date_hierarchy = "creado"

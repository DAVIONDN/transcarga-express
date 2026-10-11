"""Registro de los modelos en el panel de administración de Django."""

from django.contrib import admin

from .models import Advertencia, Incidencia, Transportista


@admin.register(Transportista)
class TransportistaAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "numero_documento",
        "placa",
        "nivel",
        "capacidad_toneladas",
        "estado",
        "soat_vence",
        "licencia_vence",
    )
    list_filter = ("estado", "nivel", "tipo_vehiculo", "tipo_documento", "certificacion_carga_peligrosa")
    search_fields = ("nombre", "numero_documento", "placa")
    readonly_fields = ("nivel", "creado", "actualizado")
    date_hierarchy = "creado"
    fieldsets = (
        (
            "Identificación",
            {
                "fields": (
                    "tipo_documento",
                    "numero_documento",
                    "nombre",
                    "direccion",
                    "anios_experiencia",
                    "estado",
                )
            },
        ),
        (
            "Vehículo principal",
            {
                "fields": (
                    "placa",
                    "tipo_vehiculo",
                    "capacidad_toneladas",
                    "nivel",
                    "certificacion_carga_peligrosa",
                    "fotografia_vehiculo",
                )
            },
        ),
        (
            "Documentación",
            {
                "fields": (
                    "fecha_vencimiento_licencia",
                    "fecha_vencimiento_revision_tecnica",
                    "fecha_vencimiento_soat",
                    "copia_soat",
                )
            },
        ),
        ("Auditoría", {"fields": ("creado", "actualizado")}),
    )

    @admin.display(description="Vence el SOAT", ordering="fecha_vencimiento_soat")
    def soat_vence(self, obj):
        return obj.fecha_vencimiento_soat

    @admin.display(description="Vence la licencia", ordering="fecha_vencimiento_licencia")
    def licencia_vence(self, obj):
        return obj.fecha_vencimiento_licencia


@admin.register(Advertencia)
class AdvertenciaAdmin(admin.ModelAdmin):
    list_display = ("fecha", "transportista", "descripcion_corta", "asignacion", "registrado_por")
    list_filter = ("fecha", "transportista__estado")
    search_fields = ("descripcion", "transportista__nombre", "transportista__numero_documento")
    autocomplete_fields = ("transportista",)
    readonly_fields = ("creado",)

    @admin.display(description="Descripción")
    def descripcion_corta(self, obj):
        return obj.descripcion[:70]


@admin.register(Incidencia)
class IncidenciaAdmin(admin.ModelAdmin):
    list_display = ("fecha", "tipo", "transportista", "empresa_cliente", "estado_revision")
    list_filter = ("tipo", "estado_revision", "fecha")
    search_fields = ("descripcion", "transportista__nombre", "empresa_cliente__razon_social")
    autocomplete_fields = ("transportista", "empresa_cliente")
    readonly_fields = ("creado",)

"""Registro del módulo de liquidaciones en el panel de administración."""

from django.contrib import admin

from .models import FormatoSemanal, Liquidacion, ParametrosLiquidacion


@admin.register(ParametrosLiquidacion)
class ParametrosLiquidacionAdmin(admin.ModelAdmin):
    list_display = ("comision_pct", "penalidad_semanal", "actualizado")


@admin.register(FormatoSemanal)
class FormatoSemanalAdmin(admin.ModelAdmin):
    list_display = (
        "asignacion",
        "periodo_inicio",
        "periodo_fin",
        "fecha_prevista",
        "fecha_firma",
        "estado",
    )
    list_filter = ("estado", "fecha_prevista")
    search_fields = ("asignacion__oferta__codigo", "asignacion__transportista__nombre")
    readonly_fields = ("creado", "actualizado")


@admin.register(Liquidacion)
class LiquidacionAdmin(admin.ModelAdmin):
    list_display = ("formato", "estado", "base", "comision_monto", "penalidad_monto", "total")
    list_filter = ("estado",)
    search_fields = (
        "formato__asignacion__oferta__codigo",
        "formato__asignacion__transportista__nombre",
    )
    readonly_fields = (
        "base",
        "comision_monto",
        "penalidad_monto",
        "semanas_retraso",
        "total",
        "detalle",
        "creado",
        "actualizado",
    )

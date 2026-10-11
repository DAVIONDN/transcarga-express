"""Registro de auditoría de operaciones críticas.

Guarda quién, cuándo, qué acción, sobre qué entidad y un resumen construido
explícitamente (nunca volcados de formularios): jamás contraseñas, secretos ni
tokens. No se afirma inalterabilidad: los superusuarios conservan acceso total
por diseño nativo de Django.
"""

from django.conf import settings
from django.db import models


class TipoAccion(models.TextChoices):
    CREAR = "CREAR", "Creación"
    ACTUALIZAR = "ACTUALIZAR", "Actualización"
    CAMBIAR_ESTADO = "CAMBIAR_ESTADO", "Cambio de estado"
    ASIGNAR = "ASIGNAR", "Asignación"
    FINALIZAR = "FINALIZAR", "Finalización"
    CANCELAR = "CANCELAR", "Cancelación"
    ADVERTENCIA = "ADVERTENCIA", "Advertencia"
    USUARIO = "USUARIO", "Gestión de usuarios"
    DOCUMENTO = "DOCUMENTO", "Documento"
    FORMATO = "FORMATO", "Formato semanal"
    LIQUIDACION = "LIQUIDACION", "Liquidación"
    CURSO = "CURSO", "Capacitación"
    EXPORTAR = "EXPORTAR", "Exportación de reporte"


class RegistroAuditoria(models.Model):
    """Rastro consultable de una operación crítica."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="registros_auditoria",
        verbose_name="Usuario responsable",
    )
    fecha_hora = models.DateTimeField("Fecha y hora", auto_now_add=True)
    accion = models.CharField("Tipo de acción", max_length=15, choices=TipoAccion.choices)
    entidad = models.CharField("Entidad afectada", max_length=30)
    entidad_id = models.PositiveIntegerField("Identificador", null=True, blank=True)
    resumen = models.CharField("Resumen", max_length=280)

    class Meta:
        verbose_name = "Registro de auditoría"
        verbose_name_plural = "Registros de auditoría"
        ordering = ["-fecha_hora", "-id"]
        permissions = [
            ("ver_auditoria", "Puede consultar la auditoría de operaciones."),
        ]

    def __str__(self):
        return f"{self.get_accion_display()} {self.entidad} #{self.entidad_id or '—'}"


def auditar(*, usuario, accion, entidad, entidad_id=None, resumen=""):
    """Registra una acción crítica. El resumen lo construye quien llama."""
    if usuario is None or getattr(usuario, "is_anonymous", False):
        return None
    return RegistroAuditoria.objects.create(
        usuario=usuario,
        accion=accion,
        entidad=entidad,
        entidad_id=entidad_id,
        resumen=(resumen or "")[:280],
    )

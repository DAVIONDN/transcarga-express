"""Modelo de las asignaciones entre transportistas y ofertas de carga.

Invariantes que se garantizan aquí:
* R5/R6: una oferta cubierta solo puede tener una asignación (OneToOneField) y un
  transportista no puede tener más de una asignación activa (restricción parcial).
"""

from django.core.exceptions import ValidationError
from django.db import models

from comun.choices import EstadoAsignacion
from ofertas.models import OfertaCarga
from transportistas.models import Transportista


class Asignacion(models.Model):
    """Asignación de una oferta de carga a un transportista.

    Estados: Activa (en curso), Finalizada (cerrada con fecha de finalización) y
    Cancelada (anulada dejando constancia). Ningún estado borra el registro ni la
    relación con la oferta o el transportista: el historial se conserva siempre.
    """

    transportista = models.ForeignKey(
        Transportista,
        on_delete=models.PROTECT,
        related_name="asignaciones",
        verbose_name="Transportista",
    )
    oferta = models.OneToOneField(
        OfertaCarga,
        on_delete=models.PROTECT,
        related_name="asignacion",
        verbose_name="Oferta de carga",
        help_text="Una oferta cubierta no puede recibir otra asignación.",
    )
    fecha_inicio = models.DateField("Fecha de inicio")
    fecha_fin = models.DateField(
        "Fecha de finalización",
        null=True,
        blank=True,
        help_text="Puede dejarse vacía mientras la asignación esté en curso.",
    )
    estado = models.CharField(
        "Estado",
        max_length=12,
        choices=EstadoAsignacion.choices,
        default=EstadoAsignacion.ACTIVA,
    )
    motivo_cancelacion = models.TextField(
        "Motivo de la cancelación",
        blank=True,
        default="",
        help_text="Obligatorio al cancelar: explica por qué no se ejecutó el servicio.",
    )

    creado = models.DateTimeField("Creado", auto_now_add=True)
    actualizado = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        verbose_name = "Asignación"
        verbose_name_plural = "Asignaciones"
        ordering = ["-fecha_inicio", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["transportista"],
                condition=models.Q(estado=EstadoAsignacion.ACTIVA),
                name="una_asignacion_activa_por_transportista",
            )
        ]
        permissions = [
            ("finalizar_asignacion", "Puede finalizar una asignación."),
            ("cancelar_asignacion", "Puede cancelar una asignación."),
        ]

    def __str__(self):
        return f"{self.oferta.codigo} → {self.transportista.nombre} ({self.get_estado_display()})"

    def clean(self):
        super().clean()
        if self.fecha_inicio and self.fecha_fin and self.fecha_fin < self.fecha_inicio:
            raise ValidationError(
                {"fecha_fin": "La fecha de finalización no puede ser anterior a la fecha de inicio."}
            )

    @property
    def esta_activa(self):
        return self.estado == EstadoAsignacion.ACTIVA

    @property
    def esta_finalizada(self):
        return self.estado == EstadoAsignacion.FINALIZADA

    @property
    def esta_cancelada(self):
        return self.estado == EstadoAsignacion.CANCELADA

    @property
    def alerta_documental(self):
        """Documentos obligatorios vencidos o pendientes durante el servicio.

        Solo aplica a asignaciones activas: si un documento vence durante la
        ejecución, se genera esta alerta sin cambiar el estado contractual ni
        crear advertencias automáticas (eso lo decide un operador).
        """
        if not self.esta_activa:
            return []
        return self.transportista.documentos_vencidos() + self.transportista.documentos_pendientes()

    def finalizar(self, fecha):
        """Cierra la asignación con su fecha de finalización, sin borrar nada."""
        self.estado = EstadoAsignacion.FINALIZADA
        self.fecha_fin = fecha
        self.full_clean()
        self.save(update_fields=["estado", "fecha_fin", "actualizado"])

    def cancelar(self, fecha=None, motivo=""):
        """Marca la asignación como Cancelada conservando el historial completo.

        La oferta permanece Cubierta (decisión D6 del plan: una oferta cubierta no se
        reasigna en el MVP). El transportista queda libre para otra asignación, porque
        la restricción de unicidad solo alcanza a las asignaciones Activas. El motivo
        queda registrado y no puede quedar vacío desde la pantalla de cancelación.

        Devuelve True si el estado cambió en esta llamada.
        """
        if self.estado == EstadoAsignacion.CANCELADA:
            return False
        self.estado = EstadoAsignacion.CANCELADA
        if fecha is not None:
            self.fecha_fin = fecha
        self.motivo_cancelacion = (motivo or "").strip()
        self.full_clean()
        self.save(update_fields=["estado", "fecha_fin", "motivo_cancelacion", "actualizado"])
        return True

    @property
    def advertencias_total(self):
        return self.advertencias.count()

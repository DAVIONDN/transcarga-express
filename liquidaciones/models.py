"""Formatos semanales, liquidaciones y parámetros financieros.

Fuente de verdad de los importes: `OfertaCarga.remuneracion` (total del
servicio). La base semanal se prorratea (`liquidaciones.calculos`) y cada
liquidación guarda el detalle que justifica su total. Una liquidación
CERRADA es inmutable: no hay vistas de edición y el reproceso solo
recalcula borradores.
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction

from comun import fechas
from comun.choices import EstadoAsignacion

from . import calculos


class ParametrosLiquidacion(models.Model):
    """Parámetros financieros configurables (sin valores comerciales inventados).

    Registro único (pk = 1): hasta que la comisión y la penalidad estén
    configuradas, el cierre definitivo queda bloqueado.
    """

    comision_pct = models.DecimalField(
        "Comisión de intermediación (%)",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Porcentaje definido por la empresa antes de calcular.",
    )
    penalidad_semanal = models.DecimalField(
        "Penalidad por semana de retraso (S/)",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Monto por cada semana de retraso en la firma del formato.",
    )
    actualizado = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        verbose_name = "Parámetros de liquidación"
        verbose_name_plural = "Parámetros de liquidación"
        permissions = [
            ("configurar_liquidacion", "Puede configurar los parámetros financieros."),
        ]

    def __str__(self):
        return "Parámetros de liquidación"

    @classmethod
    def obtener(cls):
        """Devuelve el registro único, creándolo vacío si no existe."""
        registro, _ = cls.objects.get_or_create(pk=1)
        return registro

    @property
    def configurados(self):
        return self.comision_pct is not None and self.penalidad_semanal is not None


class EstadoFormato(models.TextChoices):
    PENDIENTE = "PENDIENTE", "Pendiente"
    PRESENTADO = "PRESENTADO", "Presentado"
    REGULARIZADO = "REGULARIZADO", "Regularizado"
    LIQUIDADO = "LIQUIDADO", "Liquidado"


class EstadoLiquidacion(models.TextChoices):
    BORRADOR = "BORRADOR", "Borrador"
    CERRADA = "CERRADA", "Cerrada"


class FormatoSemanal(models.Model):
    """Formato semanal de un servicio: se firma o confirma los viernes."""

    asignacion = models.ForeignKey(
        "asignaciones.Asignacion",
        on_delete=models.PROTECT,
        related_name="formatos",
        verbose_name="Asignación",
    )
    periodo_inicio = models.DateField("Inicio del periodo (lunes)")
    periodo_fin = models.DateField("Fin del periodo (domingo)")
    fecha_prevista = models.DateField("Fecha prevista de firma (viernes)")
    fecha_firma = models.DateField("Fecha real de firma", null=True, blank=True)
    estado = models.CharField(
        "Estado",
        max_length=12,
        choices=EstadoFormato.choices,
        default=EstadoFormato.PENDIENTE,
    )
    creado = models.DateTimeField("Creado", auto_now_add=True)
    actualizado = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        verbose_name = "Formato semanal"
        verbose_name_plural = "Formatos semanales"
        ordering = ["periodo_inicio", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["asignacion", "periodo_inicio"],
                name="un_formato_por_semana_y_asignacion",
            )
        ]
        permissions = [
            ("generar_formatos", "Puede generar los formatos semanales."),
            ("firmar_formato", "Puede registrar la firma de un formato."),
        ]

    def __str__(self):
        return f"{self.asignacion.oferta.codigo} · semana {fechas.formatear_fecha(self.periodo_inicio)}"

    def clean(self):
        super().clean()
        if self.periodo_fin and self.periodo_inicio and self.periodo_fin < self.periodo_inicio:
            raise ValidationError(
                {"periodo_fin": "El fin del periodo no puede ser anterior a su inicio."}
            )
        if self.fecha_firma and self.fecha_firma > fechas.hoy():
            raise ValidationError(
                {"fecha_firma": "La fecha de firma no puede ser futura."}
            )

    @property
    def esta_firmado(self):
        return self.fecha_firma is not None

    @property
    def esta_atrasado(self):
        """Pendiente pasada la fecha prevista (derivado, sin proceso)."""
        return self.estado == EstadoFormato.PENDIENTE and self.fecha_prevista < fechas.hoy()

    @property
    def etiqueta_estado(self):
        if self.esta_atrasado:
            return "Atrasado"
        return self.get_estado_display()

    @property
    def exento_penalidad(self):
        """Contratos inferiores a una semana: firman el viernes sin penalidad."""
        return calculos.exento_por_duracion_corta(
            self.asignacion.fecha_inicio, self.asignacion.fecha_fin
        )

    @property
    def semanas_retraso(self):
        if self.exento_penalidad or not self.fecha_firma:
            return 0
        return calculos.semanas_retraso(self.fecha_prevista, self.fecha_firma)

    def firmar(self, fecha):
        """Registra la firma: presentada en plazo, regularizada si fue tardía.

        No permite firmar si la liquidación ya está cerrada ni cambiar la fecha
        una vez firmada desde esta vía (la corrección usa el panel de
        administración). Devuelve el estado resultante.
        """
        if hasattr(self, "liquidacion") and self.liquidacion.esta_cerrada:
            raise ValidationError(
                "El formato ya tiene liquidación cerrada y no admite cambios."
            )
        self.fecha_firma = fecha
        self.full_clean()
        self.estado = (
            EstadoFormato.PRESENTADO
            if fecha <= self.fecha_prevista
            else EstadoFormato.REGULARIZADO
        )
        self.save(update_fields=["fecha_firma", "estado", "actualizado"])
        return self.estado


class Liquidacion(models.Model):
    """Liquidación de un formato semanal: neto = base − comisión − penalidad.

    Sentido adoptado (pendiente): la empresa descuenta del transportista la
    comisión de intermediación y la penalidad por retraso. El reproceso
    recalcula el borrador desde los datos verificables (sin duplicar).
    """

    formato = models.OneToOneField(
        FormatoSemanal,
        on_delete=models.PROTECT,
        related_name="liquidacion",
        verbose_name="Formato semanal",
    )
    estado = models.CharField(
        "Estado",
        max_length=10,
        choices=EstadoLiquidacion.choices,
        default=EstadoLiquidacion.BORRADOR,
    )
    base = models.DecimalField("Base semanal (S/)", max_digits=10, decimal_places=2, default=0)
    comision_monto = models.DecimalField(
        "Comisión (S/)", max_digits=10, decimal_places=2, default=0
    )
    penalidad_monto = models.DecimalField(
        "Penalidad (S/)", max_digits=10, decimal_places=2, default=0
    )
    semanas_retraso = models.PositiveSmallIntegerField("Semanas de retraso", default=0)
    total = models.DecimalField("Neto a pagar (S/)", max_digits=10, decimal_places=2, default=0)
    detalle = models.TextField("Detalle del cálculo", default="", blank=True)
    creado = models.DateTimeField("Creado", auto_now_add=True)
    actualizado = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        verbose_name = "Liquidación"
        verbose_name_plural = "Liquidaciones"
        ordering = ["formato__periodo_inicio", "id"]
        permissions = [
            ("generar_liquidacion", "Puede generar liquidaciones en borrador."),
            ("cerrar_liquidacion", "Puede cerrar una liquidación."),
        ]

    def __str__(self):
        return f"Liquidación {self.formato} ({self.get_estado_display()})"

    @property
    def esta_cerrada(self):
        return self.estado == EstadoLiquidacion.CERRADA

    def _componentes(self):
        """Calcula los componentes sin guardar (fuente: oferta y parámetros)."""
        formato = self.formato
        total_formatos = formato.asignacion.formatos.count() or 1
        bases = calculos.bases_semanales(
            formato.asignacion.oferta.remuneracion, total_formatos
        )
        indice = list(
            formato.asignacion.formatos.order_by("periodo_inicio", "id").values_list(
                "pk", flat=True
            )
        ).index(formato.pk)
        base = bases[indice]
        parametros = ParametrosLiquidacion.obtener()
        comision = (
            (base * parametros.comision_pct / 100).quantize(Decimal("0.01"))
            if parametros.comision_pct is not None
            else Decimal("0.00")
        )
        semanas = formato.semanas_retraso
        penalidad = (
            Decimal(semanas) * parametros.penalidad_semanal
            if parametros.penalidad_semanal is not None
            else Decimal("0.00")
        )
        return {
            "base": base,
            "comision": comision,
            "semanas": semanas,
            "penalidad": penalidad,
            "total": base - comision - penalidad,
            "parametros": parametros,
            "total_formatos": total_formatos,
        }

    def _detalle_texto(self, componentes):
        formato = self.formato
        lineas = [
            f"Base semanal: S/ {componentes['base']} "
            f"(prorrateo {formato.asignacion.formatos.count()} semana(s) de "
            f"S/ {formato.asignacion.oferta.remuneracion}).",
            f"Comisión ({componentes['parametros'].comision_pct}%): "
            f"S/ {componentes['comision']}.",
        ]
        if formato.exento_penalidad:
            lineas.append("Sin penalidad: contrato inferior a una semana.")
        elif componentes["semanas"]:
            lineas.append(
                f"Penalidad: {componentes['semanas']} semana(s) de retraso "
                f"(firma {fechas.formatear_fecha(formato.fecha_firma)}, prevista "
                f"{fechas.formatear_fecha(formato.fecha_prevista)}): "
                f"S/ {componentes['penalidad']}."
            )
        else:
            lineas.append(
                f"Sin penalidad: firma en plazo ({fechas.formatear_fecha(formato.fecha_firma)})."
            )
        lineas.append(f"Neto a pagar: S/ {componentes['total']}.")
        return "\n".join(lineas)

    @transaction.atomic
    def recalcular(self):
        """Reprocesa el borrador desde datos verificables (nunca duplica).

        Falla si la liquidación está cerrada: las cerradas son inmutables.
        """
        liquidacion = Liquidacion.objects.select_for_update().get(pk=self.pk)
        if liquidacion.esta_cerrada:
            raise ValidationError(
                "La liquidación está cerrada y no admite reprocesamiento."
            )
        componentes = self._componentes()
        self.base = componentes["base"]
        self.comision_monto = componentes["comision"]
        self.semanas_retraso = componentes["semanas"]
        self.penalidad_monto = componentes["penalidad"]
        self.total = componentes["total"]
        self.detalle = self._detalle_texto(componentes)
        self.save()
        return self

    @transaction.atomic
    def cerrar(self):
        """Cierra la liquidación: exige formato firmado y parámetros configurados."""
        liquidacion = Liquidacion.objects.select_for_update().get(pk=self.pk)
        formato = liquidacion.formato
        if liquidacion.esta_cerrada:
            raise ValidationError("La liquidación ya está cerrada.")
        if not formato.esta_firmado:
            raise ValidationError(
                "No se puede cerrar: el formato obligatorio está pendiente de firma."
            )
        parametros = ParametrosLiquidacion.obtener()
        if not parametros.configurados:
            raise ValidationError(
                "No se puede cerrar: configure la comisión y la penalidad antes del "
                "cálculo definitivo."
            )
        self.recalcular()
        self.estado = EstadoLiquidacion.CERRADA
        self.save(update_fields=["estado", "actualizado"])
        formato.estado = EstadoFormato.LIQUIDADO
        formato.save(update_fields=["estado", "actualizado"])
        return self

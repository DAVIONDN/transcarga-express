"""Modelo de las ofertas de carga publicadas por las empresas clientes."""

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from clientes.models import EmpresaCliente
from comun.choices import EstadoOferta, NivelCarga, TipoVehiculo


class OfertaCarga(models.Model):
    """Oferta de carga con el nivel y el tipo de vehículo requeridos."""

    codigo = models.CharField(
        "Código",
        max_length=10,
        unique=True,
        editable=False,
        blank=True,
        help_text="Se genera automáticamente con el formato OF-00001.",
    )
    empresa_cliente = models.ForeignKey(
        EmpresaCliente,
        on_delete=models.PROTECT,
        related_name="ofertas",
        verbose_name="Empresa cliente",
    )
    origen = models.CharField("Origen", max_length=120)
    destino = models.CharField("Destino", max_length=120)
    tipo_vehiculo_requerido = models.CharField(
        "Tipo de vehículo requerido",
        max_length=20,
        choices=TipoVehiculo.choices,
    )
    nivel_requerido = models.PositiveSmallIntegerField("Nivel requerido", choices=NivelCarga.choices)
    remuneracion = models.DecimalField(
        "Remuneración (S/)",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0.01, message="La remuneración debe ser mayor que cero.")],
    )
    estado = models.CharField(
        "Estado",
        max_length=12,
        choices=EstadoOferta.choices,
        default=EstadoOferta.DISPONIBLE,
    )

    creado = models.DateTimeField("Creado", auto_now_add=True)
    actualizado = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        verbose_name = "Oferta de carga"
        verbose_name_plural = "Ofertas de carga"
        ordering = ["-creado", "-id"]
        # Índice útil: el estado filtra el listado de ofertas y los conteos del panel.
        indexes = [models.Index(fields=["estado"], name="oferta_estado_idx")]
        permissions = [
            (
                "cambiar_estado_oferta",
                "Puede cambiar el estado de una oferta de carga.",
            ),
        ]

    def __str__(self):
        return f"{self.codigo}: {self.origen} → {self.destino}"

    def clean(self):
        super().clean()
        if self.remuneracion is not None and self.remuneracion <= 0:
            raise ValidationError({"remuneracion": "La remuneración debe ser mayor que cero."})

    def save(self, *args, **kwargs):
        if not self.codigo:
            self.codigo = self.generar_codigo()
        super().save(*args, **kwargs)

    @classmethod
    def generar_codigo(cls):
        """Código único consecutivo con formato OF-00001."""
        numero = cls.objects.count() + 1
        while True:
            codigo = f"OF-{numero:05d}"
            if not cls.objects.filter(codigo=codigo).exists():
                return codigo
            numero += 1

    @property
    def esta_disponible(self):
        return self.estado == EstadoOferta.DISPONIBLE

    @property
    def esta_cubierta(self):
        return self.estado == EstadoOferta.CUBIERTA

    @property
    def requiere_certificacion(self):
        """Una oferta de Nivel 1 solo puede cubrirse con vehículos certificados."""
        return self.nivel_requerido == NivelCarga.NIVEL_1

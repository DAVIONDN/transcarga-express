"""Modelo de las empresas clientes que publican ofertas de carga."""

from django.core.exceptions import ValidationError
from django.db import models


class EmpresaCliente(models.Model):
    """Empresa que contrata el transporte de carga."""

    ruc = models.CharField(
        "RUC",
        max_length=11,
        unique=True,
        help_text="11 dígitos, sin guiones.",
    )
    razon_social = models.CharField("Razón social", max_length=200)
    direccion = models.CharField("Dirección", max_length=200)
    actividad_economica = models.CharField("Actividad económica", max_length=200)

    creado = models.DateTimeField("Creado", auto_now_add=True)
    actualizado = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        verbose_name = "Empresa cliente"
        verbose_name_plural = "Empresas clientes"
        ordering = ["razon_social"]

    def __str__(self):
        return f"{self.razon_social} ({self.ruc})"

    def clean(self):
        super().clean()
        if self.ruc:
            if not self.ruc.isdigit():
                raise ValidationError({"ruc": "El RUC debe contener solo dígitos."})
            if len(self.ruc) != 11:
                raise ValidationError({"ruc": "El RUC debe tener 11 dígitos."})

    @property
    def ofertas_disponibles(self):
        from comun.choices import EstadoOferta

        return self.ofertas.filter(estado=EstadoOferta.DISPONIBLE).count()

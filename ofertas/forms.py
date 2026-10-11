"""Formularios de ofertas de carga.

El estado de la oferta no se edita desde el formulario: se cambia con una acción
confirmada (`CambiarEstadoOfertaForm`), de modo que la regla de una oferta cubierta
viva en un único lugar.
"""

from django import forms

from asignaciones.models import Asignacion
from clientes.models import EmpresaCliente
from comun.choices import EstadoOferta
from comun.forms import FormularioBootstrapMixin

from .models import OfertaCarga

# Campos que determinan la validez de una asignación ya registrada
CAMPOS_CRITICOS = (
    ("empresa_cliente", "la empresa cliente"),
    ("tipo_vehiculo_requerido", "el tipo de vehículo requerido"),
    ("nivel_requerido", "el nivel requerido"),
)

MENSAJE_OFERTA_ASIGNADA = (
    "Esta oferta ya está Cubierta por una asignación: no se puede cambiar {campos}, "
    "porque invalidaría la asignación existente. Solo puede ajustar el origen, el destino y "
    "la remuneración; la reasignación de ofertas cubiertas está fuera del alcance de este MVP."
)


class OfertaCargaForm(FormularioBootstrapMixin, forms.ModelForm):
    """Alta y edición de ofertas de carga (datos de la oferta)."""

    class Meta:
        model = OfertaCarga
        fields = (
            "empresa_cliente",
            "origen",
            "destino",
            "tipo_vehiculo_requerido",
            "nivel_requerido",
            "remuneracion",
        )
        widgets = {
            "remuneracion": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
        }
        help_texts = {
            "nivel_requerido": (
                "Nivel 1 (más de 20 t) solo puede cubrirse con un transportista que tenga "
                "certificación de carga peligrosa."
            ),
            "remuneracion": "Importe acordado en soles, mayor que cero.",
            "empresa_cliente": "La oferta siempre pertenece a una empresa cliente registrada.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["empresa_cliente"].queryset = EmpresaCliente.objects.order_by("razon_social")

    @property
    def tiene_asignacion(self):
        return bool(self.instance.pk) and Asignacion.objects.filter(oferta=self.instance).exists()

    def clean(self):
        datos = super().clean()
        if not self.tiene_asignacion:
            return datos

        # Con una asignación registrada, los campos críticos quedan bloqueados.
        bloqueados = [
            etiqueta
            for campo, etiqueta in CAMPOS_CRITICOS
            if campo in datos and datos[campo] != getattr(self.instance, campo)
        ]
        if bloqueados:
            mensaje = MENSAJE_OFERTA_ASIGNADA.format(campos=", ".join(bloqueados))
            for campo, etiqueta in CAMPOS_CRITICOS:
                if etiqueta in bloqueados:
                    self.add_error(campo, mensaje)
        return datos


class CambiarEstadoOfertaForm(FormularioBootstrapMixin, forms.Form):
    """Cambio de estado confirmado de una oferta de carga."""

    estado = forms.ChoiceField(label="Nuevo estado", choices=EstadoOferta.choices)

    def __init__(self, *args, oferta=None, **kwargs):
        self.oferta = oferta
        super().__init__(*args, **kwargs)

    def clean_estado(self):
        nuevo_estado = self.cleaned_data["estado"]
        oferta = self.oferta

        if nuevo_estado == oferta.estado:
            raise forms.ValidationError(
                f"La oferta ya se encuentra en estado «{oferta.get_estado_display()}»."
            )
        # Solo se bloquea volver a «Disponible» cuando existe una asignación registrada;
        # una oferta marcada como Cubierta a mano puede volver a admitir asignaciones.
        if nuevo_estado == EstadoOferta.DISPONIBLE and Asignacion.objects.filter(oferta=oferta).exists():
            raise forms.ValidationError(
                "La oferta tiene una asignación registrada: no puede volver a «Disponible». "
                "La reasignación de ofertas cubiertas está fuera del alcance de este MVP."
            )
        return nuevo_estado

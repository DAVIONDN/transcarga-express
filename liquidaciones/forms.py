"""Formularios del módulo de liquidaciones (validación en el servidor)."""

from django import forms

from comun import fechas
from comun.forms import FormularioBootstrapMixin

from .models import ParametrosLiquidacion


class FirmarFormatoForm(FormularioBootstrapMixin, forms.Form):
    """Registra la fecha real de firma o recepción del formato semanal."""

    fecha_firma = forms.DateField(
        label="Fecha de firma",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
        initial=fechas.hoy,
        help_text="No puede ser futura. Si es posterior al viernes previsto, se regulariza.",
    )

    def clean_fecha_firma(self):
        fecha = self.cleaned_data["fecha_firma"]
        if fecha > fechas.hoy():
            raise forms.ValidationError("La fecha de firma no puede ser futura.")
        return fecha


class ParametrosForm(FormularioBootstrapMixin, forms.ModelForm):
    """Configura la comisión y la penalidad (solo Administrador)."""

    class Meta:
        model = ParametrosLiquidacion
        fields = ("comision_pct", "penalidad_semanal")
        widgets = {
            "comision_pct": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "penalidad_semanal": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }
        help_texts = {
            "comision_pct": "Porcentaje de intermediación definido por la empresa.",
            "penalidad_semanal": "Monto en soles por cada semana de retraso.",
        }

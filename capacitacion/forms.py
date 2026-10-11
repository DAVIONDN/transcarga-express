"""Formularios de capacitación (validación en el servidor)."""

from django import forms

from comun import fechas
from comun.choices import EstadoParticipacion, ResultadoParticipacion
from comun.forms import FormularioBootstrapMixin
from transportistas.models import Transportista

from .models import Curso, Participacion


class CursoForm(FormularioBootstrapMixin, forms.ModelForm):
    """Alta y edición de cursos (código único, duración positiva)."""

    class Meta:
        model = Curso
        fields = ("codigo", "titulo", "tema", "duracion_horas", "estado")
        help_texts = {
            "codigo": "Único, en mayúsculas y sin espacios.",
            "duracion_horas": "Cantidad entera de horas, mayor que cero.",
        }
        error_messages = {
            "codigo": {"unique": "Ya existe un curso registrado con este código."},
        }

    def clean_codigo(self):
        from .models import normalizar_codigo

        return normalizar_codigo(self.cleaned_data.get("codigo") or "")


class InscribirParticipacionForm(FormularioBootstrapMixin, forms.ModelForm):
    """Inscripción: siempre nace en estado Inscrito."""

    class Meta:
        model = Participacion
        fields = ("transportista", "curso", "convocatoria", "fecha")
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }
        help_texts = {
            "convocatoria": "Edición del curso, por ejemplo «2026-03».",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["transportista"].queryset = Transportista.objects.order_by("nombre")
        self.fields["curso"].queryset = Curso.objects.order_by("codigo")
        self.fields["fecha"].initial = fechas.hoy()

    def clean_convocatoria(self):
        return (self.cleaned_data.get("convocatoria") or "").strip().upper()

    def save(self, commit=True):
        participacion = super().save(commit=False)
        participacion.estado = EstadoParticipacion.INSCRITO
        if commit:
            participacion.save()
        return participacion


class AvanzarParticipacionForm(FormularioBootstrapMixin, forms.ModelForm):
    """Cambia entre Inscrito y En progreso (nunca a Completado directo)."""

    class Meta:
        model = Participacion
        fields = ("estado",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["estado"].choices = [
            (EstadoParticipacion.INSCRITO, "Inscrito"),
            (EstadoParticipacion.EN_PROGRESO, "En progreso"),
        ]

    def clean_estado(self):
        estado = self.cleaned_data["estado"]
        if estado == EstadoParticipacion.COMPLETADO:
            raise forms.ValidationError(
                "La finalización solo se confirma con la acción explícita."
            )
        return estado


class ConfirmarParticipacionForm(FormularioBootstrapMixin, forms.Form):
    """Confirmación explícita de la finalización (acción autorizada)."""

    fecha_finalizacion = forms.DateField(
        label="Fecha de finalización",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
        initial=fechas.hoy,
    )
    resultado = forms.ChoiceField(
        label="Resultado verificado",
        choices=ResultadoParticipacion.choices,
    )
    observaciones = forms.CharField(
        label="Observaciones",
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
    )
    constancia = forms.FileField(
        label="Constancia digital",
        required=False,
        help_text="Opcional. PDF, JPG o PNG de hasta 5 MB. Cada repetición guarda la suya.",
    )

    def __init__(self, *args, participacion=None, **kwargs):
        self.participacion = participacion
        super().__init__(*args, **kwargs)

    def clean_constancia(self):
        from .models import validar_constancia

        archivo = self.cleaned_data.get("constancia")
        if archivo:
            validar_constancia(archivo)
        return archivo

    def clean(self):
        datos = super().clean()
        inicio = self.participacion.fecha if self.participacion else None
        fin = datos.get("fecha_finalizacion")
        if inicio and fin and fin < inicio:
            self.add_error(
                "fecha_finalizacion",
                "La finalización no puede ser anterior a la inscripción.",
            )
        return datos

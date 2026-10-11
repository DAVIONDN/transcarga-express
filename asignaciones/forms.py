"""Formularios de asignaciones."""

from django import forms

from comun import fechas
from comun.choices import EstadoOferta, EstadoTransportista
from comun.forms import FormularioBootstrapMixin
from ofertas.models import OfertaCarga
from transportistas.models import Transportista

from . import reglas

FORMATOS_FECHA = ["%Y-%m-%d", "%d/%m/%Y"]


class AsignacionForm(FormularioBootstrapMixin, forms.Form):
    """Selección de la oferta y del transportista, con las fechas del servicio.

    Si se construye con `oferta=...`, la oferta queda fija (flujo que parte de la
    ficha de la oferta) y el campo no se muestra; sin ella, se elige entre las
    ofertas Disponibles.
    """

    oferta = forms.ModelChoiceField(
        queryset=OfertaCarga.objects.none(),
        label="Oferta de carga",
        required=False,
    )
    transportista = forms.ModelChoiceField(
        queryset=Transportista.objects.none(),
        label="Transportista",
    )
    fecha_inicio = forms.DateField(
        label="Fecha de inicio",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        input_formats=FORMATOS_FECHA,
        initial=fechas.hoy,
    )
    fecha_fin = forms.DateField(
        label="Fecha de finalización",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        input_formats=FORMATOS_FECHA,
        help_text="Opcional: puede completarse después, al finalizar la asignación.",
    )

    def __init__(self, *args, oferta=None, **kwargs):
        self.oferta_fija = oferta
        super().__init__(*args, **kwargs)

        if oferta is not None:
            self.fields.pop("oferta")
        else:
            self.fields["oferta"].queryset = (
                OfertaCarga.objects.filter(estado=EstadoOferta.DISPONIBLE)
                .select_related("empresa_cliente")
                .order_by("-creado", "-id")
            )
            self.fields["oferta"].required = True
            self.fields["oferta"].label_from_instance = lambda disponible: (
                f"{disponible.codigo} — {disponible.origen} a {disponible.destino} "
                f"(Nivel {disponible.nivel_requerido}, "
                f"{disponible.get_tipo_vehiculo_requerido_display()})"
            )

        # Los transportistas de baja no se ofrecen; el resto se evalúa con las reglas
        # para poder explicar por qué no es elegible.
        self.fields["transportista"].queryset = Transportista.objects.exclude(
            estado=EstadoTransportista.BAJA
        ).order_by("nombre")
        self.fields["transportista"].label_from_instance = lambda transportista: (
            f"{transportista.nombre} — Nivel {transportista.nivel} · "
            f"{transportista.get_tipo_vehiculo_display()} · "
            f"{transportista.capacidad_toneladas} t ({transportista.placa})"
        )

    @property
    def oferta_seleccionada(self):
        if self.oferta_fija is not None:
            return self.oferta_fija
        if hasattr(self, "cleaned_data"):
            return self.cleaned_data.get("oferta")
        return None

    def clean(self):
        datos = super().clean()
        oferta = self.oferta_seleccionada
        transportista = datos.get("transportista")
        inicio = datos.get("fecha_inicio")
        fin = datos.get("fecha_fin")

        if oferta and transportista and not reglas.es_elegible(
            transportista, oferta, fecha_referencia=inicio
        ):
            self.add_error(
                "transportista",
                " ".join(reglas.motivos_no_elegibilidad(transportista, oferta, fecha_referencia=inicio)),
            )
        if inicio and fin and fin < inicio:
            self.add_error(
                "fecha_fin",
                "La fecha de finalización no puede ser anterior a la fecha de inicio.",
            )
        return datos


class FinalizarAsignacionForm(FormularioBootstrapMixin, forms.Form):
    """Registra la fecha de finalización y cierra la asignación."""

    fecha_fin = forms.DateField(
        label="Fecha de finalización",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        input_formats=FORMATOS_FECHA,
        initial=fechas.hoy,
    )

    def __init__(self, *args, asignacion=None, **kwargs):
        self.asignacion = asignacion
        super().__init__(*args, **kwargs)

    def clean_fecha_fin(self):
        fecha_fin = self.cleaned_data["fecha_fin"]
        if self.asignacion and fecha_fin < self.asignacion.fecha_inicio:
            raise forms.ValidationError(
                "La fecha de finalización no puede ser anterior a la fecha de inicio "
                f"({fechas.formatear_fecha(self.asignacion.fecha_inicio)})."
            )
        return fecha_fin


class CancelarAsignacionForm(FormularioBootstrapMixin, forms.Form):
    """Registra la fecha y el motivo de cancelación, dejando constancia sin borrar nada."""

    fecha = forms.DateField(
        label="Fecha de cancelación",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        input_formats=FORMATOS_FECHA,
        initial=fechas.hoy,
        help_text="La asignación no se borra: queda registrada como Cancelada.",
    )
    motivo = forms.CharField(
        label="Motivo de la cancelación",
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Obligatorio: explique por qué no se ejecutó el servicio.",
    )

    def __init__(self, *args, asignacion=None, **kwargs):
        self.asignacion = asignacion
        super().__init__(*args, **kwargs)

    def clean_fecha(self):
        fecha = self.cleaned_data["fecha"]
        if self.asignacion and fecha < self.asignacion.fecha_inicio:
            raise forms.ValidationError(
                "La fecha de cancelación no puede ser anterior a la fecha de inicio "
                f"({fechas.formatear_fecha(self.asignacion.fecha_inicio)})."
            )
        return fecha

    def clean_motivo(self):
        motivo = (self.cleaned_data.get("motivo") or "").strip()
        if not motivo:
            raise forms.ValidationError("Indique el motivo de la cancelación.")
        return motivo

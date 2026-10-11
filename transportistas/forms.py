"""Formularios de transportistas y advertencias (validación del lado del servidor)."""

from django import forms

from asignaciones.models import Asignacion
from clientes.models import EmpresaCliente
from comun import fechas
from comun.choices import EstadoTransportista, TipoDocumento, TipoIncidencia
from comun.forms import FormularioBootstrapMixin

from .models import MAXIMO_ADVERTENCIAS, Advertencia, Incidencia, Transportista


class TransportistaForm(FormularioBootstrapMixin, forms.ModelForm):
    """Alta y edición de transportistas (R1, R2, R3 y R10)."""

    class Meta:
        model = Transportista
        fields = (
            "tipo_documento",
            "numero_documento",
            "nombre",
            "direccion",
            "anios_experiencia",
            "placa",
            "tipo_vehiculo",
            "capacidad_toneladas",
            "certificacion_carga_peligrosa",
            "fecha_vencimiento_licencia",
            "fecha_vencimiento_revision_tecnica",
            "fecha_vencimiento_soat",
            "copia_soat",
            "fotografia_vehiculo",
            "estado",
        )
        widgets = {
            "fecha_vencimiento_licencia": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            ),
            "fecha_vencimiento_revision_tecnica": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            ),
            "fecha_vencimiento_soat": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "copia_soat": forms.ClearableFileInput(attrs={"accept": ".pdf,.jpg,.jpeg,.png"}),
            "fotografia_vehiculo": forms.ClearableFileInput(attrs={"accept": "image/*"}),
            "direccion": forms.TextInput(),
        }
        help_texts = {
            "capacidad_toneladas": "En toneladas. El nivel se calcula automáticamente.",
            "copia_soat": "Opcional. Copia en PDF, JPG o PNG de hasta 5 MB.",
            "fotografia_vehiculo": "Requisito obligatorio. JPG o PNG de hasta 5 MB.",
            "numero_documento": "DNI de 8 dígitos o RUC de 11 dígitos, sin guiones.",
        }
        error_messages = {
            "numero_documento": {
                "unique": "Ya existe un transportista registrado con este número de documento.",
            },
            "placa": {
                "unique": "Ya existe un transportista registrado con esta placa.",
            },
        }

    def clean_numero_documento(self):
        numero = (self.cleaned_data.get("numero_documento") or "").strip()
        tipo = self.cleaned_data.get("tipo_documento")
        if not numero:
            return numero
        if not numero.isdigit():
            raise forms.ValidationError("El número de documento debe contener solo dígitos.")
        if tipo:
            esperado = 8 if tipo == TipoDocumento.DNI else 11
            if len(numero) != esperado:
                raise forms.ValidationError(
                    f"El {dict(TipoDocumento.choices)[tipo]} debe tener {esperado} dígitos."
                )
        return numero

    # La vigencia documental (licencia y revisión técnica con estado Activo) y la
    # normalización de la placa viven en Transportista.clean(): el formulario no las
    # duplica, solo las muestra como errores de campo.


class CambiarEstadoTransportistaForm(FormularioBootstrapMixin, forms.Form):
    """Cambio de estado con las validaciones de activación (R1, R4 y D7)."""

    estado = forms.ChoiceField(label="Nuevo estado", choices=EstadoTransportista.choices)

    def __init__(self, *args, transportista=None, **kwargs):
        self.transportista = transportista
        super().__init__(*args, **kwargs)

    def clean_estado(self):
        nuevo_estado = self.cleaned_data["estado"]
        transportista = self.transportista

        if transportista.esta_de_baja or transportista.esta_baja_pendiente:
            raise forms.ValidationError(
                "Un transportista dado de baja (o en baja pendiente) no puede reactivarse "
                "desde esta pantalla. Solo el panel de administración puede corregir su estado."
            )
        if nuevo_estado == EstadoTransportista.BAJA_PENDIENTE:
            raise forms.ValidationError(
                "La «Baja pendiente» no se asigna manualmente: solo se aplica por la baja "
                "diferida tras la tercera advertencia con excepción del cliente."
            )
        if nuevo_estado == transportista.estado:
            raise forms.ValidationError(
                f"El transportista ya se encuentra en estado «{transportista.get_estado_display()}»."
            )
        if nuevo_estado == EstadoTransportista.ACTIVO:
            faltantes = []
            if not transportista.fotografia_vehiculo:
                faltantes.append("la fotografía del vehículo")
            if not transportista.licencia_vigente:
                faltantes.append("la licencia de conducir vigente")
            if not transportista.revision_tecnica_vigente:
                faltantes.append("la revisión técnica vigente")
            if faltantes:
                raise forms.ValidationError(
                    "No se puede activar el transportista porque falta "
                    + ", ".join(faltantes)
                    + ". Complete la documentación obligatoria antes de activarlo."
                )
        return nuevo_estado


class AdvertenciaForm(FormularioBootstrapMixin, forms.ModelForm):
    """Registro de una advertencia para un transportista (R7 y R8)."""

    class Meta:
        model = Advertencia
        fields = ("fecha", "descripcion", "asignacion")
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "descripcion": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "descripcion": "Descripción del motivo",
        }

    def __init__(self, *args, transportista=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.transportista = transportista
        consulta = Asignacion.objects.none()
        if transportista is not None and transportista.pk:
            consulta = transportista.asignaciones.select_related("oferta")
        self.fields["asignacion"].queryset = consulta
        self.fields["asignacion"].required = False
        self.fields["asignacion"].label_from_instance = (
            lambda asignacion: (
                f"{asignacion.oferta.codigo} — {asignacion.oferta.origen} a "
                f"{asignacion.oferta.destino} ({asignacion.get_estado_display()})"
            )
        )
        self.fields["fecha"].initial = fechas.hoy()

    def clean_descripcion(self):
        return (self.cleaned_data.get("descripcion") or "").strip()

    def save(self, commit=True):
        advertencia = super().save(commit=False)
        if self.transportista is not None:
            advertencia.transportista = self.transportista
        if commit:
            advertencia.save()
        return advertencia

    def aviso_acumulado(self):
        """Mensaje informativo con el total real de advertencias tras el registro.

        Se consulta la base de datos (no el objeto en memoria) para que el aviso y el
        estado de «Baja» siempre coincidan con lo guardado.
        """
        transportista = Transportista.objects.get(pk=self.transportista.pk)
        total = transportista.advertencias.count()
        if transportista.esta_de_baja:
            return (
                f"El transportista alcanzó {total} advertencias (máximo {MAXIMO_ADVERTENCIAS}) "
                "y pasó automáticamente a estado «Baja»: no podrá recibir nuevas asignaciones."
            )
        if transportista.esta_baja_pendiente:
            return (
                f"El transportista alcanzó {total} advertencias (máximo {MAXIMO_ADVERTENCIAS}) "
                "y pasó a estado «Baja pendiente»: solo puede completar su servicio en curso "
                "hasta que se aplique la baja formal."
            )
        return (
            f"Advertencia registrada. El transportista acumula {total} de "
            f"{MAXIMO_ADVERTENCIAS} advertencias permitidas."
        )


class IncidenciaForm(FormularioBootstrapMixin, forms.ModelForm):
    """Registro de una queja, renuncia o excepción a la baja.

    Registrar la incidencia no cambia estados ni crea advertencias solas: la
    advertencia formal nace solo de la conversión explícita.
    """

    class Meta:
        model = Incidencia
        fields = (
            "tipo",
            "fecha",
            "descripcion",
            "empresa_cliente",
            "transportista",
            "asignacion",
            "acuerdo_reemplazo",
        )
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "descripcion": forms.Textarea(attrs={"rows": 3}),
            "acuerdo_reemplazo": forms.Textarea(attrs={"rows": 2}),
        }
        labels = {
            "descripcion": "Descripción del motivo",
            "acuerdo_reemplazo": "Acuerdo de reemplazo (solo renuncias)",
        }
        help_texts = {
            "empresa_cliente": "Obligatoria para las quejas.",
            "asignacion": "Opcional, salvo en la excepción a la baja (contrato en curso).",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["transportista"].queryset = Transportista.objects.order_by("nombre")
        self.fields["empresa_cliente"].queryset = EmpresaCliente.objects.order_by("razon_social")
        self.fields["empresa_cliente"].required = False
        self.fields["asignacion"].queryset = Asignacion.objects.select_related(
            "oferta", "transportista"
        ).order_by("-fecha_inicio", "-id")
        self.fields["asignacion"].required = False
        self.fields["asignacion"].label_from_instance = (
            lambda asignacion: (
                f"{asignacion.oferta.codigo} — {asignacion.transportista.nombre} "
                f"({asignacion.get_estado_display()})"
            )
        )
        self.fields["acuerdo_reemplazo"].required = False
        self.fields["fecha"].initial = fechas.hoy()

    def clean_descripcion(self):
        return (self.cleaned_data.get("descripcion") or "").strip()

    def clean(self):
        datos = super().clean()
        # La coherencia fina (cliente obligatorio en quejas, asignación en la
        # excepción y correspondencia asignación-transportista) vive en el modelo.
        return datos


class VincularReemplazoForm(FormularioBootstrapMixin, forms.Form):
    """Vincula la nueva asignación que cubre el reemplazo, verificándola.

    La nueva asignación debe existir (oferta independiente) y el reemplazo debe
    ser elegible a su fecha de inicio: no se asignan dos transportistas a la
    misma oferta ni se reemplaza silenciosamente.
    """

    nueva_asignacion = forms.ModelChoiceField(
        queryset=Asignacion.objects.none(),
        label="Nueva asignación del reemplazo",
        help_text="Asignación ya registrada sobre una oferta independiente.",
    )

    def __init__(self, *args, incidencia=None, **kwargs):
        self.incidencia = incidencia
        super().__init__(*args, **kwargs)
        self.fields["nueva_asignacion"].queryset = Asignacion.objects.select_related(
            "oferta", "transportista"
        ).order_by("-fecha_inicio", "-id")
        self.fields["nueva_asignacion"].label_from_instance = (
            lambda asignacion: (
                f"{asignacion.oferta.codigo} — {asignacion.transportista.nombre} "
                f"(inicio {fechas.formatear_fecha(asignacion.fecha_inicio)})"
            )
        )

    def clean_nueva_asignacion(self):
        from asignaciones import reglas

        nueva = self.cleaned_data["nueva_asignacion"]
        incidencia = self.incidencia
        if incidencia is None or incidencia.asignacion_id is None:
            raise forms.ValidationError(
                "La incidencia no tiene asignación original: registre primero la "
                "asignación afectada antes de vincular un reemplazo."
            )
        if nueva.pk == incidencia.asignacion_id:
            raise forms.ValidationError(
                "La nueva asignación no puede ser la misma asignación original."
            )
        if nueva.oferta_id == incidencia.asignacion.oferta_id:
            raise forms.ValidationError(
                "Una oferta no admite dos transportistas: el reemplazo debe correr "
                "sobre una oferta independiente."
            )
        motivos = reglas.motivos_reemplazo(nueva, incidencia.transportista_id)
        if motivos:
            raise forms.ValidationError(
                "El reemplazo no es válido: " + " ".join(motivos)
            )
        return nueva

"""Modelos de transportistas y de las advertencias que registran.

Reglas que viven aquí (invariantes de datos):
* R1: documentación obligatoria (número de documento y fotografía son obligatorios;
  con estado Activo, licencia y revisión técnica deben estar vigentes).
* R2: el nivel siempre se deriva de la capacidad; nunca se recibe del usuario.
* R3: una capacidad superior a 20 t exige certificación de carga peligrosa.
* R7: al acumular tres advertencias el transportista pasa automáticamente a Baja.
* Placa y número de documento se validan en formato (sin consultas externas).
"""

import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction

from comun import fechas
from comun.choices import (
    EstadoAsignacion,
    EstadoRevision,
    EstadoTransportista,
    NivelCarga,
    TipoDocumento,
    TipoIncidencia,
    TipoVehiculo,
    nivel_desde_capacidad,
    requiere_certificacion,
)

MAXIMO_ADVERTENCIAS = 3
PESO_MAXIMO_FOTOGRAFIA = 5 * 1024 * 1024  # 5 MB
EXTENSIONES_FOTOGRAFIA = (".jpg", ".jpeg", ".png")
PESO_MAXIMO_COPIA_SOAT = 5 * 1024 * 1024  # 5 MB
EXTENSIONES_COPIA_SOAT = (".pdf", ".jpg", ".jpeg", ".png")

# Placa peruana: 6 caracteres alfanuméricos con guion central opcional
# («ABC-123», «A1B-234», «ABC123»). No se consulta ninguna entidad externa.
PATRON_PLACA = re.compile(r"^[A-Z0-9]{3}-?[A-Z0-9]{3}$")
PATRON_PLACA_SIN_GUION = re.compile(r"^[A-Z0-9]{6}$")
MENSAJE_PLACA = (
    "La placa debe tener 6 caracteres alfanuméricos, con guion central opcional: "
    "«ABC-123» o «A1B-234»."
)


def normalizar_placa(valor):
    """Devuelve la placa en mayúsculas y con guion central: «abc123» → «ABC-123»."""
    if not valor:
        return valor
    limpio = str(valor).strip().upper().replace(" ", "")
    if PATRON_PLACA_SIN_GUION.match(limpio):
        return f"{limpio[:3]}-{limpio[3:]}"
    return limpio


def validar_placa(valor):
    """Valida el formato de la placa sin consultar SUNAT ni ningún registro externo."""
    if valor and not PATRON_PLACA.match(str(valor).strip().upper().replace(" ", "")):
        raise ValidationError(MENSAJE_PLACA)


def validar_fotografia(archivo):
    """Comprueba peso y formato de la fotografía del vehículo."""
    if archivo.size > PESO_MAXIMO_FOTOGRAFIA:
        raise ValidationError("La fotografía del vehículo no debe pesar más de 5 MB.")
    if not archivo.name.lower().endswith(EXTENSIONES_FOTOGRAFIA):
        raise ValidationError("La fotografía del vehículo debe estar en formato JPG o PNG.")


def validar_copia_soat(archivo):
    """Comprueba peso y formato de la copia del SOAT (en el servidor)."""
    if archivo.size > PESO_MAXIMO_COPIA_SOAT:
        raise ValidationError("La copia del SOAT no debe pesar más de 5 MB.")
    if not archivo.name.lower().endswith(EXTENSIONES_COPIA_SOAT):
        raise ValidationError("La copia del SOAT debe estar en formato PDF, JPG o PNG.")


class Transportista(models.Model):
    """Transportista con su único vehículo principal (simplificación del MVP)."""

    tipo_documento = models.CharField(
        "Tipo de documento",
        max_length=3,
        choices=TipoDocumento.choices,
        default=TipoDocumento.DNI,
    )
    numero_documento = models.CharField(
        "Número de documento",
        max_length=15,
        unique=True,
        help_text="DNI de 8 dígitos o RUC de 11 dígitos.",
    )
    nombre = models.CharField(
        "Nombres y apellidos o razón social",
        max_length=150,
    )
    direccion = models.CharField("Dirección", max_length=200)
    anios_experiencia = models.PositiveSmallIntegerField(
        "Años de experiencia",
        default=0,
        validators=[MinValueValidator(0, message="Los años de experiencia no pueden ser negativos.")],
    )

    placa = models.CharField(
        "Placa del vehículo",
        max_length=10,
        unique=True,
        validators=[validar_placa],
        help_text="6 caracteres alfanuméricos: «ABC-123» o «A1B-234».",
    )
    tipo_vehiculo = models.CharField("Tipo de vehículo", max_length=20, choices=TipoVehiculo.choices)
    capacidad_toneladas = models.DecimalField(
        "Capacidad de carga (toneladas)",
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(0.01, message="La capacidad de carga debe ser mayor que cero.")],
    )
    certificacion_carga_peligrosa = models.BooleanField(
        "Certificación de carga peligrosa",
        default=False,
        help_text="Obligatoria cuando la capacidad supera las 20 toneladas (Nivel 1).",
    )
    nivel = models.PositiveSmallIntegerField(
        "Nivel",
        choices=NivelCarga.choices,
        editable=False,
        help_text="Se calcula automáticamente a partir de la capacidad de carga.",
    )

    fecha_vencimiento_licencia = models.DateField("Vencimiento de la licencia de conducir")
    fecha_vencimiento_revision_tecnica = models.DateField("Vencimiento de la revisión técnica")
    fecha_vencimiento_soat = models.DateField("Vencimiento del SOAT")

    fotografia_vehiculo = models.ImageField(
        "Fotografía del vehículo",
        upload_to="vehiculos/%Y/%m/",
        validators=[validar_fotografia],
    )
    copia_soat = models.FileField(
        "Copia del SOAT",
        upload_to="soat/%Y/%m/",
        null=True,
        blank=True,
        validators=[validar_copia_soat],
        help_text="Opcional: copia en PDF, JPG o PNG de hasta 5 MB. No sustituye la fecha de vencimiento.",
    )
    estado = models.CharField(
        "Estado",
        max_length=16,
        choices=EstadoTransportista.choices,
        default=EstadoTransportista.ACTIVO,
    )

    creado = models.DateTimeField("Creado", auto_now_add=True)
    actualizado = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        verbose_name = "Transportista"
        verbose_name_plural = "Transportistas"
        ordering = ["nombre"]
        # Índice útil: el estado se usa en los listados, en el panel y al evaluar
        # candidatos para una oferta. Las claves foráneas ya llevan índice propio.
        indexes = [models.Index(fields=["estado"], name="transportista_estado_idx")]
        permissions = [
            (
                "cambiar_estado_transportista",
                "Puede cambiar el estado de un transportista.",
            ),
        ]

    def __str__(self):
        return f"{self.nombre} — {self.placa}"

    # ------------------------------------------------------------------ reglas
    def calcular_nivel(self):
        """Nivel que corresponde a la capacidad de carga registrada (R2)."""
        return nivel_desde_capacidad(self.capacidad_toneladas)

    def clean(self):
        super().clean()
        errores = {}

        if self.capacidad_toneladas is not None and self.capacidad_toneladas <= 0:
            errores["capacidad_toneladas"] = "La capacidad de carga debe ser mayor que cero."

        # El nivel nunca se acepta desde el formulario: se recalcula (R2).
        self.nivel = self.calcular_nivel()

        if (
            self.capacidad_toneladas is not None
            and requiere_certificacion(self.capacidad_toneladas)
            and not self.certificacion_carga_peligrosa
        ):
            errores["certificacion_carga_peligrosa"] = (
                "La capacidad supera las 20 toneladas (Nivel 1), por lo que la certificación "
                "de carga peligrosa es obligatoria."
            )

        if self.numero_documento and not self.numero_documento.isdigit():
            errores["numero_documento"] = "El número de documento debe contener solo dígitos."
        else:
            esperado = 8 if self.tipo_documento == TipoDocumento.DNI else 11
            if self.numero_documento and len(self.numero_documento) != esperado:
                errores["numero_documento"] = (
                    f"El {self.get_tipo_documento_display()} debe tener {esperado} dígitos."
                )

        # La placa se guarda normalizada: mayúsculas y guion central.
        self.placa = normalizar_placa(self.placa)

        # R1: mientras el transportista esté Activo, la licencia y la revisión técnica
        # deben estar vigentes. Con En Reserva o Baja se permite registrar documentos
        # vencidos (decisión D7/R10 del plan), porque la realidad debe poder registrarse.
        if self.estado == EstadoTransportista.ACTIVO:
            for campo, documento in (
                ("fecha_vencimiento_licencia", "la licencia de conducir"),
                ("fecha_vencimiento_revision_tecnica", "la revisión técnica"),
            ):
                fecha = getattr(self, campo)
                if fecha and not fechas.esta_vigente(fecha):
                    errores[campo] = (
                        f"Para registrar o mantener un transportista como Activo, {documento} debe "
                        f"estar vigente (venció el {fechas.formatear_fecha(fecha)}). Si necesita "
                        "guardar documentación vencida, cambie el estado a «En Reserva» o «Baja»."
                    )

        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        # El nivel y la placa se normalizan siempre, incluso al guardar desde el panel
        # de administración o desde código.
        self.nivel = self.calcular_nivel()
        self.placa = normalizar_placa(self.placa)
        super().save(*args, **kwargs)

    # -------------------------------------------------------------- propiedades
    @property
    def licencia_vigente(self):
        return fechas.esta_vigente(self.fecha_vencimiento_licencia)

    @property
    def revision_tecnica_vigente(self):
        return fechas.esta_vigente(self.fecha_vencimiento_revision_tecnica)

    @property
    def soat_vigente(self):
        return fechas.esta_vigente(self.fecha_vencimiento_soat)

    @property
    def documentacion_completa(self):
        """Requisitos documentales obligatorios para registrar o activar (R1)."""
        return bool(self.fotografia_vehiculo) and self.licencia_vigente and self.revision_tecnica_vigente

    @property
    def placa_normalizada(self):
        """Placa en su forma canónica (mayúsculas y guion central)."""
        return normalizar_placa(self.placa)

    @property
    def advertencias_total(self):
        return self.advertencias.count()

    @property
    def tiene_asignacion_activa(self):
        return self.asignaciones.filter(estado=EstadoAsignacion.ACTIVA).exists()

    @property
    def asignacion_activa(self):
        return self.asignaciones.filter(estado=EstadoAsignacion.ACTIVA).first()

    @property
    def esta_activo(self):
        return self.estado == EstadoTransportista.ACTIVO

    @property
    def esta_de_baja(self):
        return self.estado == EstadoTransportista.BAJA

    @property
    def esta_baja_pendiente(self):
        return self.estado == EstadoTransportista.BAJA_PENDIENTE

    def excepcion_baja_vigente(self):
        """Excepción que difiere la baja: registrada, sin baja aplicada y con
        la asignación afectada aún Activa (contrato en curso)."""
        if self.esta_de_baja:
            return None
        return (
            self.incidencias.filter(
                tipo=TipoIncidencia.EXCEPCION_BAJA,
                asignacion__estado=EstadoAsignacion.ACTIVA,
            )
            .select_related("asignacion", "asignacion__oferta")
            .order_by("-fecha", "-id")
            .first()
        )

    def ultima_excepcion_baja(self):
        """Última excepción registrada, esté o no vigente (para aplicar la baja)."""
        return (
            self.incidencias.filter(tipo=TipoIncidencia.EXCEPCION_BAJA)
            .select_related("asignacion", "asignacion__oferta")
            .order_by("-fecha", "-id")
            .first()
        )

    @transaction.atomic
    def aplicar_baja_por_advertencias(self):
        """Lógica central de la baja por tres advertencias formales.

        La usan `Advertencia.save`, el panel de administración y cualquier otra
        vía que registre advertencias: el conteo sale siempre de la base de
        datos con la fila bloqueada. Devuelve "baja", "baja_pendiente" o None.
        Con excepción vigente, el transportista pasa a «Baja pendiente» para
        terminar únicamente el servicio en curso; sin excepción, a «Baja».
        """
        transportista = Transportista.objects.select_for_update().get(pk=self.pk)
        if (
            transportista.advertencias.count() < MAXIMO_ADVERTENCIAS
            or transportista.estado
            in (EstadoTransportista.BAJA, EstadoTransportista.BAJA_PENDIENTE)
        ):
            return None
        if transportista.excepcion_baja_vigente():
            transportista.estado = EstadoTransportista.BAJA_PENDIENTE
        else:
            transportista.estado = EstadoTransportista.BAJA
        transportista.save(update_fields=["estado", "actualizado"])
        return (
            "baja_pendiente"
            if transportista.esta_baja_pendiente
            else "baja"
        )

    @transaction.atomic
    def aplicar_baja_diferida(self):
        """Aplica la baja formal diferida por la excepción del cliente.

        Exige estado «Baja pendiente» y contrato terminado (la asignación
        afectada ya no está Activa): si el servicio sigue en curso, no aplica
        y lo informa. Al aplicar, deja constancia marcando la excepción como
        revisada. Devuelve (aplicada, mensaje).
        """
        transportista = Transportista.objects.select_for_update().get(pk=self.pk)
        if transportista.estado != EstadoTransportista.BAJA_PENDIENTE:
            return False, "Solo puede aplicarse la baja a un transportista en «Baja pendiente»."
        excepcion = transportista.ultima_excepcion_baja()
        if excepcion is None:
            return False, "No hay una excepción a la baja registrada para este transportista."
        if excepcion.asignacion is not None and excepcion.asignacion.esta_activa:
            return (
                False,
                "El contrato afectado sigue en curso: la baja se aplica cuando el "
                "servicio termine (finalizado o cancelado).",
            )
        transportista.estado = EstadoTransportista.BAJA
        transportista.save(update_fields=["estado", "actualizado"])
        excepcion.estado_revision = EstadoRevision.REVISADA
        excepcion.save(update_fields=["estado_revision"])
        return True, (
            "Baja formal aplicada. El transportista no puede recibir nuevas asignaciones "
            "y su historial se conserva."
        )

    def documentos_por_vencer(self, dias=fechas.DIAS_AVISO_VENCIMIENTO):
        """Devuelve los documentos que vencen dentro de los próximos `dias` días."""
        pendientes = []
        for etiqueta, fecha in (
            ("Licencia de conducir", self.fecha_vencimiento_licencia),
            ("Revisión técnica", self.fecha_vencimiento_revision_tecnica),
            ("SOAT", self.fecha_vencimiento_soat),
        ):
            if fecha and fechas.vence_pronto(fecha, dias):
                pendientes.append((etiqueta, fecha))
        return pendientes

    def documentos_detalle(self, dias=fechas.DIAS_AVISO_VENCIMIENTO):
        """Estado de cada documento obligatorio, calculado desde la fecha actual.

        Devuelve una lista de dictados con codigo, nombre, fecha, estado, dias y
        detalle en español. La fotografía figura como `pendiente` cuando falta;
        las fechas ausentes (defensivo: la columna no admite nulos) también.
        """
        detalle = []
        for codigo, nombre, fecha in (
            ("licencia", "Licencia de conducir", self.fecha_vencimiento_licencia),
            ("revision", "Revisión técnica", self.fecha_vencimiento_revision_tecnica),
            ("soat", "SOAT", self.fecha_vencimiento_soat),
        ):
            estado, restantes = fechas.estado_documento(fecha, dias)
            detalle.append(
                {
                    "codigo": codigo,
                    "nombre": nombre,
                    "fecha": fecha,
                    "estado": estado,
                    "dias": restantes,
                    "detalle": self._texto_estado_documento(nombre, fecha, estado, restantes),
                }
            )
        estado_foto = (
            fechas.ESTADO_VIGENTE if self.fotografia_vehiculo else fechas.ESTADO_PENDIENTE
        )
        detalle.append(
            {
                "codigo": "fotografia",
                "nombre": "Fotografía del vehículo",
                "fecha": None,
                "estado": estado_foto,
                "dias": None,
                "detalle": (
                    "Registrada."
                    if self.fotografia_vehiculo
                    else "Pendiente: súbala desde la edición de la ficha."
                ),
            }
        )
        return detalle

    @staticmethod
    def _texto_estado_documento(nombre, fecha, estado, restantes):
        if estado == fechas.ESTADO_PENDIENTE:
            return f"{nombre}: pendiente, falta registrar la fecha de vencimiento."
        if estado == fechas.ESTADO_VENCIDO:
            return (
                f"{nombre}: vencido el {fechas.formatear_fecha(fecha)} "
                f"(hace {abs(restantes)} día(s)). Regularice la fecha en su ficha."
            )
        if estado == fechas.ESTADO_PROXIMO:
            if restantes == 0:
                return f"{nombre}: vence hoy ({fechas.formatear_fecha(fecha)})."
            return (
                f"{nombre}: vence en {restantes} día(s) "
                f"({fechas.formatear_fecha(fecha)})."
            )
        return f"{nombre}: vigente hasta el {fechas.formatear_fecha(fecha)}."

    def documentos_vencidos(self, dias=fechas.DIAS_AVISO_VENCIMIENTO):
        """Nombres de los documentos obligatorios vencidos."""
        return [d["nombre"] for d in self.documentos_detalle(dias) if d["estado"] == fechas.ESTADO_VENCIDO]

    def documentos_proximos(self, dias=fechas.DIAS_AVISO_VENCIMIENTO):
        """Nombres de los documentos obligatorios próximos a vencer (sin contar vencidos)."""
        return [d["nombre"] for d in self.documentos_detalle(dias) if d["estado"] == fechas.ESTADO_PROXIMO]

    def documentos_pendientes(self, dias=fechas.DIAS_AVISO_VENCIMIENTO):
        """Nombres de los documentos obligatorios pendientes de información."""
        return [d["nombre"] for d in self.documentos_detalle(dias) if d["estado"] == fechas.ESTADO_PENDIENTE]

    @property
    def alerta_documental(self):
        """True si algún documento obligatorio está vencido o pendiente.

        Es un aviso operativo: no cambia estados ni crea advertencias solas.
        """
        return bool(self.documentos_vencidos() or self.documentos_pendientes())


class Advertencia(models.Model):
    """Advertencia registrada a un transportista (R7 y R8)."""

    fecha = models.DateField("Fecha", default=fechas.hoy)
    descripcion = models.TextField("Descripción")
    transportista = models.ForeignKey(
        Transportista,
        on_delete=models.PROTECT,
        related_name="advertencias",
        verbose_name="Transportista",
    )
    asignacion = models.ForeignKey(
        "asignaciones.Asignacion",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="advertencias",
        verbose_name="Asignación relacionada",
        help_text="Opcional: complete solo si la advertencia se originó en una asignación.",
    )
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="advertencias_registradas",
        verbose_name="Registrado por",
    )
    creado = models.DateTimeField("Creado", auto_now_add=True)

    class Meta:
        verbose_name = "Advertencia"
        verbose_name_plural = "Advertencias"
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"Advertencia del {fechas.formatear_fecha(self.fecha)} a {self.transportista.nombre}"

    def clean(self):
        super().clean()
        if (
            self.asignacion_id
            and self.transportista_id
            and self.asignacion.transportista_id != self.transportista_id
        ):
            raise ValidationError(
                {"asignacion": "La asignación seleccionada no corresponde al transportista indicado."}
            )

    @transaction.atomic
    def save(self, *args, **kwargs):
        """Guarda la advertencia y aplica el límite en una sola transacción.

        Así el registro de la tercera advertencia y el cambio de estado a Baja se
        confirman juntos: si algo falla, no queda ninguno de los dos.
        """
        super().save(*args, **kwargs)
        self.aplicar_limite_advertencias()

    def aplicar_limite_advertencias(self):
        """Pasa el transportista a Baja (o Baja pendiente con excepción) al
        alcanzar el máximo de advertencias (R7).

        Delega en la lógica central `Transportista.aplicar_baja_por_advertencias`
        para que todas las vías compartan la misma transición. Devuelve True si
        se aplicó alguna baja en esta llamada.
        """
        transportista = Transportista.objects.get(pk=self.transportista_id)
        return transportista.aplicar_baja_por_advertencias() is not None


class Incidencia(models.Model):
    """Queja, renuncia o excepción a la baja vinculadas a un transportista.

    Una queja recibida NO es una advertencia formal: solo genera una advertencia
    (que sí cuenta hacia la baja) cuando un usuario autorizado la convierte
    expresamente. La renuncia se registra sin cambiar estados por sí sola; el
    retorno al grupo activo se hace con la acción explícita de cambio de estado.
    La excepción a la baja queda registrada de forma explícita (decisión del
    cliente, fecha, responsable y asignación afectada); su tratamiento diferido
    está pendiente de confirmación (P2) y hoy no altera la baja automática.
    """

    tipo = models.CharField(
        "Tipo de incidencia",
        max_length=15,
        choices=TipoIncidencia.choices,
        default=TipoIncidencia.QUEJA,
    )
    fecha = models.DateField("Fecha", default=fechas.hoy)
    descripcion = models.TextField(
        "Descripción",
        help_text="Queja: lo reportado por el cliente. Renuncia: motivo del transportista. "
        "Excepción: decisión del cliente que rechaza el reemplazo inmediato.",
    )
    empresa_cliente = models.ForeignKey(
        "clientes.EmpresaCliente",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="incidencias",
        verbose_name="Empresa cliente",
        help_text="Obligatoria para las quejas.",
    )
    transportista = models.ForeignKey(
        Transportista,
        on_delete=models.PROTECT,
        related_name="incidencias",
        verbose_name="Transportista",
    )
    asignacion = models.ForeignKey(
        "asignaciones.Asignacion",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="incidencias",
        verbose_name="Asignación relacionada",
        help_text="Opcional, salvo en la excepción a la baja (asignación afectada).",
    )
    estado_revision = models.CharField(
        "Estado de revisión",
        max_length=10,
        choices=EstadoRevision.choices,
        default=EstadoRevision.PENDIENTE,
    )
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="incidencias_registradas",
        verbose_name="Registrado por",
    )
    advertencia_generada = models.OneToOneField(
        Advertencia,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="incidencia_origen",
        verbose_name="Advertencia generada",
        help_text="Como máximo una advertencia formal por incidencia (evita duplicados).",
    )
    acuerdo_reemplazo = models.TextField(
        "Acuerdo de reemplazo",
        blank=True,
        default="",
        help_text="Renuncia: acuerdo alcanzado sobre el reemplazo, si lo hay.",
    )
    transportista_reemplazo = models.ForeignKey(
        Transportista,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reemplazos_asignados",
        verbose_name="Transportista de reemplazo",
    )
    nueva_asignacion = models.ForeignKey(
        "asignaciones.Asignacion",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reemplazos_origen",
        verbose_name="Nueva asignación del reemplazo",
        help_text="Asignación independiente (nueva oferta) que cubre el reemplazo.",
    )
    creado = models.DateTimeField("Creado", auto_now_add=True)

    class Meta:
        verbose_name = "Incidencia"
        verbose_name_plural = "Incidencias"
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"{self.get_tipo_display()} del {fechas.formatear_fecha(self.fecha)} a {self.transportista.nombre}"

    def clean(self):
        super().clean()
        errores = {}
        if (
            self.asignacion_id
            and self.transportista_id
            and self.asignacion.transportista_id != self.transportista_id
        ):
            errores["asignacion"] = (
                "La asignación seleccionada no corresponde al transportista indicado."
            )
        if self.tipo == TipoIncidencia.QUEJA and not self.empresa_cliente_id:
            errores["empresa_cliente"] = "La queja debe indicar la empresa cliente que reporta."
        if self.tipo == TipoIncidencia.EXCEPCION_BAJA and not self.asignacion_id:
            errores["asignacion"] = (
                "La excepción debe indicar la asignación afectada (contrato en curso)."
            )
        if errores:
            raise ValidationError(errores)

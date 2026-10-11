"""Reglas de elegibilidad y creación de asignaciones.

Es la única fuente de verdad de las reglas R5, R6 y R11: la usan el formulario,
las vistas, el panel de administración y las pruebas.
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from comun import fechas
from comun.choices import (
    EstadoAsignacion,
    EstadoOferta,
    EstadoTransportista,
    NivelCarga,
)
from ofertas.models import OfertaCarga
from transportistas.models import Transportista

from .models import Asignacion


def motivos_no_elegibilidad(transportista, oferta, fecha_referencia=None):
    """Motivos (en español) por los que el transportista no puede cubrir la oferta.

    Se evalúan en el servidor (formulario, vista y pruebas) y cada motivo indica,
    además, cómo resolverlo. La vigencia documental se comprueba en
    `fecha_referencia` cuando es posterior a hoy (normalmente la fecha de inicio
    del servicio): no se crea la asignación si un documento obligatorio vence
    antes del inicio, aunque hoy siga vigente. Con inicio pasado o sin fecha, se
    evalúa contra hoy.
    """
    motivos = []
    referencia = max(fechas.hoy(), fecha_referencia or fechas.hoy())
    al_inicio = referencia > fechas.hoy()
    texto_referencia = (
        f"a la fecha de inicio del servicio ({fechas.formatear_fecha(referencia)})"
        if al_inicio
        else "hoy"
    )

    # 1. Estado del transportista
    if transportista.estado == EstadoTransportista.BAJA:
        motivos.append(
            "El transportista está dado de baja (acumuló 3 advertencias) y no puede recibir "
            "asignaciones. Solo el panel de administración puede corregir su estado."
        )
    elif transportista.estado == EstadoTransportista.BAJA_PENDIENTE:
        motivos.append(
            "El transportista está en «Baja pendiente»: solo puede completar el servicio "
            "que ya tiene en curso y no puede recibir nuevas asignaciones hasta que se "
            "aplique su baja formal."
        )
    elif transportista.estado == EstadoTransportista.EN_RESERVA:
        motivos.append(
            "El transportista está En Reserva y no puede recibir nuevas asignaciones. Cambie su "
            "estado a «Activo» desde su ficha antes de asignarle una oferta."
        )
    elif transportista.estado != EstadoTransportista.ACTIVO:
        motivos.append(
            f"El transportista está en estado «{transportista.get_estado_display()}»: solo un "
            "transportista Activo puede recibir asignaciones."
        )

    # 2. Documentación obligatoria completa y vigente al inicio del servicio
    if not transportista.fotografia_vehiculo:
        motivos.append(
            "Al transportista le falta la fotografía del vehículo. Súbala desde su ficha antes "
            "de asignarle una oferta."
        )
    if not fechas.vigente_en(transportista.fecha_vencimiento_licencia, referencia):
        motivos.append(
            "La licencia de conducir del transportista no está vigente "
            f"{texto_referencia} "
            f"(vence el {fechas.formatear_fecha(transportista.fecha_vencimiento_licencia)}). "
            "Actualice la fecha en su ficha antes de asignar."
        )
    if not fechas.vigente_en(transportista.fecha_vencimiento_revision_tecnica, referencia):
        motivos.append(
            "La revisión técnica del transportista no está vigente "
            f"{texto_referencia} "
            f"(vence el {fechas.formatear_fecha(transportista.fecha_vencimiento_revision_tecnica)}). "
            "Actualice la fecha en su ficha antes de asignar."
        )

    # 3. SOAT vigente al inicio del servicio: sin SOAT no se inicia la ruta
    if not fechas.vigente_en(transportista.fecha_vencimiento_soat, referencia):
        motivos.append(
            "El SOAT del transportista está vencido "
            f"{texto_referencia} "
            f"(vence el {fechas.formatear_fecha(transportista.fecha_vencimiento_soat)}); no se "
            "puede asignar. Actualice la fecha del SOAT en su ficha."
        )

    # 4. Compatibilidad de nivel y tipo de vehículo
    if transportista.nivel != oferta.nivel_requerido:
        motivos.append(
            f"El nivel del transportista (Nivel {transportista.nivel}) no coincide con el nivel "
            f"requerido por la oferta (Nivel {oferta.nivel_requerido}). Elija un transportista "
            "con el nivel requerido."
        )

    if transportista.tipo_vehiculo != oferta.tipo_vehiculo_requerido:
        motivos.append(
            f"El tipo de vehículo del transportista "
            f"({transportista.get_tipo_vehiculo_display()}) no coincide con el requerido "
            f"({oferta.get_tipo_vehiculo_requerido_display()}). Elija un transportista con el "
            "vehículo requerido."
        )

    # 5. Nivel 1: certificación de carga peligrosa obligatoria
    if oferta.nivel_requerido == NivelCarga.NIVEL_1 and not transportista.certificacion_carga_peligrosa:
        motivos.append(
            "La oferta es de Nivel 1 y el transportista no cuenta con certificación de carga "
            "peligrosa. Registre la certificación en su ficha o asigne una oferta de otro nivel."
        )

    # 6. Una sola asignación activa por transportista
    if transportista.tiene_asignacion_activa:
        motivos.append(
            "El transportista ya tiene una asignación activa. Finalice o cancele esa asignación "
            "antes de crear otra."
        )

    # 7. La oferta debe estar Disponible
    if oferta.estado == EstadoOferta.CUBIERTA:
        motivos.append(
            "La oferta ya está cubierta por otra asignación. Cree una oferta nueva para esta "
            "carga."
        )

    return motivos


def es_elegible(transportista, oferta, fecha_referencia=None):
    return not motivos_no_elegibilidad(transportista, oferta, fecha_referencia)


def motivos_reemplazo(nueva_asignacion, sustituido_id):
    """Motivos por los que una asignación existente no vale como reemplazo.

    A diferencia de `motivos_no_elegibilidad`, aquí la nueva asignación ya
    existe: no se exige que su oferta esté Disponible ni se cuenta su propia
    asignación activa. Sí se verifican compatibilidad (nivel, vehículo,
    certificación), disponibilidad (sin otra activa además de esta),
    documentación vigente a su fecha de inicio y que el reemplazo sea otra
    persona y no esté dado de baja.
    """
    motivos = []
    reemplazo = nueva_asignacion.transportista
    oferta = nueva_asignacion.oferta
    inicio = nueva_asignacion.fecha_inicio
    texto_inicio = f"a la fecha de inicio del servicio ({fechas.formatear_fecha(inicio)})"

    if reemplazo.pk == sustituido_id:
        motivos.append(
            "El reemplazo debe ser otro transportista, no el sustituido."
        )
    if reemplazo.estado == EstadoTransportista.BAJA:
        motivos.append(
            "El transportista de reemplazo está dado de baja y no puede operar."
        )
    elif reemplazo.estado != EstadoTransportista.ACTIVO:
        motivos.append(
            "El transportista de reemplazo no está Activo y no puede operar."
        )
    if not reemplazo.fotografia_vehiculo:
        motivos.append("Al reemplazo le falta la fotografía del vehículo.")
    if not fechas.vigente_en(reemplazo.fecha_vencimiento_licencia, inicio):
        motivos.append(
            "La licencia de conducir del reemplazo no está vigente "
            f"{texto_inicio}."
        )
    if not fechas.vigente_en(reemplazo.fecha_vencimiento_revision_tecnica, inicio):
        motivos.append(
            f"La revisión técnica del reemplazo no está vigente {texto_inicio}."
        )
    if not fechas.vigente_en(reemplazo.fecha_vencimiento_soat, inicio):
        motivos.append(f"El SOAT del reemplazo no está vigente {texto_inicio}.")
    if reemplazo.nivel != oferta.nivel_requerido:
        motivos.append(
            f"El nivel del reemplazo (Nivel {reemplazo.nivel}) no coincide con el nivel "
            f"requerido por la oferta (Nivel {oferta.nivel_requerido})."
        )
    if reemplazo.tipo_vehiculo != oferta.tipo_vehiculo_requerido:
        motivos.append(
            "El tipo de vehículo del reemplazo no coincide con el requerido por la oferta."
        )
    if oferta.nivel_requerido == NivelCarga.NIVEL_1 and not reemplazo.certificacion_carga_peligrosa:
        motivos.append(
            "La oferta es de Nivel 1 y el reemplazo no tiene certificación de carga peligrosa."
        )
    if (
        reemplazo.asignaciones.filter(estado=EstadoAsignacion.ACTIVA)
        .exclude(pk=nueva_asignacion.pk)
        .exists()
    ):
        motivos.append(
            "El reemplazo tiene otra asignación activa además de esta."
        )
    return motivos


def candidatos(oferta, incluir_baja=False, fecha_referencia=None):
    """Lista de transportistas evaluados para una oferta, con sus motivos."""
    consulta = Transportista.objects.order_by("nombre")
    if not incluir_baja:
        consulta = consulta.exclude(estado=EstadoTransportista.BAJA)
    resultado = []
    for transportista in consulta:
        motivos = motivos_no_elegibilidad(transportista, oferta, fecha_referencia)
        resultado.append(
            {
                "transportista": transportista,
                "motivos": motivos,
                "elegible": not motivos,
            }
        )
    return resultado


@transaction.atomic
def crear_asignacion(*, transportista, oferta, fecha_inicio, fecha_fin=None):
    """Crea la asignación y marca la oferta como Cubierta en una sola transacción.

    Vuelve a evaluar las reglas con los registros bloqueados para evitar que dos
    operadores cubran la misma oferta o asignen dos veces al mismo transportista.
    """
    oferta = OfertaCarga.objects.select_for_update().get(pk=oferta.pk)
    transportista = Transportista.objects.select_for_update().get(pk=transportista.pk)

    # La asignación creada y la ruta iniciada no se confunden: la vigencia se
    # exige a la fecha de inicio del servicio, no solo al crear el registro.
    motivos = motivos_no_elegibilidad(transportista, oferta, fecha_referencia=fecha_inicio)
    if motivos:
        raise ValidationError(motivos)

    asignacion = Asignacion(
        transportista=transportista,
        oferta=oferta,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        estado=EstadoAsignacion.ACTIVA,
    )
    asignacion.full_clean()
    asignacion.save()

    oferta.estado = EstadoOferta.CUBIERTA
    oferta.save(update_fields=["estado", "actualizado"])
    return asignacion

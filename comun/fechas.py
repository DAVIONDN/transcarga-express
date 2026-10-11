"""Utilidades de fechas y vigencia de documentos.

Todas las comparaciones usan la fecha local (America/Lima) para que las reglas
de vigencia sean consistentes con lo que ve el usuario.
"""

from datetime import datetime

from django.utils import timezone

# Días de anticipación con los que el panel avisa de un vencimiento próximo.
# Es el umbral documentado de «próximo a vencer»: un aviso operativo, no una
# fecha legal de vencimiento (la vigencia real la da la fecha del documento).
DIAS_AVISO_VENCIMIENTO = 30

# Estados de un documento obligatorio, calculados siempre desde la fecha actual
ESTADO_VIGENTE = "vigente"
ESTADO_PROXIMO = "proximo"
ESTADO_VENCIDO = "vencido"
ESTADO_PENDIENTE = "pendiente"

ETIQUETAS_ESTADO_DOCUMENTO = {
    ESTADO_VIGENTE: "Vigente",
    ESTADO_PROXIMO: "Próximo a vencer",
    ESTADO_VENCIDO: "Vencido",
    ESTADO_PENDIENTE: "Pendiente",
}

# Formatos aceptados al interpretar una fecha escrita (filtros de listados)
FORMATOS_ENTRADA = ("%Y-%m-%d", "%d/%m/%Y")


def interpretar_fecha(texto):
    """Convierte una fecha escrita en `date`; devuelve None si no es válida."""
    if not texto:
        return None
    for formato in FORMATOS_ENTRADA:
        try:
            return datetime.strptime(str(texto).strip(), formato).date()
        except (TypeError, ValueError):
            continue
    return None


def hoy():
    """Fecha actual en la zona horaria local del proyecto."""
    return timezone.localdate()


def esta_vigente(fecha_vencimiento):
    """True si la fecha existe y no ha vencido (vence hoy todavía cuenta como vigente)."""
    if not fecha_vencimiento:
        return False
    return fecha_vencimiento >= hoy()


def vigente_en(fecha_vencimiento, referencia):
    """True si el documento está vigente en la fecha de referencia dada.

    Permite comprobar la vigencia al inicio del servicio y no solo hoy: vencer
    el día de referencia todavía cuenta como vigente.
    """
    if not fecha_vencimiento or not referencia:
        return False
    return fecha_vencimiento >= referencia


def dias_para_vencer(fecha_vencimiento):
    """Días restantes hasta el vencimiento (negativo si ya venció)."""
    if not fecha_vencimiento:
        return None
    return (fecha_vencimiento - hoy()).days


def vence_pronto(fecha_vencimiento, dias=DIAS_AVISO_VENCIMIENTO):
    """True si la fecha vence dentro de los próximos `dias` días (incluye vencidas)."""
    if not fecha_vencimiento:
        return False
    return fecha_vencimiento <= hoy() + timezone.timedelta(days=dias)


def estado_documento(fecha_vencimiento, dias=DIAS_AVISO_VENCIMIENTO):
    """Estado de un documento obligatorio calculado desde la fecha actual.

    Devuelve (codigo, dias_restantes): `pendiente` si falta la fecha, `vencido`
    si ya pasó (vencer hoy cuenta como vigente), `proximo` si vence dentro del
    umbral y `vigente` en los demás casos. Nadie escribe el estado a mano.
    """
    if not fecha_vencimiento:
        return ESTADO_PENDIENTE, None
    restantes = dias_para_vencer(fecha_vencimiento)
    if restantes < 0:
        return ESTADO_VENCIDO, restantes
    if restantes <= dias:
        return ESTADO_PROXIMO, restantes
    return ESTADO_VIGENTE, restantes


def formatear_fecha(fecha):
    """Formato corto dd/mm/aaaa para mensajes y plantillas."""
    if not fecha:
        return "—"
    return fecha.strftime("%d/%m/%Y")


def texto_vigencia(fecha_vencimiento):
    """Describe la vigencia en español, con los días restantes."""
    if not fecha_vencimiento:
        return "sin fecha registrada"
    dias = dias_para_vencer(fecha_vencimiento)
    if dias < 0:
        return f"vencido el {formatear_fecha(fecha_vencimiento)} (hace {abs(dias)} día(s))"
    if dias == 0:
        return f"vence hoy ({formatear_fecha(fecha_vencimiento)})"
    return f"vigente hasta el {formatear_fecha(fecha_vencimiento)} ({dias} día(s))"

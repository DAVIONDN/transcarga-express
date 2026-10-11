"""Cálculos de formatos semanales y liquidaciones (funciones puras).

Zona horaria de la empresa: America/Lima, siempre vía `comun.fechas.hoy()`.
Semana: lunes a domingo; la firma prevista es el viernes de cada semana de
servicio. Decisiones documentadas como pendientes (el caso no las especifica):
conteo de semanas de retraso por techo, prorrateo igualitario con el resto en
la última semana y sentido de la comisión (descuento al transportista).
"""

from datetime import timedelta
from decimal import Decimal, ROUND_DOWN

from comun import fechas

DIAS_POR_SEMANA = 7
DIA_FIRMA = 4  # viernes, con lunes = 0


def lunes_de(fecha):
    """Lunes de la semana que contiene a `fecha`."""
    return fecha - timedelta(days=fecha.weekday())


def viernes_previsto(inicio, lunes):
    """Viernes de firma de la semana que empieza el `lunes` dado.

    Si ese viernes es anterior al inicio del servicio, se pasa al viernes
    siguiente: la primera firma nunca vence antes de empezar.
    """
    viernes = lunes + timedelta(days=DIA_FIRMA)
    if viernes < inicio:
        viernes += timedelta(days=DIAS_POR_SEMANA)
    return viernes


def semanas_servicio(fecha_inicio, fecha_fin=None):
    """Semanas (lunes, domingo, viernes de firma) que cubren el servicio.

    Para asignaciones en curso se usa la fecha actual como fin provisional;
    al invocar de nuevo solo se crean las semanas que falten (idempotente).
    """
    fin = fecha_fin or fechas.hoy()
    if fin < fecha_inicio:
        return []
    semanas = []
    lunes = lunes_de(fecha_inicio)
    while lunes <= fin:
        semanas.append(
            (lunes, lunes + timedelta(days=6), viernes_previsto(fecha_inicio, lunes))
        )
        lunes += timedelta(days=DIAS_POR_SEMANA)
    return semanas


def duracion_dias(fecha_inicio, fecha_fin=None):
    """Días calendario cubiertos por el servicio (inclusivo); sin fecha de fin
    se usa la fecha actual."""
    return ((fecha_fin or fechas.hoy()) - fecha_inicio).days + 1


def exento_por_duracion_corta(fecha_inicio, fecha_fin=None):
    """Contratos inferiores a una semana: firman el viernes sin penalidad."""
    return duracion_dias(fecha_inicio, fecha_fin) < DIAS_POR_SEMANA


def semanas_retraso(fecha_prevista, fecha_firma):
    """Semanas completas o parciales de retraso (por techo).

    Firmar hasta el viernes inclusive no genera retraso. Criterio adoptado
    porque el caso solo dice «penalidad por semana de retraso» (pendiente).
    """
    if not fecha_firma or fecha_firma <= fecha_prevista:
        return 0
    return ((fecha_firma - fecha_prevista).days + DIAS_POR_SEMANA - 1) // DIAS_POR_SEMANA


def bases_semanales(remuneracion, cantidad):
    """Prorrateo igualitario de la remuneración entre las semanas del servicio.

    Cada parte se trunca a céntimos y el resto queda en la última semana, de
    modo que la suma es exacta. Criterio adoptado (pendiente): la única fuente
    de verdad del importe es `OfertaCarga.remuneracion`.
    """
    if cantidad <= 0:
        return []
    total = Decimal(remuneracion)
    parte = (total / cantidad).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    partes = [parte] * cantidad
    partes[-1] += total - sum(partes)
    return partes

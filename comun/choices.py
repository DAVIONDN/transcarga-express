"""Catálogos y reglas de clasificación compartidas por las aplicaciones.

Se mantienen aquí para que el modelo, los formularios, las vistas y las pruebas
usen exactamente la misma fuente de verdad.
"""

from decimal import Decimal

from django.db import models

# Límites de capacidad (en toneladas) que definen los niveles de carga
CAPACIDAD_MINIMA_NIVEL_2 = Decimal("5")
CAPACIDAD_MAXIMA_NIVEL_2 = Decimal("20")


class TipoDocumento(models.TextChoices):
    DNI = "DNI", "DNI"
    RUC = "RUC", "RUC"


class TipoVehiculo(models.TextChoices):
    CAMIONETA = "CAMIONETA", "Camioneta"
    FURGON = "FURGON", "Furgón"
    CAMION = "CAMION", "Camión"
    TRAILER = "TRAILER", "Tráiler"
    CISTERNA = "CISTERNA", "Cisterna"
    VOLQUETE = "VOLQUETE", "Volquete"


class NivelCarga(models.IntegerChoices):
    NIVEL_1 = 1, "Nivel 1 (más de 20 t, exige certificación de carga peligrosa)"
    NIVEL_2 = 2, "Nivel 2 (de 5 a 20 t inclusive)"
    NIVEL_3 = 3, "Nivel 3 (menos de 5 t)"


class EstadoTransportista(models.TextChoices):
    ACTIVO = "ACTIVO", "Activo"
    EN_RESERVA = "EN_RESERVA", "En Reserva"
    BAJA = "BAJA", "Baja"
    BAJA_PENDIENTE = "BAJA_PENDIENTE", "Baja pendiente"


class EstadoOferta(models.TextChoices):
    DISPONIBLE = "DISPONIBLE", "Disponible"
    CUBIERTA = "CUBIERTA", "Cubierta"


class EstadoAsignacion(models.TextChoices):
    ACTIVA = "ACTIVA", "Activa"
    FINALIZADA = "FINALIZADA", "Finalizada"
    CANCELADA = "CANCELADA", "Cancelada"


class TipoIncidencia(models.TextChoices):
    QUEJA = "QUEJA", "Queja de empresa cliente"
    RENUNCIA = "RENUNCIA", "Renuncia voluntaria"
    EXCEPCION_BAJA = "EXCEPCION_BAJA", "Excepción a la baja (rechazo de reemplazo)"


class EstadoRevision(models.TextChoices):
    PENDIENTE = "PENDIENTE", "Pendiente de revisión"
    REVISADA = "REVISADA", "Revisada"


class EstadoCurso(models.TextChoices):
    ACTIVO = "ACTIVO", "Activo"
    INACTIVO = "INACTIVO", "Inactivo"


class EstadoParticipacion(models.TextChoices):
    INSCRITO = "INSCRITO", "Inscrito"
    EN_PROGRESO = "EN_PROGRESO", "En progreso"
    COMPLETADO = "COMPLETADO", "Completado"


class ResultadoParticipacion(models.TextChoices):
    APROBADO = "APROBADO", "Aprobado"
    DESAPROBADO = "DESAPROBADO", "Desaprobado"


# Reglas de clasificación (valores en toneladas)
NIVEL_POR_CAPACIDAD = (
    (NivelCarga.NIVEL_3, Decimal("5")),
    (NivelCarga.NIVEL_2, Decimal("20")),
    (NivelCarga.NIVEL_1, None),
)


def nivel_desde_capacidad(capacidad):
    """Devuelve el nivel que corresponde a una capacidad en toneladas.

    Nivel 3: menos de 5 t. Nivel 2: de 5 a 20 t inclusive.
    Nivel 1: más de 20 t (exige certificación de carga peligrosa).
    """
    if capacidad is None:
        return None
    capacidad = Decimal(capacidad)
    if capacidad < CAPACIDAD_MINIMA_NIVEL_2:
        return NivelCarga.NIVEL_3
    if capacidad <= CAPACIDAD_MAXIMA_NIVEL_2:
        return NivelCarga.NIVEL_2
    return NivelCarga.NIVEL_1


def requiere_certificacion(capacidad):
    """Indica si una capacidad obliga a contar con certificación de carga peligrosa."""
    return nivel_desde_capacidad(capacidad) == NivelCarga.NIVEL_1

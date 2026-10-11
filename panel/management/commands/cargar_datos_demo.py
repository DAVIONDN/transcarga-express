"""Carga datos ficticios de demostración (comando idempotente).

No crea usuarios ni contraseñas: para entrar al sistema use `createsuperuser`.
Se puede ejecutar varias veces: omite lo que ya existe y nunca borra ni modifica
registros previos. Nombres, documentos y RUC son inventados para la demostración
y no corresponden a personas ni empresas reales.

Conjunto ampliado (para poder probar todos los casos del MVP):

* 6 empresas clientes y 17 transportistas (niveles 1, 2 y 3; estados Activo,
  En Reserva y Baja; documentación vigente, por vencer y vencida; DNI y RUC;
  0 años de experiencia; una baja administrativa sin advertencias).
* 18 ofertas de carga: disponibles y cubiertas, de los tres niveles y de todos
  los tipos de vehículo.
* 7 asignaciones: activas, finalizadas y canceladas (el historial se conserva).
* 10 advertencias: transportistas con 1, 2 y 3 advertencias, de modo que se vea
  la baja automática y también un transportista que sigue habilitado.
* 2 cursos con 3 participaciones (inscrita, en progreso y completada aprobada
  sin constancia, para ver el aviso de carga pendiente).
* 2 incidencias: una queja pendiente de revisión (sin advertencia formal) y una
  renuncia con acuerdo de reemplazo.
* Formatos semanales de las asignaciones finalizadas (uno regularizado) con sus
  liquidaciones en borrador. Los parámetros financieros quedan sin configurar:
  no se inventan valores comerciales y el cierre sigue bloqueado.
"""

from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from PIL import Image

from asignaciones import reglas
from asignaciones.models import Asignacion
from capacitacion.models import Curso, Participacion
from clientes.models import EmpresaCliente
from comun.choices import (
    EstadoAsignacion,
    EstadoOferta,
    EstadoParticipacion,
    EstadoTransportista,
    NivelCarga,
    ResultadoParticipacion,
    TipoDocumento,
    TipoIncidencia,
    TipoVehiculo,
)
from liquidaciones import calculos as calculos_liquidacion
from liquidaciones.models import EstadoFormato, FormatoSemanal, Liquidacion
from ofertas.models import OfertaCarga
from transportistas.models import (
    MAXIMO_ADVERTENCIAS,
    Advertencia,
    Incidencia,
    Transportista,
)

# --------------------------------------------------------------------- catálogos

EMPRESAS = [
    {
        "ruc": "20100070970",
        "razon_social": "Distribuidora Andina S.A.C.",
        "direccion": "Av. Argentina 1234, Lima",
        "actividad_economica": "Comercio al por mayor de alimentos",
    },
    {
        "ruc": "20481234567",
        "razon_social": "Agroexport del Sur S.R.L.",
        "direccion": "Panamericana Sur km 32, Ica",
        "actividad_economica": "Agroexportación",
    },
    {
        "ruc": "20556677889",
        "razon_social": "Minera Andina del Cobre S.A.",
        "direccion": "Av. Los Minerales 500, Arequipa",
        "actividad_economica": "Minería",
    },
    {
        "ruc": "20601122334",
        "razon_social": "Frío del Pacífico S.A.C.",
        "direccion": "Av. Elmer Faucett 780, Callao",
        "actividad_economica": "Cadena de frío y productos refrigerados",
    },
    {
        "ruc": "20709988776",
        "razon_social": "Ferretería Industrial Lima S.A.",
        "direccion": "Av. Aviación 2450, Lima",
        "actividad_economica": "Comercio de materiales de construcción",
    },
    {
        "ruc": "20805544332",
        "razon_social": "Agroindustrial Piura S.R.L.",
        "direccion": "Carretera Piura–Sullana km 12, Piura",
        "actividad_economica": "Agroindustria y exportación",
    },
]

# Documentos: días desde hoy (negativos = ya vencidos, positivos = vigentes)
TRANSPORTISTAS = [
    {
        "numero_documento": "40123456",
        "nombre": "Carlos Mendoza Ríos",
        "direccion": "Jr. Las Begonias 245, Lima",
        "anios_experiencia": 14,
        "placa": "V1A-201",
        "tipo_vehiculo": TipoVehiculo.TRAILER,
        "capacidad_toneladas": Decimal("32.00"),
        "certificacion_carga_peligrosa": True,
        "estado": EstadoTransportista.ACTIVO,
        "licencia": 240,
        "revision": 150,
        "soat": 75,
        "color": (13, 110, 253),
    },
    {
        "numero_documento": "41234567",
        "nombre": "María Fernanda Quispe Rojas",
        "direccion": "Av. Universitaria 1520, Lima",
        "anios_experiencia": 9,
        "placa": "C2B-415",
        "tipo_vehiculo": TipoVehiculo.CAMION,
        "capacidad_toneladas": Decimal("18.00"),
        "certificacion_carga_peligrosa": False,
        "estado": EstadoTransportista.ACTIVO,
        "licencia": 200,
        "revision": 120,
        "soat": 45,
        "color": (25, 135, 84),
    },
    {
        "numero_documento": "42345678",
        "nombre": "Luis Alberto Huamán Castro",
        "direccion": "Calle Los Nogales 87, Trujillo",
        "anios_experiencia": 6,
        "placa": "F3C-728",
        "tipo_vehiculo": TipoVehiculo.FURGON,
        "capacidad_toneladas": Decimal("12.50"),
        "certificacion_carga_peligrosa": False,
        "estado": EstadoTransportista.ACTIVO,
        "licencia": 300,
        "revision": 90,
        "soat": 25,
        "color": (255, 193, 7),
    },
    {
        "numero_documento": "43456789",
        "nombre": "Rosa Elena Ticona Mamani",
        "direccion": "Av. Bolognesi 312, Arequipa",
        "anios_experiencia": 4,
        "placa": "M4D-903",
        "tipo_vehiculo": TipoVehiculo.CAMIONETA,
        "capacidad_toneladas": Decimal("3.50"),
        "certificacion_carga_peligrosa": False,
        "estado": EstadoTransportista.ACTIVO,
        "licencia": 180,
        "revision": 100,
        "soat": 60,
        "color": (108, 117, 125),
    },
    {
        "numero_documento": "44567890",
        "nombre": "Pedro Ccahuana López",
        "direccion": "Av. Los Héroes 890, Arequipa",
        "anios_experiencia": 11,
        "placa": "T5E-119",
        "tipo_vehiculo": TipoVehiculo.CISTERNA,
        "capacidad_toneladas": Decimal("24.00"),
        "certificacion_carga_peligrosa": True,
        "estado": EstadoTransportista.EN_RESERVA,
        "licencia": 365,
        "revision": -15,
        "soat": -20,
        "color": (220, 53, 69),
    },
    {
        "numero_documento": "45678901",
        "nombre": "Ana Lucía Vargas Medina",
        "direccion": "Av. Grau 245, Piura",
        "anios_experiencia": 7,
        "placa": "V6F-330",
        "tipo_vehiculo": TipoVehiculo.CAMION,
        "capacidad_toneladas": Decimal("9.00"),
        "certificacion_carga_peligrosa": False,
        "estado": EstadoTransportista.ACTIVO,
        "licencia": 150,
        "revision": 130,
        "soat": 30,
        "color": (111, 66, 193),
    },
    {
        "numero_documento": "46789012",
        "nombre": "Jorge Salazar Pinto",
        "direccion": "Av. Sánchez Cerro 140, Chiclayo",
        "anios_experiencia": 12,
        "placa": "V7G-542",
        "tipo_vehiculo": TipoVehiculo.CAMION,
        "capacidad_toneladas": Decimal("15.00"),
        "certificacion_carga_peligrosa": False,
        "estado": EstadoTransportista.ACTIVO,
        "licencia": 210,
        "revision": 140,
        "soat": 55,
        "color": (32, 201, 151),
    },
    {
        # Furgón de Nivel 2 con asignación ya finalizada
        "numero_documento": "47890123",
        "nombre": "Marco Antonio Salcedo Ríos",
        "direccion": "Av. Los Libertadores 1150, Lima",
        "anios_experiencia": 16,
        "placa": "V8H-651",
        "tipo_vehiculo": TipoVehiculo.FURGON,
        "capacidad_toneladas": Decimal("15.00"),
        "certificacion_carga_peligrosa": False,
        "estado": EstadoTransportista.ACTIVO,
        "licencia": 300,
        "revision": 200,
        "soat": 120,
        "color": (255, 99, 132),
    },
    {
        # Nivel 3 con revisión técnica y SOAT por vencer (avisos del panel)
        "numero_documento": "48901234",
        "nombre": "Teresa Núñez Campos",
        "direccion": "Jr. Puno 330, Huancayo",
        "anios_experiencia": 3,
        "placa": "V9J-762",
        "tipo_vehiculo": TipoVehiculo.CAMIONETA,
        "capacidad_toneladas": Decimal("4.50"),
        "certificacion_carga_peligrosa": False,
        "estado": EstadoTransportista.ACTIVO,
        "licencia": 150,
        "revision": 22,
        "soat": 12,
        "color": (54, 162, 235),
    },
    {
        # Nivel 1 con asignación activa y SOAT por vencer
        "numero_documento": "49012345",
        "nombre": "Víctor Hugo Paredes Luna",
        "direccion": "Av. Grau 1180, Piura",
        "anios_experiencia": 22,
        "placa": "W1K-873",
        "tipo_vehiculo": TipoVehiculo.TRAILER,
        "capacidad_toneladas": Decimal("38.00"),
        "certificacion_carga_peligrosa": True,
        "estado": EstadoTransportista.ACTIVO,
        "licencia": 400,
        "revision": 90,
        "soat": 26,
        "color": (153, 102, 255),
    },
    {
        # Capacidad exactamente en el límite (20.00 t → Nivel 2) y documento RUC
        "tipo_documento": TipoDocumento.RUC,
        "numero_documento": "20512233445",
        "nombre": "Empresa de Transportes El Sol E.I.R.L.",
        "direccion": "Av. Argentina 4520, Callao",
        "anios_experiencia": 18,
        "placa": "W2L-984",
        "tipo_vehiculo": TipoVehiculo.CAMION,
        "capacidad_toneladas": Decimal("20.00"),
        "certificacion_carga_peligrosa": False,
        "estado": EstadoTransportista.ACTIVO,
        "licencia": 365,
        "revision": 60,
        "soat": 200,
        "color": (75, 192, 192),
    },
    {
        # En Reserva con licencia por vencer y revisión técnica y SOAT vencidos
        "numero_documento": "50123456",
        "nombre": "Sofía Alejandra Bermúdez Ito",
        "direccion": "Calle Los Cedros 55, Arequipa",
        "anios_experiencia": 3,
        "placa": "W3M-095",
        "tipo_vehiculo": TipoVehiculo.CAMION,
        "capacidad_toneladas": Decimal("17.50"),
        "certificacion_carga_peligrosa": False,
        "estado": EstadoTransportista.EN_RESERVA,
        "licencia": 30,
        "revision": -5,
        "soat": -40,
        "color": (255, 159, 64),
    },
    {
        # Volquete de Nivel 1 con una advertencia y asignación finalizada
        "numero_documento": "51234567",
        "nombre": "Rodrigo Pantoja Cárdenas",
        "direccion": "Av. Brasil 2290, Lima",
        "anios_experiencia": 9,
        "placa": "W4N-106",
        "tipo_vehiculo": TipoVehiculo.VOLQUETE,
        "capacidad_toneladas": Decimal("26.00"),
        "certificacion_carga_peligrosa": True,
        "estado": EstadoTransportista.ACTIVO,
        "licencia": 200,
        "revision": 100,
        "soat": 50,
        "color": (199, 199, 199),
    },
    {
        # Llega a 3 advertencias: la baja automática se aplica al cargar los datos
        "numero_documento": "52345678",
        "nombre": "Karina Espinoza Loayza",
        "direccion": "Av. Canta Callao 890, Lima",
        "anios_experiencia": 5,
        "placa": "W5P-217",
        "tipo_vehiculo": TipoVehiculo.CAMION,
        "capacidad_toneladas": Decimal("8.00"),
        "certificacion_carga_peligrosa": False,
        "estado": EstadoTransportista.ACTIVO,
        "licencia": 250,
        "revision": 110,
        "soat": 70,
        "color": (255, 205, 86),
    },
    {
        # Sin experiencia registrada y SOAT por vencer
        "numero_documento": "53456789",
        "nombre": "Julio César Meléndez Rojas",
        "direccion": "Jr. Amazonas 470, Tarapoto",
        "anios_experiencia": 0,
        "placa": "W6Q-328",
        "tipo_vehiculo": TipoVehiculo.CAMION,
        "capacidad_toneladas": Decimal("6.50"),
        "certificacion_carga_peligrosa": False,
        "estado": EstadoTransportista.ACTIVO,
        "licencia": 120,
        "revision": 45,
        "soat": 15,
        "color": (201, 203, 207),
    },
    {
        # Baja administrativa (sin advertencias): el estado lo fija el operador
        "numero_documento": "54567890",
        "nombre": "Nadia Rocío Fuentes Aguirre",
        "direccion": "Av. Sánchez Carrión 155, Trujillo",
        "anios_experiencia": 7,
        "placa": "W7R-439",
        "tipo_vehiculo": TipoVehiculo.CISTERNA,
        "capacidad_toneladas": Decimal("22.00"),
        "certificacion_carga_peligrosa": True,
        "estado": EstadoTransportista.BAJA,
        "licencia": 300,
        "revision": 150,
        "soat": 120,
        "color": (128, 0, 128),
    },
    {
        # Cisterna de Nivel 1 disponible: da un candidato elegible a la oferta de cisterna
        "numero_documento": "55678901",
        "nombre": "Héctor Ramírez Ocampo",
        "direccion": "Carretera Central km 18, Santa Anita, Lima",
        "anios_experiencia": 13,
        "placa": "W8S-540",
        "tipo_vehiculo": TipoVehiculo.CISTERNA,
        "capacidad_toneladas": Decimal("30.00"),
        "certificacion_carga_peligrosa": True,
        "estado": EstadoTransportista.ACTIVO,
        "licencia": 330,
        "revision": 160,
        "soat": 95,
        "color": (0, 128, 128),
    },
]

# clave = identificador interno para relacionar asignaciones y advertencias
OFERTAS = [
    {
        "clave": "lima-trujillo",
        "empresa": "20100070970",
        "origen": "Lima",
        "destino": "Trujillo",
        "tipo_vehiculo_requerido": TipoVehiculo.CAMION,
        "nivel_requerido": NivelCarga.NIVEL_2,
        "remuneracion": Decimal("2100.00"),
    },
    {
        "clave": "lima-chiclayo",
        "empresa": "20100070970",
        "origen": "Lima",
        "destino": "Chiclayo",
        "tipo_vehiculo_requerido": TipoVehiculo.CAMIONETA,
        "nivel_requerido": NivelCarga.NIVEL_3,
        "remuneracion": Decimal("850.00"),
    },
    {
        "clave": "ica-lima",
        "empresa": "20481234567",
        "origen": "Ica",
        "destino": "Lima",
        "tipo_vehiculo_requerido": TipoVehiculo.FURGON,
        "nivel_requerido": NivelCarga.NIVEL_2,
        "remuneracion": Decimal("1450.00"),
    },
    {
        "clave": "ica-piura",
        "empresa": "20481234567",
        "origen": "Ica",
        "destino": "Piura",
        "tipo_vehiculo_requerido": TipoVehiculo.CAMION,
        "nivel_requerido": NivelCarga.NIVEL_2,
        "remuneracion": Decimal("3200.00"),
    },
    {
        "clave": "arequipa-matarani",
        "empresa": "20556677889",
        "origen": "Arequipa",
        "destino": "Puerto de Matarani",
        "tipo_vehiculo_requerido": TipoVehiculo.TRAILER,
        "nivel_requerido": NivelCarga.NIVEL_1,
        "remuneracion": Decimal("5400.00"),
    },
    {
        "clave": "lima-arequipa",
        "empresa": "20100070970",
        "origen": "Lima",
        "destino": "Arequipa",
        "tipo_vehiculo_requerido": TipoVehiculo.CAMION,
        "nivel_requerido": NivelCarga.NIVEL_2,
        "remuneracion": Decimal("2800.00"),
    },
    {
        "clave": "callao-lima-frio",
        "empresa": "20601122334",
        "origen": "Callao",
        "destino": "Lima",
        "tipo_vehiculo_requerido": TipoVehiculo.FURGON,
        "nivel_requerido": NivelCarga.NIVEL_2,
        "remuneracion": Decimal("1750.00"),
    },
    {
        "clave": "callao-trujillo-frio",
        "empresa": "20601122334",
        "origen": "Callao",
        "destino": "Trujillo",
        "tipo_vehiculo_requerido": TipoVehiculo.FURGON,
        "nivel_requerido": NivelCarga.NIVEL_2,
        "remuneracion": Decimal("2600.00"),
    },
    {
        "clave": "lima-huancayo",
        "empresa": "20709988776",
        "origen": "Lima",
        "destino": "Huancayo",
        "tipo_vehiculo_requerido": TipoVehiculo.CAMIONETA,
        "nivel_requerido": NivelCarga.NIVEL_3,
        "remuneracion": Decimal("980.00"),
    },
    {
        "clave": "piura-lima",
        "empresa": "20805544332",
        "origen": "Piura",
        "destino": "Lima",
        "tipo_vehiculo_requerido": TipoVehiculo.CAMION,
        "nivel_requerido": NivelCarga.NIVEL_2,
        "remuneracion": Decimal("2950.00"),
    },
    {
        "clave": "piura-tumbes",
        "empresa": "20805544332",
        "origen": "Piura",
        "destino": "Tumbes",
        "tipo_vehiculo_requerido": TipoVehiculo.FURGON,
        "nivel_requerido": NivelCarga.NIVEL_2,
        "remuneracion": Decimal("1200.00"),
    },
    {
        "clave": "arequipa-moquegua",
        "empresa": "20556677889",
        "origen": "Arequipa",
        "destino": "Moquegua",
        "tipo_vehiculo_requerido": TipoVehiculo.VOLQUETE,
        "nivel_requerido": NivelCarga.NIVEL_1,
        "remuneracion": Decimal("6100.00"),
    },
    {
        "clave": "arequipa-lima",
        "empresa": "20556677889",
        "origen": "Arequipa",
        "destino": "Lima",
        "tipo_vehiculo_requerido": TipoVehiculo.TRAILER,
        "nivel_requerido": NivelCarga.NIVEL_1,
        "remuneracion": Decimal("7200.00"),
    },
    {
        "clave": "lima-cusco",
        "empresa": "20709988776",
        "origen": "Lima",
        "destino": "Cusco",
        "tipo_vehiculo_requerido": TipoVehiculo.CAMION,
        "nivel_requerido": NivelCarga.NIVEL_2,
        "remuneracion": Decimal("3400.00"),
    },
    {
        "clave": "callao-arequipa",
        "empresa": "20601122334",
        "origen": "Callao",
        "destino": "Arequipa",
        "tipo_vehiculo_requerido": TipoVehiculo.CAMION,
        "nivel_requerido": NivelCarga.NIVEL_2,
        "remuneracion": Decimal("3800.00"),
    },
    {
        "clave": "lima-iquitos",
        "empresa": "20709988776",
        "origen": "Lima",
        "destino": "Iquitos",
        "tipo_vehiculo_requerido": TipoVehiculo.FURGON,
        "nivel_requerido": NivelCarga.NIVEL_2,
        "remuneracion": Decimal("4100.00"),
    },
    {
        "clave": "piura-chiclayo",
        "empresa": "20805544332",
        "origen": "Piura",
        "destino": "Chiclayo",
        "tipo_vehiculo_requerido": TipoVehiculo.CAMIONETA,
        "nivel_requerido": NivelCarga.NIVEL_3,
        "remuneracion": Decimal("890.00"),
    },
    {
        "clave": "arequipa-tacna",
        "empresa": "20556677889",
        "origen": "Arequipa",
        "destino": "Tacna",
        "tipo_vehiculo_requerido": TipoVehiculo.CISTERNA,
        "nivel_requerido": NivelCarga.NIVEL_1,
        "remuneracion": Decimal("5800.00"),
    },
]

# inicio/fin son días respecto de hoy; estado_final deja constancia sin borrar nada
ASIGNACIONES = [
    {"oferta": "lima-arequipa", "transportista": "41234567", "inicio": 0},
    {"oferta": "arequipa-lima", "transportista": "49012345", "inicio": -4},
    {"oferta": "piura-lima", "transportista": "20512233445", "inicio": -2},
    {
        "oferta": "callao-lima-frio",
        "transportista": "47890123",
        "inicio": -40,
        "fin": -25,
        "estado_final": EstadoAsignacion.FINALIZADA,
    },
    {
        "oferta": "lima-huancayo",
        "transportista": "48901234",
        "inicio": -60,
        "fin": -50,
        "estado_final": EstadoAsignacion.FINALIZADA,
    },
    {
        "oferta": "arequipa-moquegua",
        "transportista": "51234567",
        "inicio": -90,
        "fin": -80,
        "estado_final": EstadoAsignacion.FINALIZADA,
    },
    {
        "oferta": "callao-trujillo-frio",
        "transportista": "42345678",
        "inicio": -20,
        "fin": -15,
        "estado_final": EstadoAsignacion.CANCELADA,
    },
]

ADVERTENCIAS = [
    ("45678901", "Demora de 6 horas en la entrega en Trujillo.", 20, None),
    ("45678901", "Documentación de transporte presentada incompleta.", 5, None),
    ("46789012", "Incumplimiento del horario de recojo acordado.", 90, None),
    ("46789012", "Mercadería entregada sin verificar el peso declarado.", 60, None),
    ("46789012", "Reiteradas quejas del cliente por trato inadecuado.", 10, None),
    (
        "47890123",
        "Queja del cliente por manipulación inadecuada de la carga refrigerada.",
        22,
        "callao-lima-frio",
    ),
    ("51234567", "Documentación de transporte presentada fuera de plazo.", 45, None),
    ("52345678", "Retraso de 4 horas en la entrega de materiales.", 30, None),
    ("52345678", "Carga entregada con el embalaje dañado.", 12, None),
    ("52345678", "Reincidencia en el incumplimiento de la ruta acordada.", 3, None),
]

CURSOS = [
    {
        "codigo": "CUR01",
        "titulo": "Manejo defensivo",
        "tema": "Seguridad vial",
        "duracion_horas": 8,
    },
    {
        "codigo": "CUR02",
        "titulo": "Primeros auxilios en ruta",
        "tema": "Salud ocupacional",
        "duracion_horas": 4,
    },
]

PARTICIPACIONES = [
    {
        "transportista": "41234567",
        "curso": "CUR01",
        "convocatoria": "2026-10",
        "estado": EstadoParticipacion.INSCRITO,
        "dias_atras": 5,
    },
    {
        "transportista": "49012345",
        "curso": "CUR01",
        "convocatoria": "2026-10",
        "estado": EstadoParticipacion.EN_PROGRESO,
        "dias_atras": 12,
    },
    {
        "transportista": "48901234",
        "curso": "CUR02",
        "convocatoria": "2026-09",
        "estado": EstadoParticipacion.COMPLETADO,
        "resultado": ResultadoParticipacion.APROBADO,
        "dias_atras": 20,
        "fin_dias_atras": 18,
    },
]

INCIDENCIAS = [
    {
        "tipo": TipoIncidencia.QUEJA,
        "transportista": "49012345",
        "oferta": "arequipa-lima",
        "descripcion": "Queja del cliente por retraso en la entrega de Arequipa.",
        "dias_atras": 3,
    },
    {
        "tipo": TipoIncidencia.RENUNCIA,
        "transportista": "42345678",
        "descripcion": "Renuncia voluntaria por motivos personales.",
        "acuerdo": "Se acuerda buscar reemplazo antes de fin de mes.",
        "dias_atras": 6,
    },
]

# Asignaciones finalizadas cuyas semanas se liquidan en borrador. La primera
# semana de la primera se firma con retraso para mostrar la regularización;
# el resto se firma el viernes previsto.
OFERTAS_A_LIQUIDAR = ["callao-lima-frio", "lima-huancayo", "arequipa-moquegua"]


class Command(BaseCommand):
    help = (
        "Carga datos ficticios de demostración (transportistas, clientes, ofertas, "
        "asignaciones y advertencias). Es idempotente y no borra nada."
    )

    def handle(self, *args, **options):
        hoy = timezone.localdate()
        self.creados = {
            "empresas": 0,
            "transportistas": 0,
            "ofertas": 0,
            "asignaciones": 0,
            "advertencias": 0,
            "cursos": 0,
            "participaciones": 0,
            "incidencias": 0,
            "formatos": 0,
            "liquidaciones": 0,
        }

        with transaction.atomic():
            empresas = self._cargar_empresas()
            transportistas = self._cargar_transportistas(hoy)
            ofertas = self._cargar_ofertas(empresas)
            asignaciones = self._cargar_asignaciones(ofertas, transportistas, hoy)
            self._cargar_advertencias(transportistas, asignaciones, hoy)
            cursos = self._cargar_cursos()
            self._cargar_participaciones(transportistas, cursos, hoy)
            self._cargar_incidencias(transportistas, ofertas, asignaciones, hoy)
            self._cargar_formatos(asignaciones)

        self._resumen(hoy)

    # ------------------------------------------------------------------ datos
    def _cargar_empresas(self):
        empresas = {}
        for datos in EMPRESAS:
            empresa, creada = EmpresaCliente.objects.get_or_create(
                ruc=datos["ruc"],
                defaults={
                    "razon_social": datos["razon_social"],
                    "direccion": datos["direccion"],
                    "actividad_economica": datos["actividad_economica"],
                },
            )
            self.creados["empresas"] += int(creada)
            empresas[datos["ruc"]] = empresa
        return empresas

    def _cargar_transportistas(self, hoy):
        transportistas = {}
        for datos in TRANSPORTISTAS:
            existente = Transportista.objects.filter(
                numero_documento=datos["numero_documento"]
            ).first()
            if existente:
                transportistas[datos["numero_documento"]] = existente
                continue

            transportista = Transportista(
                tipo_documento=datos.get("tipo_documento", TipoDocumento.DNI),
                numero_documento=datos["numero_documento"],
                nombre=datos["nombre"],
                direccion=datos["direccion"],
                anios_experiencia=datos["anios_experiencia"],
                placa=datos["placa"],
                tipo_vehiculo=datos["tipo_vehiculo"],
                capacidad_toneladas=datos["capacidad_toneladas"],
                certificacion_carga_peligrosa=datos["certificacion_carga_peligrosa"],
                estado=datos["estado"],
                fecha_vencimiento_licencia=hoy + timedelta(days=datos["licencia"]),
                fecha_vencimiento_revision_tecnica=hoy + timedelta(days=datos["revision"]),
                fecha_vencimiento_soat=hoy + timedelta(days=datos["soat"]),
                fotografia_vehiculo=self._fotografia(datos["placa"], datos["color"]),
            )
            transportista.nivel = transportista.calcular_nivel()
            transportista.full_clean()
            transportista.save()
            transportistas[datos["numero_documento"]] = transportista
            self.creados["transportistas"] += 1
        return transportistas

    def _fotografia(self, placa, color):
        """Genera una imagen PNG ficticia para el vehículo."""
        buffer = BytesIO()
        Image.new("RGB", (480, 300), color).save(buffer, format="PNG")
        return ContentFile(buffer.getvalue(), name=f"{placa}.png")

    def _cargar_ofertas(self, empresas):
        ofertas = {}
        for datos in OFERTAS:
            datos = dict(datos)
            clave = datos.pop("clave")
            empresa = empresas[datos.pop("empresa")]
            existente = OfertaCarga.objects.filter(
                empresa_cliente=empresa,
                origen=datos["origen"],
                destino=datos["destino"],
            ).first()
            if existente:
                ofertas[clave] = existente
                continue
            oferta = OfertaCarga.objects.create(empresa_cliente=empresa, **datos)
            ofertas[clave] = oferta
            self.creados["ofertas"] += 1
        return ofertas

    def _cargar_asignaciones(self, ofertas, transportistas, hoy):
        """Crea las asignaciones y aplica su estado final sin borrar el historial."""
        asignaciones = {}
        for datos in ASIGNACIONES:
            oferta = ofertas[datos["oferta"]]
            existente = Asignacion.objects.filter(oferta=oferta).first()
            if existente:
                asignaciones[datos["oferta"]] = existente
                continue

            asignacion = reglas.crear_asignacion(
                transportista=transportistas[datos["transportista"]],
                oferta=oferta,
                fecha_inicio=hoy + timedelta(days=datos["inicio"]),
                fecha_fin=None,
            )
            estado_final = datos.get("estado_final")
            if estado_final == EstadoAsignacion.FINALIZADA:
                asignacion.finalizar(hoy + timedelta(days=datos["fin"]))
            elif estado_final == EstadoAsignacion.CANCELADA:
                asignacion.cancelar(hoy + timedelta(days=datos["fin"]))
            asignaciones[datos["oferta"]] = asignacion
            self.creados["asignaciones"] += 1
        return asignaciones

    def _cargar_advertencias(self, transportistas, asignaciones, hoy):
        for numero_documento, descripcion, dias_atras, clave_asignacion in ADVERTENCIAS:
            transportista = transportistas[numero_documento]
            if transportista.advertencias.filter(descripcion=descripcion).exists():
                continue
            Advertencia.objects.create(
                transportista=transportista,
                descripcion=descripcion,
                fecha=hoy - timedelta(days=dias_atras),
                asignacion=asignaciones.get(clave_asignacion) if clave_asignacion else None,
            )
            self.creados["advertencias"] += 1

        # Aviso de las bajas automáticas producidas por el límite de advertencias
        for transportista in Transportista.objects.filter(
            advertencias__isnull=False
        ).distinct():
            if transportista.advertencias_total >= MAXIMO_ADVERTENCIAS:
                self.stdout.write(
                    self.style.WARNING(
                        f"{transportista.nombre} acumula {transportista.advertencias_total} "
                        f"advertencias y está en estado «{transportista.get_estado_display()}»."
                    )
                )

    def _cargar_cursos(self):
        cursos = {}
        for datos in CURSOS:
            curso, creada = Curso.objects.get_or_create(
                codigo=datos["codigo"],
                defaults={
                    "titulo": datos["titulo"],
                    "tema": datos["tema"],
                    "duracion_horas": datos["duracion_horas"],
                },
            )
            self.creados["cursos"] += int(creada)
            cursos[datos["codigo"]] = curso
        return cursos

    def _cargar_participaciones(self, transportistas, cursos, hoy):
        for datos in PARTICIPACIONES:
            transportista = transportistas[datos["transportista"]]
            curso = cursos[datos["curso"]]
            existente = Participacion.objects.filter(
                transportista=transportista,
                curso=curso,
                convocatoria=datos["convocatoria"],
            ).first()
            if existente:
                continue
            participacion = Participacion(
                transportista=transportista,
                curso=curso,
                convocatoria=datos["convocatoria"],
                fecha=hoy - timedelta(days=datos["dias_atras"]),
                estado=datos["estado"],
            )
            if datos["estado"] == EstadoParticipacion.COMPLETADO:
                participacion.fecha_finalizacion = hoy - timedelta(
                    days=datos["fin_dias_atras"]
                )
                participacion.resultado = datos["resultado"]
            participacion.full_clean()
            participacion.save()
            self.creados["participaciones"] += 1

    def _cargar_incidencias(self, transportistas, ofertas, asignaciones, hoy):
        for datos in INCIDENCIAS:
            transportista = transportistas[datos["transportista"]]
            if Incidencia.objects.filter(
                transportista=transportista, descripcion=datos["descripcion"]
            ).exists():
                continue
            asignacion = None
            empresa = None
            if datos.get("oferta"):
                oferta = ofertas[datos["oferta"]]
                empresa = oferta.empresa_cliente
                asignacion = asignaciones.get(datos["oferta"])
            incidencia = Incidencia(
                tipo=datos["tipo"],
                fecha=hoy - timedelta(days=datos["dias_atras"]),
                descripcion=datos["descripcion"],
                empresa_cliente=empresa,
                transportista=transportista,
                asignacion=asignacion,
                acuerdo_reemplazo=datos.get("acuerdo", ""),
            )
            incidencia.full_clean()
            incidencia.save()
            self.creados["incidencias"] += 1

    def _cargar_formatos(self, asignaciones):
        """Semanas firmadas de asignaciones finalizadas, con borrador.

        La primera semana de la primera asignación se firma con retraso para
        mostrar la regularización. No se configuran parámetros financieros ni
        se cierra nada: el cierre sigue bloqueado como corresponde.
        """
        primera = True
        for clave in OFERTAS_A_LIQUIDAR:
            asignacion = asignaciones[clave]
            semanas = calculos_liquidacion.semanas_servicio(
                asignacion.fecha_inicio, asignacion.fecha_fin
            )
            for indice, (lunes, domingo, viernes) in enumerate(semanas):
                formato, creado = FormatoSemanal.objects.get_or_create(
                    asignacion=asignacion,
                    periodo_inicio=lunes,
                    defaults={"periodo_fin": domingo, "fecha_prevista": viernes},
                )
                self.creados["formatos"] += int(creado)
                if formato.fecha_firma is None:
                    firma = viernes + timedelta(days=3) if primera and indice == 0 else viernes
                    formato.firmar(firma)
                liquidacion, creada = Liquidacion.objects.get_or_create(formato=formato)
                if creada:
                    liquidacion.recalcular()
                    self.creados["liquidaciones"] += 1
            primera = False

    # --------------------------------------------------------------- resumen
    def _resumen(self, hoy):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Datos de demostración cargados:"))
        self.stdout.write(
            "  (datos ficticios: nombres, documentos y RUC son inventados; no se borra nada)"
        )
        for nombre, cantidad in self.creados.items():
            self.stdout.write(f"  - {nombre}: {cantidad} nuevo(s)")

        self.stdout.write("")
        self.stdout.write("Totales actuales:")
        self.stdout.write(f"  - Empresas clientes: {EmpresaCliente.objects.count()}")
        self.stdout.write(f"  - Transportistas: {Transportista.objects.count()}")
        for estado in EstadoTransportista:
            self.stdout.write(
                f"      · {estado.label}: "
                f"{Transportista.objects.filter(estado=estado.value).count()}"
            )
        for nivel in NivelCarga:
            self.stdout.write(
                f"      · Nivel {nivel.value}: "
                f"{Transportista.objects.filter(nivel=nivel.value).count()}"
            )
        self.stdout.write(f"  - Ofertas de carga: {OfertaCarga.objects.count()}")
        for estado in EstadoOferta:
            self.stdout.write(
                f"      · {estado.label}: {OfertaCarga.objects.filter(estado=estado.value).count()}"
            )
        self.stdout.write(f"  - Asignaciones: {Asignacion.objects.count()}")
        for estado in EstadoAsignacion:
            self.stdout.write(
                f"      · {estado.label}: {Asignacion.objects.filter(estado=estado.value).count()}"
            )
        self.stdout.write(f"  - Advertencias: {Advertencia.objects.count()}")
        self.stdout.write(f"  - Cursos: {Curso.objects.count()}")
        self.stdout.write(
            f"  - Participaciones: {Participacion.objects.count()} "
            f"(completadas: {Participacion.objects.filter(estado=EstadoParticipacion.COMPLETADO).count()})"
        )
        self.stdout.write(f"  - Incidencias: {Incidencia.objects.count()}")
        self.stdout.write(f"  - Formatos semanales: {FormatoSemanal.objects.count()}")
        self.stdout.write(
            f"  - Liquidaciones: {Liquidacion.objects.count()} "
            "(todas en borrador: sin parámetros no hay cierre)"
        )

        with_vencidos = [
            t
            for t in Transportista.objects.all()
            if not (t.licencia_vigente and t.revision_tecnica_vigente and t.soat_vigente)
        ]
        self.stdout.write(
            f"  - Transportistas con algún documento vencido: {len(with_vencidos)}"
        )
        por_vencer = sum(len(t.documentos_por_vencer()) for t in Transportista.objects.all())
        self.stdout.write(
            f"  - Documentos que vencen en los próximos 30 días: {por_vencer} "
            f"(el panel muestra los 10 más próximos; hoy es {hoy:%d/%m/%Y})"
        )

        self.stdout.write("")
        self.stdout.write(
            "Recuerde crear un usuario para ingresar: "
            "python manage.py createsuperuser"
        )

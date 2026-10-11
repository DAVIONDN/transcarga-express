"""Datos ficticios reutilizables por las pruebas del proyecto."""

import itertools
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from PIL import Image

from clientes.models import EmpresaCliente
from comun.choices import (
    EstadoTransportista,
    NivelCarga,
    TipoDocumento,
    TipoVehiculo,
)
from comun.permisos import (
    GRUPO_ADMINISTRADOR,
    GRUPO_CONSULTA,
    GRUPO_OPERADOR,
    inicializar_roles_y_permisos,
)
from ofertas.models import OfertaCarga
from transportistas.models import Transportista

# Contador para que documento, placa y RUC sean únicos en cada llamada
_contador = itertools.count(1)


def siguiente_numero():
    return next(_contador)


class PruebaConRol(TestCase):
    """Caso de prueba con un usuario autenticado y un rol concreto.

    Los roles se materializan como grupos de Django; `crear_roles()` los crea de
    forma idempotente en la base de datos de prueba. Con `rol = None` el usuario
    queda autenticado pero sin permisos (útil para comprobar el acceso denegado).
    """

    rol = None
    username = "operador"

    @classmethod
    def setUpTestData(cls):
        crear_roles()
        cls.usuario = get_user_model().objects.create_user(
            username=cls.username, password="clave-de-prueba-123"
        )
        if cls.rol is not None:
            cls.usuario.groups.set([Group.objects.get(name=cls.rol)])

    def setUp(self):
        self.client.force_login(self.usuario)


class PruebaAutenticada(PruebaConRol):
    """Usuario con rol Operador: opera todos los módulos de negocio."""

    rol = GRUPO_OPERADOR


class PruebaAdministrador(PruebaConRol):
    """Usuario con rol Administrador: además administra cuentas."""

    rol = GRUPO_ADMINISTRADOR
    username = "administrador"


class PruebaConsulta(PruebaConRol):
    """Usuario con rol Consulta: solo lectura de los módulos."""

    rol = GRUPO_CONSULTA
    username = "consulta"


class PruebaSinPermisos(PruebaConRol):
    """Usuario autenticado sin rol: no accede a ninguna operación."""

    rol = None
    username = "sin_permisos"


def crear_roles():
    """Crea los grupos de rol y sus permisos (idempotente, para las pruebas)."""
    return inicializar_roles_y_permisos()


def imagen_de_prueba(nombre="vehiculo.png"):
    """Devuelve una imagen PNG válida en memoria para el campo de fotografía."""
    buffer = BytesIO()
    Image.new("RGB", (8, 8), "white").save(buffer, format="PNG")
    return SimpleUploadedFile(nombre, buffer.getvalue(), content_type="image/png")


def fechas_vigentes():
    """Fechas de vencimiento futuras para los tres documentos obligatorios."""
    hoy = timezone.localdate()
    return {
        "fecha_vencimiento_licencia": hoy + timedelta(days=365),
        "fecha_vencimiento_revision_tecnica": hoy + timedelta(days=180),
        "fecha_vencimiento_soat": hoy + timedelta(days=90),
    }


def datos_transportista(**cambios):
    """Diccionario de datos de un transportista con documentación vigente."""
    numero = siguiente_numero()
    datos = {
        "tipo_documento": TipoDocumento.DNI,
        "numero_documento": f"{10000000 + numero}",
        "nombre": f"Juan Pérez Quispe {numero}",
        "direccion": "Av. Los Álamos 123, Lima",
        "anios_experiencia": 5,
        "placa": f"V{numero:05d}",
        "tipo_vehiculo": TipoVehiculo.CAMION,
        "capacidad_toneladas": Decimal("10.00"),
        "certificacion_carga_peligrosa": False,
        "fotografia_vehiculo": imagen_de_prueba(),
        "estado": EstadoTransportista.ACTIVO,
    }
    datos.update(fechas_vigentes())
    datos.update(cambios)
    return datos


def datos_post_transportista(**cambios):
    """Los mismos datos, con las fechas en formato ISO, listos para enviar por POST."""
    datos = datos_transportista(**cambios)
    for campo in (
        "fecha_vencimiento_licencia",
        "fecha_vencimiento_revision_tecnica",
        "fecha_vencimiento_soat",
    ):
        if hasattr(datos[campo], "isoformat"):
            datos[campo] = datos[campo].isoformat()
    return datos


def construir_transportista(**cambios):
    """Instancia de transportista (sin guardar) con el nivel ya calculado."""
    transportista = Transportista(**datos_transportista(**cambios))
    transportista.nivel = transportista.calcular_nivel()
    return transportista


def crear_transportista(**cambios):
    """Transportista guardado, sin ejecutar la validación completa del modelo."""
    transportista = construir_transportista(**cambios)
    transportista.save()
    return transportista


def crear_empresa_cliente(**cambios):
    datos = {
        "ruc": f"20{100000000 + siguiente_numero()}",
        "razon_social": "Transportes del Norte S.A.C.",
        "direccion": "Av. Industrial 456, Lima",
        "actividad_economica": "Comercio al por mayor",
    }
    datos.update(cambios)
    return EmpresaCliente.objects.create(**datos)


def crear_oferta(empresa=None, **cambios):
    """Oferta de carga que, por omisión, exige un camión de Nivel 2."""
    datos = {
        "empresa_cliente": empresa or EmpresaCliente.objects.first() or crear_empresa_cliente(),
        "origen": "Lima",
        "destino": "Arequipa",
        "tipo_vehiculo_requerido": TipoVehiculo.CAMION,
        "nivel_requerido": NivelCarga.NIVEL_2,
        "remuneracion": Decimal("2500.00"),
    }
    datos.update(cambios)
    return OfertaCarga.objects.create(**datos)

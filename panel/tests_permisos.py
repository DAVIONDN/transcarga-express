"""Pruebas del control de acceso por roles y permisos (validación en el servidor).

Comprueban que la protección no depende de ocultar botones: cada operación se
rechaza con 403 cuando el usuario autenticado no tiene el permiso requerido, tanto
en GET como en POST.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from comun.permisos import GRUPO_OPERADOR
from comun.pruebas import (
    PruebaAdministrador,
    PruebaAutenticada,
    PruebaConsulta,
    PruebaSinPermisos,
    crear_empresa_cliente,
    crear_roles,
    crear_transportista,
)
from transportistas.models import Transportista

Usuario = get_user_model()


class AccesoAnonimoTests(TestCase):
    """Sin sesión iniciada, las rutas de usuarios redirigen al acceso."""

    def test_las_rutas_de_usuarios_exigen_sesion(self):
        for nombre in ("panel:usuarios_lista", "panel:usuarios_crear"):
            with self.subTest(ruta=nombre):
                respuesta = self.client.get(reverse(nombre))
                self.assertEqual(respuesta.status_code, 302)
                self.assertTrue(respuesta.url.startswith(reverse("login")))


class RutaProtegidaConsultaTests(PruebaConsulta):
    """El rol Consulta es de solo lectura."""

    def test_puede_ver_los_listados(self):
        for nombre in (
            "transportistas:lista",
            "clientes:lista",
            "ofertas:lista",
            "asignaciones:lista",
            "transportistas:advertencias",
        ):
            with self.subTest(ruta=nombre):
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 200)

    def test_no_puede_acceder_a_las_pantallas_de_alta(self):
        for nombre in ("transportistas:crear", "clientes:crear", "ofertas:crear"):
            with self.subTest(ruta=nombre):
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 403)

    def test_no_puede_editar(self):
        transportista = crear_transportista()
        empresa = crear_empresa_cliente()
        for nombre, pk in (("transportistas:editar", transportista.pk), ("clientes:editar", empresa.pk)):
            with self.subTest(ruta=nombre):
                self.assertEqual(
                    self.client.get(reverse(nombre, args=[pk])).status_code, 403
                )

    def test_no_puede_operar_por_post(self):
        respuesta = self.client.post(reverse("transportistas:crear"), {})

        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(Transportista.objects.exists())

    def test_los_botones_de_accion_no_aparecen(self):
        respuesta = self.client.get(reverse("transportistas:lista"))

        self.assertNotContains(respuesta, "Nuevo transportista")


class RutaProtegidaOperadorTests(PruebaAutenticada):
    """El rol Operador opera los módulos, pero no administra cuentas."""

    def test_puede_acceder_al_alta_de_transportistas(self):
        self.assertEqual(self.client.get(reverse("transportistas:crear")).status_code, 200)

    def test_ve_los_botones_de_accion(self):
        respuesta = self.client.get(reverse("transportistas:lista"))

        self.assertContains(respuesta, "Nuevo transportista")

    def test_no_puede_administrar_usuarios(self):
        for nombre in ("panel:usuarios_lista", "panel:usuarios_crear"):
            with self.subTest(ruta=nombre):
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 403)

    def test_no_puede_administrar_usuarios_por_post(self):
        respuesta = self.client.post(reverse("panel:usuarios_crear"), {})

        self.assertEqual(respuesta.status_code, 403)


class RutaProtegidaAdminTests(PruebaAdministrador):
    """El rol Administrador administra cuentas y opera los módulos."""

    def test_puede_acceder_a_la_gestion_de_usuarios(self):
        self.assertEqual(self.client.get(reverse("panel:usuarios_lista")).status_code, 200)
        self.assertEqual(self.client.get(reverse("panel:usuarios_crear")).status_code, 200)


class SinPermisosTests(PruebaSinPermisos):
    """Un usuario autenticado sin rol no accede a ninguna operación."""

    def test_recibe_acceso_denegado_en_los_modulos(self):
        for nombre in (
            "transportistas:lista",
            "clientes:lista",
            "ofertas:lista",
            "asignaciones:lista",
            "panel:usuarios_lista",
        ):
            with self.subTest(ruta=nombre):
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 403)

    def test_el_panel_de_inicio_sigue_visible(self):
        self.assertEqual(self.client.get(reverse("panel:inicio")).status_code, 200)


class CuentaInactivaTests(TestCase):
    """Una cuenta inactiva no puede autenticarse ni mantener la sesión."""

    def setUp(self):
        crear_roles()
        self.usuario = Usuario.objects.create_user(
            username="inactivo", password="clave-de-prueba-123"
        )
        self.usuario.groups.set([Group.objects.get(name=GRUPO_OPERADOR)])

    def test_un_usuario_inactivo_no_puede_autenticarse(self):
        self.usuario.is_active = False
        self.usuario.save(update_fields=["is_active"])

        self.assertFalse(
            self.client.login(username="inactivo", password="clave-de-prueba-123")
        )

    def test_la_sesion_de_un_usuario_desactivado_se_rechaza(self):
        self.assertTrue(
            self.client.login(username="inactivo", password="clave-de-prueba-123")
        )
        self.usuario.is_active = False
        self.usuario.save(update_fields=["is_active"])

        respuesta = self.client.get(reverse("transportistas:lista"))

        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta.url.startswith(reverse("login")))

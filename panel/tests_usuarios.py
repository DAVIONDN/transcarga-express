"""Pruebas de la gestión de usuarios (exclusiva del rol Administrador).

Comprueban el alta, la edición, la activación/desactivación, el restablecimiento de
contraseña, la protección del último administrador, la imposibilidad de gestionar
cuentas de superusuario por parte de un administrador no superusuario, la
manipulación de roles y la conservación de las operaciones históricas.
"""

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse

from comun.permisos import GRUPO_ADMINISTRADOR, GRUPO_OPERADOR
from comun.pruebas import PruebaAdministrador, crear_transportista
from transportistas.models import Advertencia

Usuario = get_user_model()

CLAVE = "clave-de-prueba-123"


class GestionUsuariosTests(PruebaAdministrador):
    def test_lista_usuarios_muestra_rol_y_estado(self):
        respuesta = self.client.get(reverse("panel:usuarios_lista"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.usuario.username)
        self.assertContains(respuesta, GRUPO_ADMINISTRADOR)
        self.assertContains(respuesta, "Activo")

    def test_busqueda_de_usuarios(self):
        Usuario.objects.create_user(username="jperez", password=CLAVE)

        respuesta = self.client.get(reverse("panel:usuarios_lista"), {"q": "jperez"})

        self.assertContains(respuesta, "jperez")

    def test_crear_usuario_con_rol(self):
        respuesta = self.client.post(
            reverse("panel:usuarios_crear"),
            {
                "username": "nuevo.operador",
                "password1": "clave-segura-12345",
                "password2": "clave-segura-12345",
                "first_name": "Nuevo",
                "last_name": "Operador",
                "email": "nuevo@example.com",
                "rol": GRUPO_OPERADOR,
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        usuario = Usuario.objects.get(username="nuevo.operador")
        self.assertTrue(usuario.check_password("clave-segura-12345"))
        self.assertTrue(usuario.groups.filter(name=GRUPO_OPERADOR).exists())

    def test_editar_datos_basicos(self):
        usuario = Usuario.objects.create_user(username="editable", password=CLAVE)

        respuesta = self.client.post(
            reverse("panel:usuarios_editar", args=[usuario.pk]),
            {
                "username": "editable",
                "first_name": "Editado",
                "last_name": "",
                "email": "",
                "is_active": "on",
                "rol": GRUPO_OPERADOR,
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        usuario.refresh_from_db()
        self.assertEqual(usuario.first_name, "Editado")
        self.assertTrue(usuario.groups.filter(name=GRUPO_OPERADOR).exists())

    def test_desactivar_cuenta_con_confirmacion(self):
        usuario = Usuario.objects.create_user(username="temporal", password=CLAVE)

        confirmacion = self.client.get(reverse("panel:usuarios_estado", args=[usuario.pk]))
        self.assertEqual(confirmacion.status_code, 200)
        self.assertContains(confirmacion, "desactivar")

        respuesta = self.client.post(reverse("panel:usuarios_estado", args=[usuario.pk]))

        self.assertEqual(respuesta.status_code, 302)
        usuario.refresh_from_db()
        self.assertFalse(usuario.is_active)

    def test_restablecer_clave(self):
        usuario = Usuario.objects.create_user(username="clave", password="clave-antigua-123")

        respuesta = self.client.post(
            reverse("panel:usuarios_clave", args=[usuario.pk]),
            {"new_password1": "clave-nueva-12345", "new_password2": "clave-nueva-12345"},
        )

        self.assertEqual(respuesta.status_code, 302)
        usuario.refresh_from_db()
        self.assertTrue(usuario.check_password("clave-nueva-12345"))

    def test_no_se_puede_desactivar_al_ultimo_administrador(self):
        respuesta = self.client.post(reverse("panel:usuarios_estado", args=[self.usuario.pk]))

        self.assertEqual(respuesta.status_code, 302)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.is_active)

    def test_no_se_puede_degradar_al_ultimo_administrador(self):
        respuesta = self.client.post(
            reverse("panel:usuarios_editar", args=[self.usuario.pk]),
            {
                "username": self.usuario.username,
                "first_name": "",
                "last_name": "",
                "email": "",
                "is_active": "on",
                "rol": GRUPO_OPERADOR,
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.groups.filter(name=GRUPO_ADMINISTRADOR).exists())

    def test_rol_manipulado_no_otorga_permisos(self):
        respuesta = self.client.post(
            reverse("panel:usuarios_crear"),
            {
                "username": "malicioso",
                "password1": "clave-segura-12345",
                "password2": "clave-segura-12345",
                "rol": "SuperadminFalso",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Usuario.objects.filter(username="malicioso").exists())

    def test_no_superusuario_no_gestiona_a_un_superusuario(self):
        superusuario = Usuario.objects.create_superuser(username="root", password=CLAVE)

        for nombre in (
            "panel:usuarios_editar",
            "panel:usuarios_estado",
            "panel:usuarios_clave",
        ):
            with self.subTest(ruta=nombre):
                respuesta = self.client.get(reverse(nombre, args=[superusuario.pk]))
                self.assertEqual(respuesta.status_code, 403)

    def test_no_superusuario_no_restablece_clave_de_superusuario(self):
        superusuario = Usuario.objects.create_superuser(username="root2", password=CLAVE)

        respuesta = self.client.post(
            reverse("panel:usuarios_clave", args=[superusuario.pk]),
            {"new_password1": "clave-nueva-12345", "new_password2": "clave-nueva-12345"},
        )

        self.assertEqual(respuesta.status_code, 403)
        superusuario.refresh_from_db()
        self.assertTrue(superusuario.check_password(CLAVE))

    def test_no_se_borran_cuentas_con_historial(self):
        usuario = Usuario.objects.create_user(username="con.historial", password=CLAVE)
        transportista = crear_transportista()
        Advertencia.objects.create(
            transportista=transportista, descripcion="Motivo", registrado_por=usuario
        )

        with self.assertRaises(ProtectedError):
            usuario.delete()

        self.assertTrue(Usuario.objects.filter(username="con.historial").exists())


class BorradoDeUsuariosEnAdminTests(TestCase):
    """El panel de administración de Django no permite borrar cuentas."""

    def test_el_admin_no_permite_borrar_usuarios(self):
        modelo_admin = admin.site._registry[Usuario]

        self.assertFalse(modelo_admin.has_delete_permission(request=None))

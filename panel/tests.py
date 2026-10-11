"""Pruebas del panel de inicio y del acceso protegido (R14)."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from asignaciones.reglas import crear_asignacion
from comun.choices import EstadoTransportista
from comun.pruebas import (
    PruebaAutenticada,
    crear_empresa_cliente,
    crear_oferta,
    crear_transportista,
    datos_post_transportista,
)

HOY = timezone.localdate()


class AccesoProtegidoTests(TestCase):
    """T-30: ninguna pantalla de negocio es accesible sin sesión iniciada."""

    @classmethod
    def setUpTestData(cls):
        cls.transportista = crear_transportista()
        cls.empresa = crear_empresa_cliente()
        cls.oferta_cubierta = crear_oferta(empresa=cls.empresa)
        cls.oferta_libre = crear_oferta(empresa=cls.empresa, destino="Cusco")
        cls.asignacion = crear_asignacion(
            transportista=cls.transportista, oferta=cls.oferta_cubierta, fecha_inicio=HOY
        )

    def rutas(self):
        return [
            reverse("panel:inicio"),
            reverse("transportistas:lista"),
            reverse("transportistas:crear"),
            reverse("transportistas:detalle", args=[self.transportista.pk]),
            reverse("transportistas:editar", args=[self.transportista.pk]),
            reverse("transportistas:cambiar_estado", args=[self.transportista.pk]),
            reverse("transportistas:registrar_advertencia", args=[self.transportista.pk]),
            reverse("transportistas:advertencias"),
            reverse("clientes:lista"),
            reverse("clientes:crear"),
            reverse("clientes:detalle", args=[self.empresa.pk]),
            reverse("clientes:editar", args=[self.empresa.pk]),
            reverse("ofertas:lista"),
            reverse("ofertas:crear"),
            reverse("ofertas:detalle", args=[self.oferta_libre.pk]),
            reverse("ofertas:editar", args=[self.oferta_libre.pk]),
            reverse("ofertas:asignar", args=[self.oferta_libre.pk]),
            reverse("asignaciones:lista"),
            reverse("asignaciones:detalle", args=[self.asignacion.pk]),
        ]

    def test_las_rutas_de_negocio_redirigen_al_inicio_de_sesion(self):
        for ruta in self.rutas():
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta)
                self.assertEqual(respuesta.status_code, 302)
                self.assertTrue(respuesta.url.startswith(reverse("login")))

    def test_el_administrador_de_django_tambien_exige_sesion(self):
        respuesta = self.client.get("/admin/")

        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("/admin/login/", respuesta.url)

    def test_finalizar_asignacion_exige_sesion(self):
        respuesta = self.client.post(
            reverse("asignaciones:finalizar", args=[self.asignacion.pk]), {"fecha_fin": HOY.isoformat()}
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta.url.startswith(reverse("login")))


class PanelInicioTests(PruebaAutenticada):
    def test_el_panel_resume_el_estado_del_sistema(self):
        crear_transportista()
        crear_transportista(capacidad_toneladas="3.00")
        crear_transportista(estado=EstadoTransportista.BAJA)
        crear_empresa_cliente()
        crear_oferta()

        respuesta = self.client.get(reverse("panel:inicio"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["total_transportistas"], 3)
        self.assertEqual(respuesta.context["transportistas_activos"], 2)
        self.assertEqual(respuesta.context["transportistas_baja"], 1)
        self.assertEqual(respuesta.context["ofertas_disponibles"], 1)
        self.assertEqual(respuesta.context["ofertas_cubiertas"], 0)

    def test_el_panel_lista_los_documentos_que_vencen_pronto(self):
        crear_transportista(fecha_vencimiento_soat=HOY + timedelta(days=10))

        respuesta = self.client.get(reverse("panel:inicio"))

        self.assertEqual(len(respuesta.context["vencimientos"]), 1)
        self.assertEqual(respuesta.context["vencimientos"][0]["documento"], "SOAT")

    def test_el_panel_omite_los_transportistas_dados_de_baja(self):
        crear_transportista(
            estado=EstadoTransportista.BAJA, fecha_vencimiento_soat=HOY - timedelta(days=1)
        )

        respuesta = self.client.get(reverse("panel:inicio"))

        self.assertEqual(respuesta.context["vencimientos"], [])

    def test_el_panel_muestra_las_ultimas_advertencias(self):
        transportista = crear_transportista()
        from transportistas.models import Advertencia

        Advertencia.objects.create(transportista=transportista, descripcion="Motivo reciente", fecha=HOY)

        respuesta = self.client.get(reverse("panel:inicio"))

        self.assertContains(respuesta, "Motivo reciente")

    def test_el_panel_lista_los_transportistas_dados_de_baja(self):
        transportista = crear_transportista(estado=EstadoTransportista.BAJA)

        respuesta = self.client.get(reverse("panel:inicio"))

        self.assertEqual(list(respuesta.context["transportistas_de_baja"]), [transportista])
        self.assertContains(respuesta, "Transportistas dados de baja")
        self.assertContains(respuesta, transportista.nombre)

    def test_el_panel_no_muestra_la_seccion_de_bajas_si_no_hay_ninguna(self):
        crear_transportista()

        respuesta = self.client.get(reverse("panel:inicio"))

        self.assertEqual(list(respuesta.context["transportistas_de_baja"]), [])
        self.assertNotContains(respuesta, "Transportistas dados de baja")

    def test_la_pagina_de_acceso_se_muestra_en_espanol(self):
        self.client.logout()
        respuesta = self.client.get(reverse("login"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Ingresar")

    def test_estado_vacio_cuando_no_hay_datos(self):
        respuesta = self.client.get(reverse("panel:inicio"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.context["tiene_datos"])
        self.assertContains(respuesta, "Todavía no hay información que mostrar")
        self.assertContains(respuesta, reverse("transportistas:crear"))

    def test_alerta_de_soat_vencido(self):
        transportista = crear_transportista(fecha_vencimiento_soat=HOY - timedelta(days=5))

        respuesta = self.client.get(reverse("panel:inicio"))

        self.assertEqual(len(respuesta.context["soat_vencidos"]), 1)
        self.assertEqual(respuesta.context["soat_por_vencer"], [])
        self.assertContains(respuesta, "SOAT vencido")
        self.assertContains(respuesta, transportista.nombre)

    def test_alerta_de_soat_proximo_a_vencer(self):
        crear_transportista(fecha_vencimiento_soat=HOY + timedelta(days=10))

        respuesta = self.client.get(reverse("panel:inicio"))

        self.assertEqual(len(respuesta.context["soat_por_vencer"]), 1)
        self.assertEqual(respuesta.context["soat_vencidos"], [])
        self.assertContains(respuesta, "SOAT próximo a vencer")


class NavegacionTests(PruebaAutenticada):
    """Estructura de navegación que aporta la plantilla base."""

    def test_la_navegacion_muestra_todas_las_secciones(self):
        respuesta = self.client.get(reverse("panel:inicio"))

        for seccion in (
            "Panel",
            "Transportistas",
            "Empresas clientes",
            "Ofertas de carga",
            "Asignaciones",
            "Advertencias",
            "TransCarga Express",
            "Cerrar sesión",
        ):
            with self.subTest(seccion=seccion):
                self.assertContains(respuesta, seccion)

    def test_el_enlace_a_administracion_solo_aparece_para_staff(self):
        respuesta = self.client.get(reverse("panel:inicio"))
        self.assertNotContains(respuesta, "Panel de Django")

        self.usuario.is_staff = True
        self.usuario.save(update_fields=["is_staff"])
        respuesta = self.client.get(reverse("panel:inicio"))

        self.assertContains(respuesta, "Panel de Django")

    def test_la_pantalla_de_acceso_no_muestra_la_navegacion(self):
        self.client.logout()
        respuesta = self.client.get(reverse("login"))

        self.assertNotContains(respuesta, "Cerrar sesión")
        self.assertNotContains(respuesta, "Empresas clientes")

    def test_los_mensajes_de_exito_se_muestran_al_operador(self):
        respuesta = self.client.post(
            reverse("transportistas:crear"), datos_post_transportista(), follow=True
        )

        self.assertContains(respuesta, "Transportista registrado correctamente")

"""Pruebas de auditoría del panel, de las pantallas y del acceso protegido.

Se añadieron en la auditoría funcional para comprobar tres cosas que no estaban
cubiertas de forma explícita:

* los indicadores del panel coinciden exactamente con la base de datos;
* todas las pantallas de negocio se renderizan (ninguna ruta rota ni plantilla
  con error) y están protegidas;
* el marcado base funciona en móvil y escritorio (viewport, barra lateral
  deslizante y tablas desplazables).
"""

import re
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from asignaciones.models import Asignacion
from asignaciones.reglas import crear_asignacion
from clientes.models import EmpresaCliente
from comun.choices import (
    EstadoAsignacion,
    EstadoOferta,
    EstadoTransportista,
    NivelCarga,
    TipoVehiculo,
)
from comun.pruebas import (
    PruebaAutenticada,
    crear_empresa_cliente,
    crear_oferta,
    crear_transportista,
)
from ofertas.models import OfertaCarga
from transportistas.models import MAXIMO_ADVERTENCIAS, Advertencia, Transportista

HOY = timezone.localdate()


class DatosDePruebaMixin:
    """Conjunto de datos variado: sirve para el panel y para recorrer pantallas."""

    @classmethod
    def crear_datos(cls):
        cls.cliente = crear_empresa_cliente(razon_social="Auditoría Logística S.A.C.")
        cls.otro_cliente = crear_empresa_cliente(razon_social="Carga Pesada del Sur S.R.L.")

        cls.nivel_1 = crear_transportista(
            nombre="Transportista de Nivel Uno",
            capacidad_toneladas="32.00",
            certificacion_carga_peligrosa=True,
            tipo_vehiculo=TipoVehiculo.TRAILER,
        )
        cls.nivel_2 = crear_transportista(nombre="Transportista de Nivel Dos")
        cls.nivel_3 = crear_transportista(
            nombre="Transportista de Nivel Tres",
            capacidad_toneladas="3.00",
            tipo_vehiculo=TipoVehiculo.CAMIONETA,
            estado=EstadoTransportista.EN_RESERVA,
        )
        cls.de_baja = crear_transportista(
            nombre="Transportista Dado de Baja", estado=EstadoTransportista.BAJA
        )
        # Un transportista operativo con el SOAT vencido (alerta roja del panel)
        cls.soat_vencido = crear_transportista(
            nombre="Transportista con SOAT Vencido",
            fecha_vencimiento_soat=HOY - timedelta(days=5),
        )

        # Oferta disponible y oferta cubierta por una asignación activa
        cls.oferta_disponible = crear_oferta(empresa=cls.cliente)
        cls.oferta_con_asignacion = crear_oferta(empresa=cls.cliente, destino="Cusco")
        cls.asignacion_activa = crear_asignacion(
            transportista=cls.nivel_2, oferta=cls.oferta_con_asignacion, fecha_inicio=HOY
        )

        # Oferta cubierta a mano (sin asignación) y asignación finalizada
        cls.oferta_cubierta_sin_asignacion = crear_oferta(empresa=cls.otro_cliente, destino="Piura")
        cls.oferta_cubierta_sin_asignacion.estado = EstadoOferta.CUBIERTA
        cls.oferta_cubierta_sin_asignacion.save(update_fields=["estado", "actualizado"])

        cls.oferta_finalizada = crear_oferta(
            empresa=cls.otro_cliente,
            destino="Tacna",
            tipo_vehiculo_requerido=TipoVehiculo.TRAILER,
            nivel_requerido=NivelCarga.NIVEL_1,
        )
        cls.asignacion_finalizada = crear_asignacion(
            transportista=cls.nivel_1, oferta=cls.oferta_finalizada, fecha_inicio=HOY
        )
        cls.asignacion_finalizada.finalizar(HOY)

        # Advertencias: dos al transportista de baja, una con asignación asociada
        cls.advertencia_1 = Advertencia.objects.create(
            transportista=cls.de_baja, descripcion="Motivo auditado uno", fecha=HOY
        )
        cls.advertencia_2 = Advertencia.objects.create(
            transportista=cls.nivel_2,
            descripcion="Motivo auditado dos",
            fecha=HOY - timedelta(days=2),
            asignacion=cls.asignacion_activa,
        )
        # Un documento por vencer y un SOAT vencido, para las alertas del panel
        cls.nivel_3.fecha_vencimiento_soat = HOY + timedelta(days=10)
        cls.nivel_3.save(update_fields=["fecha_vencimiento_soat", "actualizado"])


class PanelCoincideConLaBaseDeDatosTests(DatosDePruebaMixin, PruebaAutenticada):
    """Indicadores del panel comprobados contra consultas directas a la base de datos."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.crear_datos()

    def test_los_indicadores_coinciden_con_la_base_de_datos(self):
        respuesta = self.client.get(reverse("panel:inicio"))
        contexto = respuesta.context

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(contexto["total_transportistas"], Transportista.objects.count())
        self.assertEqual(
            contexto["transportistas_activos"],
            Transportista.objects.filter(estado=EstadoTransportista.ACTIVO).count(),
        )
        self.assertEqual(
            contexto["transportistas_reserva"],
            Transportista.objects.filter(estado=EstadoTransportista.EN_RESERVA).count(),
        )
        self.assertEqual(
            contexto["transportistas_baja"],
            Transportista.objects.filter(estado=EstadoTransportista.BAJA).count(),
        )
        self.assertEqual(contexto["total_clientes"], EmpresaCliente.objects.count())
        self.assertEqual(
            contexto["ofertas_disponibles"],
            OfertaCarga.objects.filter(estado=EstadoOferta.DISPONIBLE).count(),
        )
        self.assertEqual(
            contexto["ofertas_cubiertas"],
            OfertaCarga.objects.filter(estado=EstadoOferta.CUBIERTA).count(),
        )
        self.assertEqual(
            contexto["asignaciones_activas"],
            Asignacion.objects.filter(estado=EstadoAsignacion.ACTIVA).count(),
        )

        # Los conteos por nivel suman el total de transportistas registrados
        total_por_nivel = 0
        for fila in contexto["conteo_por_nivel"]:
            esperado = Transportista.objects.filter(nivel=fila["nivel"]).count()
            self.assertEqual(fila["total"], esperado)
            total_por_nivel += fila["total"]
        self.assertEqual(total_por_nivel, Transportista.objects.count())

        # Las listas del panel reflejan exactamente lo que hay guardado
        self.assertEqual(
            {t.pk for t in contexto["transportistas_de_baja"]},
            set(
                Transportista.objects.filter(estado=EstadoTransportista.BAJA).values_list(
                    "pk", flat=True
                )
            ),
        )
        self.assertEqual(
            [a.pk for a in contexto["advertencias_recientes"]],
            list(Advertencia.objects.order_by("-fecha", "-id").values_list("pk", flat=True)[:5]),
        )

        # Alertas de SOAT: vencidos y por vencer, con los días calculados
        vencidos_esperados = (
            Transportista.objects.exclude(estado=EstadoTransportista.BAJA)
            .filter(fecha_vencimiento_soat__lt=HOY)
            .values_list("pk", flat=True)
        )
        self.assertEqual({f["transportista"].pk for f in contexto["soat_vencidos"]}, set(vencidos_esperados))
        for fila in contexto["soat_vencidos"]:
            self.assertEqual(
                fila["dias"], (fila["transportista"].fecha_vencimiento_soat - HOY).days
            )
            self.assertLess(fila["dias"], 0)
        for fila in contexto["soat_por_vencer"]:
            self.assertEqual(
                fila["dias"], (fila["transportista"].fecha_vencimiento_soat - HOY).days
            )
            self.assertGreaterEqual(fila["dias"], 0)
            self.assertLessEqual(fila["dias"], 30)

        # Vencimientos: cada fila corresponde a un documento real del transportista
        self.assertLessEqual(len(contexto["vencimientos"]), 10)
        for fila in contexto["vencimientos"]:
            etiquetas = [etiqueta for etiqueta, _ in fila["transportista"].documentos_por_vencer()]
            self.assertIn(fila["documento"], etiquetas)
            self.assertEqual(fila["dias"], (fila["fecha"] - HOY).days)
        self.assertTrue(contexto["tiene_datos"])

    def test_los_numeros_visibles_son_los_mismos_que_los_de_la_base_de_datos(self):
        respuesta = self.client.get(reverse("panel:inicio"))

        activos = Transportista.objects.filter(estado=EstadoTransportista.ACTIVO).count()
        reserva = Transportista.objects.filter(estado=EstadoTransportista.EN_RESERVA).count()
        baja = Transportista.objects.filter(estado=EstadoTransportista.BAJA).count()

        self.assertContains(respuesta, f"{Transportista.objects.count()}")
        self.assertContains(respuesta, f"{activos} activos")
        self.assertContains(respuesta, f"{reserva} en reserva")
        self.assertContains(respuesta, f"{baja} de baja")
        self.assertContains(respuesta, "Máximo una por transportista")

    def test_el_resumen_de_advertencias_del_panel_usa_el_maximo_vigente(self):
        respuesta = self.client.get(reverse("panel:inicio"))

        self.assertEqual(
            Transportista.objects.filter(estado=EstadoTransportista.BAJA).count(), 1
        )
        self.assertContains(respuesta, "Transportistas dados de baja (1)")
        self.assertContains(respuesta, f"{self.de_baja.advertencias_total} de 3")


class PantallasTests(DatosDePruebaMixin, PruebaAutenticada):
    """Todas las pantallas se renderizan y todas exigen sesión iniciada."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.crear_datos()

    def pantallas(self):
        return [
            reverse("panel:inicio"),
            reverse("transportistas:lista"),
            reverse("transportistas:crear"),
            reverse("transportistas:advertencias"),
            reverse("transportistas:detalle", args=[self.nivel_2.pk]),
            reverse("transportistas:detalle", args=[self.de_baja.pk]),
            reverse("transportistas:editar", args=[self.nivel_2.pk]),
            reverse("transportistas:cambiar_estado", args=[self.nivel_2.pk]),
            reverse("transportistas:registrar_advertencia", args=[self.nivel_2.pk]),
            reverse("clientes:lista"),
            reverse("clientes:crear"),
            reverse("clientes:detalle", args=[self.cliente.pk]),
            reverse("clientes:editar", args=[self.cliente.pk]),
            reverse("ofertas:lista"),
            reverse("ofertas:crear"),
            reverse("ofertas:detalle", args=[self.oferta_disponible.pk]),
            reverse("ofertas:detalle", args=[self.oferta_con_asignacion.pk]),
            reverse("ofertas:editar", args=[self.oferta_disponible.pk]),
            reverse("ofertas:cambiar_estado", args=[self.oferta_disponible.pk]),
            reverse("ofertas:asignar", args=[self.oferta_disponible.pk]),
            reverse("asignaciones:lista"),
            reverse("asignaciones:nueva"),
            reverse("asignaciones:detalle", args=[self.asignacion_activa.pk]),
            reverse("asignaciones:finalizar", args=[self.asignacion_activa.pk]),
            reverse("asignaciones:cancelar", args=[self.asignacion_activa.pk]),
            reverse("asignaciones:detalle", args=[self.asignacion_finalizada.pk]),
        ]

    def test_todas_las_pantallas_se_renderizan(self):
        for ruta in self.pantallas():
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta)
                self.assertEqual(respuesta.status_code, 200)

    def test_ninguna_pantalla_de_negocio_es_publica(self):
        self.client.logout()
        for ruta in self.pantallas() + [reverse("asignaciones:confirmar")]:
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta)
                self.assertEqual(respuesta.status_code, 302)
                self.assertTrue(respuesta.url.startswith(reverse("login")))

    def test_los_listados_con_datos_no_desbordan_en_movil(self):
        """Las tablas anchas van dentro de .table-responsive (Bootstrap 5)."""
        paginas_anchas = [
            reverse("transportistas:lista"),
            reverse("transportistas:advertencias"),
            reverse("clientes:lista"),
            reverse("ofertas:lista"),
            reverse("asignaciones:lista"),
        ]
        for ruta in paginas_anchas:
            with self.subTest(ruta=ruta):
                html = self.client.get(ruta).content.decode()
                self.assertIn("table-responsive", html)
                self.assertRegex(html, r"<table[^>]*class=\"[^\"]*table")

    def test_las_pantallas_de_ficha_tambien_son_desplazables(self):
        for ruta in (
            reverse("panel:inicio"),
            reverse("transportistas:detalle", args=[self.nivel_2.pk]),
            reverse("clientes:detalle", args=[self.cliente.pk]),
            reverse("ofertas:detalle", args=[self.oferta_disponible.pk]),
        ):
            with self.subTest(ruta=ruta):
                self.assertIn("table-responsive", self.client.get(ruta).content.decode())

    def test_todas_las_pantallas_declaran_la_vista_movil(self):
        for ruta in self.pantallas():
            with self.subTest(ruta=ruta):
                html = self.client.get(ruta).content.decode()
                self.assertIn('<meta name="viewport" content="width=device-width, initial-scale=1">', html)

    def test_la_estructura_responsive_esta_presente(self):
        html = self.client.get(reverse("panel:inicio")).content.decode()

        # Barra lateral fija en escritorio y deslizante (offcanvas) en móvil
        self.assertIn("offcanvas-lg offcanvas-start", html)
        self.assertIn("barra-superior d-lg-none", html)
        self.assertIn("contenido-principal", html)
        self.assertIn('data-bs-toggle="offcanvas"', html)

    def test_la_confirmacion_de_asignacion_se_renderiza_tras_elegir(self):
        elegible = crear_transportista(nombre="Transportista Elegible para el Resumen")

        respuesta = self.client.post(
            reverse("ofertas:asignar", args=[self.oferta_disponible.pk]),
            {"transportista": elegible.pk, "fecha_inicio": HOY.isoformat(), "fecha_fin": ""},
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta.url, reverse("asignaciones:confirmar"))

        resumen = self.client.get(reverse("asignaciones:confirmar"))

        self.assertEqual(resumen.status_code, 200)
        self.assertContains(resumen, self.oferta_disponible.codigo)
        self.assertContains(resumen, elegible.nombre)
        self.assertContains(resumen, elegible.placa)

    def test_los_formularios_incluyen_la_proteccion_csrf(self):
        for ruta in (
            reverse("transportistas:crear"),
            reverse("clientes:crear"),
            reverse("ofertas:crear"),
            reverse("asignaciones:nueva"),
            reverse("transportistas:registrar_advertencia", args=[self.nivel_2.pk]),
            reverse("asignaciones:finalizar", args=[self.asignacion_activa.pk]),
            reverse("asignaciones:cancelar", args=[self.asignacion_activa.pk]),
            reverse("transportistas:cambiar_estado", args=[self.nivel_2.pk]),
            reverse("ofertas:cambiar_estado", args=[self.oferta_disponible.pk]),
        ):
            with self.subTest(ruta=ruta):
                html = self.client.get(ruta).content.decode()
                self.assertRegex(html, r'name="csrfmiddlewaretoken"')

    def test_la_pantalla_de_acceso_es_la_unica_publica(self):
        self.client.logout()

        respuesta = self.client.get(reverse("login"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Ingresar")
        self.assertIn('<meta name="viewport"', respuesta.content.decode())


class MensajesDeInterfazTests(DatosDePruebaMixin, PruebaAutenticada):
    """Los mensajes de éxito y de error llegan al operador con su texto en español."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.crear_datos()

    def test_mensaje_de_error_al_registrar_un_documento_vencido(self):
        datos = {
            "tipo_documento": "DNI",
            "numero_documento": "10101010",
            "nombre": "Intento Inválido",
            "direccion": "Av. Falsa 100",
            "anios_experiencia": 1,
            "placa": "Z9Z-999",
            "tipo_vehiculo": TipoVehiculo.CAMION,
            "capacidad_toneladas": "10.00",
            "fecha_vencimiento_licencia": (HOY - timedelta(days=1)).isoformat(),
            "fecha_vencimiento_revision_tecnica": HOY.isoformat(),
            "fecha_vencimiento_soat": HOY.isoformat(),
            "estado": EstadoTransportista.ACTIVO,
        }
        respuesta = self.client.post(reverse("transportistas:crear"), datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "licencia de conducir debe estar vigente")
        self.assertFalse(Transportista.objects.filter(numero_documento="10101010").exists())

    def test_mensaje_de_exito_al_registrar_una_advertencia(self):
        respuesta = self.client.post(
            reverse("transportistas:registrar_advertencia", args=[self.nivel_1.pk]),
            {"fecha": HOY.isoformat(), "descripcion": "Motivo informado en la auditoría"},
            follow=True,
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Advertencia registrada")
        self.assertContains(respuesta, "Motivo informado en la auditoría")

    def test_mensaje_de_advertencia_al_llegar_al_maximo(self):
        transportista = crear_transportista(nombre="Acumula Advertencias")
        for numero in range(MAXIMO_ADVERTENCIAS):
            self.client.post(
                reverse("transportistas:registrar_advertencia", args=[transportista.pk]),
                {"fecha": HOY.isoformat(), "descripcion": f"Motivo {numero}"},
            )

        respuesta = self.client.get(reverse("transportistas:detalle", args=[transportista.pk]))

        transportista.refresh_from_db()
        self.assertEqual(transportista.estado, EstadoTransportista.BAJA)
        self.assertContains(respuesta, "está dado de baja")
        self.assertContains(respuesta, f"{MAXIMO_ADVERTENCIAS} advertencias")

    def test_mensaje_claro_cuando_la_oferta_ya_esta_cubierta(self):
        respuesta = self.client.get(
            reverse("ofertas:asignar", args=[self.oferta_con_asignacion.pk]), follow=True
        )

        self.assertContains(respuesta, "ya está cubierta")
        self.assertContains(respuesta, "no puede recibir otra asignación")

    def test_mensaje_claro_al_intentar_reactivar_a_un_transportista_de_baja(self):
        respuesta = self.client.post(
            reverse("transportistas:cambiar_estado", args=[self.de_baja.pk]),
            {"estado": EstadoTransportista.ACTIVO},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "no puede reactivarse desde esta pantalla")
        self.de_baja.refresh_from_db()
        self.assertEqual(self.de_baja.estado, EstadoTransportista.BAJA)

    def test_la_paginacion_conserva_los_filtros_en_el_listado_de_ofertas(self):
        # Se crean ofertas suficientes para tener una segunda página
        for numero in range(12):
            crear_oferta(destino=f"Destino {numero}")

        respuesta = self.client.get(
            reverse("ofertas:lista"),
            {"q": "Destino", "estado": EstadoOferta.DISPONIBLE, "nivel": NivelCarga.NIVEL_2},
        )

        self.assertTrue(respuesta.context["is_paginated"])
        enlace = self.enlace_de_paginacion(respuesta.content.decode(), "page=2")

        self.assertIn("q=Destino", enlace)
        self.assertIn(f"estado={EstadoOferta.DISPONIBLE}", enlace)
        self.assertIn(f"nivel={NivelCarga.NIVEL_2}", enlace)

    @staticmethod
    def enlace_de_paginacion(html, fragmento):
        coincidencia = re.search(r'href="([^"]*' + re.escape(fragmento) + r'[^"]*)"', html)
        assert coincidencia is not None, f"no se encontró el enlace con {fragmento}"
        return coincidencia.group(1)


class IntegridadDeDatosTests(TestCase):
    """Comprobaciones de integridad que no dependen de la interfaz."""

    def test_la_oferta_cubierta_por_asignacion_no_admite_otra(self):
        oferta = crear_oferta()
        crear_asignacion(transportista=crear_transportista(), oferta=oferta, fecha_inicio=HOY)

        otro = crear_transportista()

        with self.assertRaises(ValidationError):
            crear_asignacion(transportista=otro, oferta=oferta, fecha_inicio=HOY)

        self.assertEqual(Asignacion.objects.count(), 1)

    def test_una_asignacion_finalizada_conserva_su_historial(self):
        oferta = crear_oferta()
        transportista = crear_transportista()
        asignacion = crear_asignacion(
            transportista=transportista, oferta=oferta, fecha_inicio=HOY
        )

        asignacion.finalizar(HOY)

        asignacion.refresh_from_db()
        self.assertEqual(asignacion.estado, EstadoAsignacion.FINALIZADA)
        self.assertEqual(asignacion.fecha_fin, HOY)
        self.assertEqual(asignacion.transportista, transportista)
        oferta.refresh_from_db()
        self.assertEqual(oferta.estado, EstadoOferta.CUBIERTA)

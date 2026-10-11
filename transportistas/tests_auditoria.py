"""Pruebas de auditoría del módulo de transportistas.

Cubre huecos detectados en la auditoría funcional: registro con documentos
obligatorios ausentes, edición que intenta dejar Activo un transportista con
documentos vencidos, clasificación por toneladas comprobada desde la interfaz,
archivo con extensión de imagen pero contenido que no es una imagen, y
conservación de los filtros al paginar el listado de advertencias.
"""

import html
import re
from datetime import timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from asignaciones.models import Asignacion
from asignaciones.reglas import crear_asignacion
from comun.choices import EstadoTransportista, NivelCarga, TipoVehiculo
from comun.pruebas import (
    PruebaAutenticada,
    crear_oferta,
    crear_transportista,
    datos_post_transportista,
)
from transportistas.models import Advertencia, Transportista

HOY = timezone.localdate()


class DocumentosObligatoriosTests(PruebaAutenticada):
    """El registro rechaza documentos obligatorios ausentes o vencidos."""

    def test_falta_la_fecha_de_vencimiento_de_la_licencia(self):
        datos = datos_post_transportista()
        datos.pop("fecha_vencimiento_licencia")

        respuesta = self.client.post(reverse("transportistas:crear"), datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("fecha_vencimiento_licencia", respuesta.context["form"].errors)
        self.assertFalse(Transportista.objects.exists())

    def test_falta_la_fecha_de_vencimiento_de_la_revision_tecnica(self):
        datos = datos_post_transportista()
        datos.pop("fecha_vencimiento_revision_tecnica")

        respuesta = self.client.post(reverse("transportistas:crear"), datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("fecha_vencimiento_revision_tecnica", respuesta.context["form"].errors)
        self.assertFalse(Transportista.objects.exists())

    def test_falta_la_fecha_de_vencimiento_del_soat(self):
        datos = datos_post_transportista()
        datos.pop("fecha_vencimiento_soat")

        respuesta = self.client.post(reverse("transportistas:crear"), datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("fecha_vencimiento_soat", respuesta.context["form"].errors)
        self.assertFalse(Transportista.objects.exists())

    def test_falta_el_nombre_o_la_direccion(self):
        for campo in ("nombre", "direccion"):
            with self.subTest(campo=campo):
                datos = datos_post_transportista()
                datos.pop(campo)

                respuesta = self.client.post(reverse("transportistas:crear"), datos)

                self.assertEqual(respuesta.status_code, 200)
                self.assertIn(campo, respuesta.context["form"].errors)
        self.assertFalse(Transportista.objects.exists())

    def test_la_licencia_que_vence_hoy_todavia_permite_el_registro(self):
        datos = datos_post_transportista(fecha_vencimiento_licencia=HOY)

        respuesta = self.client.post(reverse("transportistas:crear"), datos)

        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(Transportista.objects.exists())

    def test_la_licencia_que_vencio_ayer_no_permite_el_registro(self):
        datos = datos_post_transportista(fecha_vencimiento_licencia=HOY - timedelta(days=1))

        respuesta = self.client.post(reverse("transportistas:crear"), datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "licencia de conducir debe estar vigente")
        self.assertFalse(Transportista.objects.exists())


class EdicionDeVigenciasTests(PruebaAutenticada):
    """La edición no puede dejar como Activo un transportista con documentos vencidos."""

    def test_no_se_activa_por_edicion_con_licencia_vencida(self):
        transportista = crear_transportista(estado=EstadoTransportista.EN_RESERVA)
        datos = datos_post_transportista(
            estado=EstadoTransportista.ACTIVO,
            fecha_vencimiento_licencia=HOY - timedelta(days=3),
        )

        respuesta = self.client.post(
            reverse("transportistas:editar", args=[transportista.pk]), datos
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "licencia de conducir debe estar vigente")
        transportista.refresh_from_db()
        self.assertEqual(transportista.estado, EstadoTransportista.EN_RESERVA)

    def test_no_se_activa_por_edicion_con_revision_tecnica_vencida(self):
        transportista = crear_transportista(estado=EstadoTransportista.EN_RESERVA)
        datos = datos_post_transportista(
            estado=EstadoTransportista.ACTIVO,
            fecha_vencimiento_revision_tecnica=HOY - timedelta(days=30),
        )

        respuesta = self.client.post(
            reverse("transportistas:editar", args=[transportista.pk]), datos
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "revisión técnica debe estar vigente")
        transportista.refresh_from_db()
        self.assertEqual(transportista.estado, EstadoTransportista.EN_RESERVA)

    def test_se_puede_guardar_documentacion_vencida_si_sigue_en_reserva(self):
        transportista = crear_transportista(estado=EstadoTransportista.EN_RESERVA)
        datos = datos_post_transportista(
            estado=EstadoTransportista.EN_RESERVA,
            fecha_vencimiento_licencia=HOY - timedelta(days=300),
            fecha_vencimiento_revision_tecnica=HOY - timedelta(days=10),
            fecha_vencimiento_soat=HOY - timedelta(days=200),
        )

        respuesta = self.client.post(
            reverse("transportistas:editar", args=[transportista.pk]), datos
        )

        self.assertEqual(respuesta.status_code, 302)
        transportista.refresh_from_db()
        self.assertEqual(transportista.estado, EstadoTransportista.EN_RESERVA)
        self.assertFalse(transportista.licencia_vigente)


class ClasificacionDesdeLaInterfazTests(PruebaAutenticada):
    """El nivel se calcula con la capacidad y se muestra; nunca se acepta del cliente."""

    def registrar(self, capacidad, certificacion=False, nivel_enviado=None):
        datos = datos_post_transportista(
            capacidad_toneladas=capacidad,
            certificacion_carga_peligrosa="on" if certificacion else "",
        )
        if nivel_enviado is not None:
            datos["nivel"] = str(nivel_enviado)
        return self.client.post(reverse("transportistas:crear"), datos)

    def test_los_limites_de_capacidad_producen_el_nivel_correcto(self):
        casos = [
            ("4.99", False, NivelCarga.NIVEL_3),
            ("5.00", False, NivelCarga.NIVEL_2),
            ("20.00", False, NivelCarga.NIVEL_2),
            ("20.01", True, NivelCarga.NIVEL_1),
            ("60.00", True, NivelCarga.NIVEL_1),
        ]
        for capacidad, certificacion, nivel_esperado in casos:
            with self.subTest(capacidad=capacidad):
                respuesta = self.registrar(capacidad, certificacion)
                self.assertEqual(respuesta.status_code, 302)
                transportista = Transportista.objects.get(
                    capacidad_toneladas=Decimal(capacidad)
                )
                self.assertEqual(transportista.nivel, nivel_esperado)

    def test_el_formulario_no_acepta_un_nivel_del_cliente(self):
        self.registrar("3.00", nivel_enviado=NivelCarga.NIVEL_1)

        transportista = Transportista.objects.get()

        self.assertEqual(transportista.capacidad_toneladas, Decimal("3.00"))
        self.assertEqual(transportista.nivel, NivelCarga.NIVEL_3)

    def test_una_capacidad_de_nivel_1_exige_certificacion(self):
        respuesta = self.registrar("25.00", certificacion=False)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "certificación de carga peligrosa es obligatoria")
        self.assertFalse(Transportista.objects.exists())

    def test_la_ficha_muestra_el_nivel_calculado(self):
        transportista = crear_transportista(
            capacidad_toneladas="32.00",
            certificacion_carga_peligrosa=True,
            tipo_vehiculo=TipoVehiculo.TRAILER,
        )

        respuesta = self.client.get(reverse("transportistas:detalle", args=[transportista.pk]))

        self.assertContains(respuesta, "Nivel 1")
        self.assertContains(respuesta, "32.00")
        self.assertContains(respuesta, "Tráiler")


class FotografiaSospechosaTests(PruebaAutenticada):
    """La validación del archivo no se fía de la extensión: comprueba el contenido."""

    def test_rechaza_un_png_que_no_es_una_imagen(self):
        datos = datos_post_transportista()
        datos["fotografia_vehiculo"] = SimpleUploadedFile(
            "vehiculo.png", b"esto no es una imagen, solo texto", content_type="image/png"
        )

        respuesta = self.client.post(reverse("transportistas:crear"), datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("fotografia_vehiculo", respuesta.context["form"].errors)
        self.assertFalse(Transportista.objects.exists())

    def test_rechaza_un_ejecutable_disfrazado_de_jpg(self):
        datos = datos_post_transportista()
        datos["fotografia_vehiculo"] = SimpleUploadedFile(
            "vehiculo.jpg", b"MZ\x90\x00 programa ejecutable", content_type="image/jpeg"
        )

        respuesta = self.client.post(reverse("transportistas:crear"), datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("fotografia_vehiculo", respuesta.context["form"].errors)
        self.assertFalse(Transportista.objects.exists())

    def test_acepta_una_imagen_png_valida(self):
        datos = datos_post_transportista()

        respuesta = self.client.post(reverse("transportistas:crear"), datos)

        self.assertEqual(respuesta.status_code, 302)
        transportista = Transportista.objects.get()
        self.assertTrue(transportista.fotografia_vehiculo.name.endswith(".png"))


class PaginacionDeAdvertenciasTests(PruebaAutenticada):
    """Los filtros del listado de advertencias sobreviven al cambio de página."""

    def setUp(self):
        super().setUp()
        self.transportista = crear_transportista(nombre="Advertido con muchas faltas")
        self.otro = crear_transportista(nombre="Advertido secundario")
        for numero in range(17):
            Advertencia.objects.create(
                transportista=self.transportista,
                descripcion=f"Retraso & Cía {numero}",
                fecha=HOY - timedelta(days=numero),
            )
        Advertencia.objects.create(
            transportista=self.otro, descripcion="Motivo del otro", fecha=HOY
        )

    def enlaces(self, respuesta):
        return re.findall(r'href="(\?[^"]*)"', respuesta.content.decode())

    def test_la_primera_pagina_esta_paginada(self):
        respuesta = self.client.get(
            reverse("transportistas:advertencias"), {"transportista": self.transportista.pk}
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.context["is_paginated"])
        self.assertTrue(
            any("page=2" in enlace for enlace in self.enlaces(respuesta)),
            "la primera página debe ofrecer el enlace a la segunda",
        )

    def test_la_paginacion_conserva_los_filtros_de_transportista_y_fechas(self):
        desde = (HOY - timedelta(days=20)).isoformat()
        respuesta = self.client.get(
            reverse("transportistas:advertencias"),
            {"transportista": self.transportista.pk, "desde": desde, "hasta": HOY.isoformat()},
        )

        enlace = next(e for e in self.enlaces(respuesta) if "page=2" in e)
        consulta = parse_qs(urlsplit(html.unescape(enlace)).query)

        self.assertEqual(consulta["transportista"], [str(self.transportista.pk)])
        self.assertEqual(consulta["desde"], [desde])
        self.assertEqual(consulta["hasta"], [HOY.isoformat()])

    def test_la_segunda_pagina_sigue_filtrando_por_transportista(self):
        respuesta = self.client.get(
            reverse("transportistas:advertencias"),
            {"transportista": self.transportista.pk, "page": 2},
        )

        advertencias = list(respuesta.context["advertencias"])
        self.assertTrue(advertencias)
        for advertencia in advertencias:
            self.assertEqual(advertencia.transportista_id, self.transportista.pk)
        self.assertLessEqual(len(advertencias), 15)

    def test_la_busqueda_con_caracteres_especiales_viaja_codificada(self):
        busqueda = "Retraso & Cía"
        respuesta = self.client.get(
            reverse("transportistas:advertencias"), {"q": busqueda, "page": 1}
        )

        enlace = next(e for e in self.enlaces(respuesta) if "page=2" in e)
        consulta = parse_qs(urlsplit(html.unescape(enlace)).query)

        self.assertEqual(consulta["q"], [busqueda])

    def test_los_filtros_no_se_pierden_al_paginar_el_listado_de_transportistas(self):
        for numero in range(12):
            crear_transportista(
                nombre=f"Filtrado {numero}",
                estado=EstadoTransportista.EN_RESERVA,
            )

        respuesta = self.client.get(
            reverse("transportistas:lista"),
            {"q": "Filtrado", "estado": EstadoTransportista.EN_RESERVA},
        )

        enlace = next(e for e in self.enlaces(respuesta) if "page=2" in e)
        consulta = parse_qs(urlsplit(html.unescape(enlace)).query)

        self.assertEqual(consulta["q"], ["Filtrado"])
        self.assertEqual(consulta["estado"], [EstadoTransportista.EN_RESERVA])


class AccionesDeAdvertenciaTests(PruebaAutenticada):
    """Coherencia entre el registro de la advertencia y el estado del transportista."""

    def test_la_advertencia_queda_asociada_a_una_asignacion_del_mismo_transportista(self):
        transportista = crear_transportista()
        oferta = crear_oferta()
        asignacion = crear_asignacion(
            transportista=transportista, oferta=oferta, fecha_inicio=HOY
        )

        respuesta = self.client.post(
            reverse("transportistas:registrar_advertencia", args=[transportista.pk]),
            {
                "fecha": HOY.isoformat(),
                "descripcion": "Retraso comprobado en la entrega",
                "asignacion": asignacion.pk,
            },
            follow=True,
        )

        self.assertEqual(respuesta.status_code, 200)
        advertencia = Advertencia.objects.get()
        self.assertEqual(advertencia.transportista, transportista)
        self.assertEqual(advertencia.asignacion, asignacion)
        self.assertEqual(advertencia.registrado_por, self.usuario)
        self.assertEqual(Asignacion.objects.count(), 1)


class EstadosDocumentalesTests(PruebaAutenticada):
    """Cada documento informa Vigente / Próximo / Vencido / Pendiente desde hoy."""

    def test_estado_documento_cubre_los_cuatro_estados(self):
        from comun import fechas as fechas_mod

        self.assertEqual(fechas_mod.estado_documento(HOY + timedelta(days=31))[0], "vigente")
        self.assertEqual(fechas_mod.estado_documento(HOY + timedelta(days=30))[0], "proximo")
        self.assertEqual(fechas_mod.estado_documento(HOY + timedelta(days=1))[0], "proximo")
        self.assertEqual(fechas_mod.estado_documento(HOY)[0], "proximo")
        self.assertEqual(
            fechas_mod.estado_documento(HOY - timedelta(days=1))[0], "vencido"
        )
        self.assertEqual(fechas_mod.estado_documento(None)[0], "pendiente")

    def test_el_umbral_de_proximo_a_vencer_es_de_treinta_dias(self):
        from comun import fechas as fechas_mod

        self.assertEqual(fechas_mod.DIAS_AVISO_VENCIMIENTO, 30)

    def test_la_ficha_muestra_proximo_a_vencer_y_detalle(self):
        transportista = crear_transportista(fecha_vencimiento_soat=HOY + timedelta(days=10))

        respuesta = self.client.get(reverse("transportistas:detalle", args=[transportista.pk]))

        self.assertContains(respuesta, "Próximo a vencer")
        self.assertContains(respuesta, "vence en 10 día(s)")

    def test_la_ficha_muestra_pendiente_cuando_falta_la_fotografia(self):
        transportista = crear_transportista(fotografia_vehiculo="")

        respuesta = self.client.get(reverse("transportistas:detalle", args=[transportista.pk]))

        self.assertContains(respuesta, "Pendiente")
        self.assertContains(respuesta, "No se registró fotografía del vehículo")

    def test_soat_ausente_se_informa_como_pendiente_sin_inventar_fechas(self):
        transportista = crear_transportista()
        transportista.fecha_vencimiento_soat = None

        self.assertIn("SOAT", transportista.documentos_pendientes())
        detalle_soat = [
            documento
            for documento in transportista.documentos_detalle()
            if documento["codigo"] == "soat"
        ][0]
        self.assertIsNone(detalle_soat["fecha"])
        self.assertEqual(detalle_soat["estado"], "pendiente")


class FiltroDocumentalTests(PruebaAutenticada):
    """El listado filtra por vencidos, próximos a vencer y pendientes."""

    def test_filtra_documentos_vencidos(self):
        vencido = crear_transportista(
            nombre="Con SOAT vencido", fecha_vencimiento_soat=HOY - timedelta(days=1)
        )
        crear_transportista(nombre="Con todo vigente")

        respuesta = self.client.get(reverse("transportistas:lista"), {"doc": "vencido"})

        self.assertContains(respuesta, vencido.nombre)
        self.assertNotContains(respuesta, "Con todo vigente")

    def test_filtra_proximos_a_vencer_sin_incluir_vencidos(self):
        proximo = crear_transportista(
            nombre="Con SOAT próximo", fecha_vencimiento_soat=HOY + timedelta(days=10)
        )
        crear_transportista(
            nombre="Con SOAT vencido", fecha_vencimiento_soat=HOY - timedelta(days=1)
        )
        crear_transportista(nombre="Con todo vigente")

        respuesta = self.client.get(reverse("transportistas:lista"), {"doc": "proximo"})

        self.assertContains(respuesta, proximo.nombre)
        self.assertNotContains(respuesta, "Con SOAT vencido")
        self.assertNotContains(respuesta, "Con todo vigente")

    def test_filtra_documentos_pendientes(self):
        pendiente = crear_transportista(nombre="Sin fotografía", fotografia_vehiculo="")
        crear_transportista(nombre="Con todo vigente")

        respuesta = self.client.get(reverse("transportistas:lista"), {"doc": "pendiente"})

        self.assertContains(respuesta, pendiente.nombre)
        self.assertNotContains(respuesta, "Con todo vigente")


class CopiaSoatTests(PruebaAutenticada):
    """La copia del SOAT se registra con el mecanismo de archivos existente."""

    def _documento(self, nombre="soat.pdf", contenido=b"%PDF-1.4 ficticio", tipo="application/pdf"):
        return SimpleUploadedFile(nombre, contenido, content_type=tipo)

    def test_registra_una_copia_en_pdf(self):
        transportista = crear_transportista()
        datos = datos_post_transportista()
        datos["copia_soat"] = self._documento()

        respuesta = self.client.post(
            reverse("transportistas:editar", args=[transportista.pk]), datos
        )

        self.assertEqual(respuesta.status_code, 302)
        transportista.refresh_from_db()
        self.assertTrue(bool(transportista.copia_soat))
        ficha = self.client.get(reverse("transportistas:detalle", args=[transportista.pk]))
        self.assertContains(ficha, "Ver copia del SOAT registrada")

    def test_rechaza_un_tipo_de_archivo_no_permitido(self):
        transportista = crear_transportista()
        datos = datos_post_transportista()
        datos["copia_soat"] = self._documento(
            "soat.exe", b"binario", "application/octet-stream"
        )

        respuesta = self.client.post(
            reverse("transportistas:editar", args=[transportista.pk]), datos
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("copia_soat", respuesta.context["form"].errors)
        transportista.refresh_from_db()
        self.assertFalse(bool(transportista.copia_soat))

    def test_rechaza_una_copia_que_supera_los_cinco_mb(self):
        from transportistas.models import PESO_MAXIMO_COPIA_SOAT

        transportista = crear_transportista()
        datos = datos_post_transportista()
        datos["copia_soat"] = self._documento(contenido=b"x" * (PESO_MAXIMO_COPIA_SOAT + 1))

        respuesta = self.client.post(
            reverse("transportistas:editar", args=[transportista.pk]), datos
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("copia_soat", respuesta.context["form"].errors)

    def test_actualizar_el_soat_despues_del_vencimiento_vuelve_a_habilitar(self):
        transportista = crear_transportista(
            fecha_vencimiento_soat=HOY - timedelta(days=1),
            estado=EstadoTransportista.EN_RESERVA,
        )
        datos = datos_post_transportista(
            fecha_vencimiento_soat=(HOY + timedelta(days=60)).isoformat(),
            estado=EstadoTransportista.EN_RESERVA,
        )
        respuesta = self.client.post(
            reverse("transportistas:editar", args=[transportista.pk]), datos
        )

        self.assertEqual(respuesta.status_code, 302)
        transportista.refresh_from_db()
        self.assertTrue(transportista.soat_vigente)

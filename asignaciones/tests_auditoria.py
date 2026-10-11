"""Pruebas de auditoría del flujo de asignaciones.

Comprueba dos puntos críticos que faltaban: el límite exacto de vigencia del SOAT
(vence hoy = vigente) y la revalidación de las reglas al confirmar, cuando entre
el paso 1 y el paso 2 la oferta se cubrió o el transportista pasó a Baja.
"""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from asignaciones.models import Asignacion
from asignaciones.reglas import crear_asignacion, es_elegible, motivos_no_elegibilidad
from asignaciones.views import CLAVE_SESION
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
from transportistas.models import Transportista

HOY = timezone.localdate()


class VigenciaDelSoatTests(TestCase):
    """El SOAT se evalúa al asignar, con el límite del día incluido."""

    def test_el_soat_que_vence_hoy_todavia_permite_asignar(self):
        transportista = crear_transportista(fecha_vencimiento_soat=HOY)
        oferta = crear_oferta()

        self.assertTrue(transportista.soat_vigente)
        self.assertTrue(es_elegible(transportista, oferta))

        asignacion = crear_asignacion(
            transportista=transportista, oferta=oferta, fecha_inicio=HOY
        )

        self.assertEqual(asignacion.estado, EstadoAsignacion.ACTIVA)

    def test_el_soat_que_vencio_ayer_bloquea_la_asignacion(self):
        transportista = crear_transportista(fecha_vencimiento_soat=HOY - timedelta(days=1))
        oferta = crear_oferta()

        self.assertFalse(es_elegible(transportista, oferta))
        self.assertIn("SOAT", " ".join(motivos_no_elegibilidad(transportista, oferta)))

    def test_la_licencia_que_vence_hoy_todavia_permite_asignar(self):
        transportista = crear_transportista(fecha_vencimiento_licencia=HOY)

        self.assertTrue(es_elegible(transportista, crear_oferta()))

    def test_la_revision_tecnica_que_vence_hoy_todavia_permite_asignar(self):
        transportista = crear_transportista(fecha_vencimiento_revision_tecnica=HOY)

        self.assertTrue(es_elegible(transportista, crear_oferta()))


class RevalidacionAlConfirmarTests(PruebaAutenticada):
    """El paso 2 vuelve a evaluar las reglas: una selección obsoleta no crea nada."""

    def seleccionar(self, oferta, transportista):
        return self.client.post(
            reverse("ofertas:asignar", args=[oferta.pk]),
            {
                "transportista": transportista.pk,
                "fecha_inicio": HOY.isoformat(),
                "fecha_fin": "",
            },
        )

    def test_no_se_confirma_si_la_oferta_se_cubrio_entre_los_dos_pasos(self):
        oferta = crear_oferta()
        elegido = crear_transportista(nombre="Elegido en el paso uno")
        otro = crear_transportista(nombre="Lo cubre antes de confirmar")

        self.seleccionar(oferta, elegido)
        self.assertIn(CLAVE_SESION, self.client.session)

        # Otro operador cubre la oferta antes de que se confirme la selección
        crear_asignacion(transportista=otro, oferta=oferta, fecha_inicio=HOY)

        respuesta = self.client.post(reverse("asignaciones:confirmar"), follow=True)

        oferta.refresh_from_db()
        self.assertEqual(Asignacion.objects.count(), 1)
        self.assertEqual(oferta.estado, EstadoOferta.CUBIERTA)
        self.assertEqual(oferta.asignacion.transportista, otro)
        self.assertContains(respuesta, "ya está cubierta")
        self.assertNotIn(CLAVE_SESION, self.client.session)

    def test_no_se_confirma_si_el_transportista_paso_a_baja_entre_los_dos_pasos(self):
        oferta = crear_oferta()
        transportista = crear_transportista(nombre="Pasa a baja tras la selección")

        self.seleccionar(oferta, transportista)

        transportista.estado = EstadoTransportista.BAJA
        transportista.save(update_fields=["estado", "actualizado"])

        respuesta = self.client.post(reverse("asignaciones:confirmar"), follow=True)

        oferta.refresh_from_db()
        self.assertFalse(Asignacion.objects.exists())
        self.assertEqual(oferta.estado, EstadoOferta.DISPONIBLE)
        self.assertContains(respuesta, "dado de baja")
        self.assertNotIn(CLAVE_SESION, self.client.session)

    def test_la_pantalla_de_confirmacion_avisa_si_la_oferta_ya_no_es_elegible(self):
        oferta = crear_oferta()
        transportista = crear_transportista(nombre="Pierde vigencia tras la selección")

        self.seleccionar(oferta, transportista)

        # El SOAT vence (se registra ayer) antes de confirmar
        transportista.fecha_vencimiento_soat = HOY - timedelta(days=1)
        transportista.save(update_fields=["fecha_vencimiento_soat", "actualizado"])

        resumen = self.client.get(reverse("asignaciones:confirmar"))

        self.assertEqual(resumen.status_code, 200)
        self.assertContains(resumen, "No se puede confirmar esta asignación")
        self.assertContains(resumen, "SOAT del transportista está vencido")
        self.assertNotContains(resumen, 'type="submit">Confirmar asignación')

    def test_confirma_correctamente_cuando_nada_cambio(self):
        oferta = crear_oferta()
        transportista = crear_transportista()

        self.seleccionar(oferta, transportista)
        respuesta = self.client.post(reverse("asignaciones:confirmar"))

        asignacion = Asignacion.objects.get()
        oferta.refresh_from_db()
        self.assertEqual(respuesta.url, reverse("asignaciones:detalle", args=[asignacion.pk]))
        self.assertEqual(oferta.estado, EstadoOferta.CUBIERTA)
        self.assertEqual(asignacion.transportista, transportista)


class EscenariosCriticosTests(TestCase):
    """Los once escenarios críticos de la auditoría, en un solo lugar."""

    def setUp(self):
        self.empresa = crear_empresa_cliente()
        self.oferta = crear_oferta(empresa=self.empresa)

    def test_no_se_puede_asignar_una_oferta_cubierta(self):
        primero = crear_transportista()
        segundo = crear_transportista()
        crear_asignacion(transportista=primero, oferta=self.oferta, fecha_inicio=HOY)

        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.estado, EstadoOferta.CUBIERTA)
        self.assertFalse(es_elegible(segundo, self.oferta))
        with self.assertRaises(ValidationError):
            crear_asignacion(transportista=segundo, oferta=self.oferta, fecha_inicio=HOY)
        self.assertEqual(Asignacion.objects.count(), 1)

    def test_no_se_puede_asignar_un_transportista_con_soat_vencido(self):
        vencido = crear_transportista(fecha_vencimiento_soat=HOY - timedelta(days=1))

        with self.assertRaises(ValidationError):
            crear_asignacion(transportista=vencido, oferta=self.oferta, fecha_inicio=HOY)

        self.assertFalse(Asignacion.objects.exists())
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.estado, EstadoOferta.DISPONIBLE)

    def test_no_se_crean_dos_asignaciones_activas_para_el_mismo_transportista(self):
        transportista = crear_transportista()
        crear_asignacion(transportista=transportista, oferta=self.oferta, fecha_inicio=HOY)

        with self.assertRaises(ValidationError):
            crear_asignacion(
                transportista=transportista,
                oferta=crear_oferta(empresa=self.empresa, destino="Cusco"),
                fecha_inicio=HOY,
            )

        self.assertEqual(
            Asignacion.objects.filter(
                transportista=transportista, estado=EstadoAsignacion.ACTIVA
            ).count(),
            1,
        )

    def test_el_estado_baja_bloquea_cualquier_asignacion_nueva(self):
        de_baja = crear_transportista(estado=EstadoTransportista.BAJA)

        self.assertFalse(es_elegible(de_baja, self.oferta))
        with self.assertRaises(ValidationError):
            crear_asignacion(transportista=de_baja, oferta=self.oferta, fecha_inicio=HOY)

    def test_una_asignacion_valida_cubre_la_oferta(self):
        transportista = crear_transportista()

        asignacion = crear_asignacion(
            transportista=transportista, oferta=self.oferta, fecha_inicio=HOY
        )

        self.oferta.refresh_from_db()
        self.assertEqual(asignacion.estado, EstadoAsignacion.ACTIVA)
        self.assertEqual(self.oferta.estado, EstadoOferta.CUBIERTA)

    def test_el_nivel_1_exige_certificacion_de_carga_peligrosa(self):
        oferta_nivel_1 = crear_oferta(
            empresa=self.empresa,
            destino="Matarani",
            tipo_vehiculo_requerido=TipoVehiculo.TRAILER,
            nivel_requerido=NivelCarga.NIVEL_1,
        )
        sin_certificacion = crear_transportista(
            capacidad_toneladas="30.00",
            certificacion_carga_peligrosa=False,
            tipo_vehiculo=TipoVehiculo.TRAILER,
        )
        con_certificacion = crear_transportista(
            capacidad_toneladas="30.00",
            certificacion_carga_peligrosa=True,
            tipo_vehiculo=TipoVehiculo.TRAILER,
        )

        self.assertFalse(es_elegible(sin_certificacion, oferta_nivel_1))
        self.assertIn(
            "certificación", " ".join(motivos_no_elegibilidad(sin_certificacion, oferta_nivel_1))
        )
        self.assertTrue(es_elegible(con_certificacion, oferta_nivel_1))

    def test_la_clasificacion_por_toneladas_alimenta_la_elegibilidad(self):
        oferta_nivel_3 = crear_oferta(
            empresa=self.empresa,
            destino="Chiclayo",
            tipo_vehiculo_requerido=TipoVehiculo.CAMIONETA,
            nivel_requerido=NivelCarga.NIVEL_3,
        )
        camioneta = crear_transportista(
            capacidad_toneladas="3.00", tipo_vehiculo=TipoVehiculo.CAMIONETA
        )
        camion = crear_transportista(capacidad_toneladas="18.00")

        self.assertEqual(camioneta.nivel, NivelCarga.NIVEL_3)
        self.assertEqual(camion.nivel, NivelCarga.NIVEL_2)
        self.assertTrue(es_elegible(camioneta, oferta_nivel_3))
        self.assertFalse(es_elegible(camion, oferta_nivel_3))

    def test_finalizar_conserva_el_historial_y_libera_al_transportista(self):
        transportista = crear_transportista()
        asignacion = crear_asignacion(
            transportista=transportista, oferta=self.oferta, fecha_inicio=HOY
        )

        asignacion.finalizar(HOY)

        asignacion.refresh_from_db()
        self.oferta.refresh_from_db()
        self.assertEqual(asignacion.estado, EstadoAsignacion.FINALIZADA)
        self.assertEqual(self.oferta.estado, EstadoOferta.CUBIERTA)
        self.assertTrue(Asignacion.objects.filter(pk=asignacion.pk).exists())
        self.assertFalse(transportista.tiene_asignacion_activa)
        self.assertTrue(
            es_elegible(
                transportista, crear_oferta(empresa=self.empresa, destino="Tacna")
            )
        )

    def test_la_tercera_advertencia_produce_la_baja_y_bloquea_asignaciones(self):
        from transportistas.models import Advertencia

        transportista = crear_transportista()
        for numero in range(3):
            Advertencia.objects.create(
                transportista=transportista, descripcion=f"Falta {numero}", fecha=HOY
            )

        transportista.refresh_from_db()
        self.assertEqual(transportista.estado, EstadoTransportista.BAJA)
        self.assertFalse(es_elegible(transportista, self.oferta))
        self.assertIsNone(transportista.asignacion_activa)

    def test_el_total_de_advertencias_se_cuenta_desde_los_registros(self):
        from transportistas.models import Advertencia

        transportista = crear_transportista()
        self.assertEqual(transportista.advertencias_total, 0)

        Advertencia.objects.create(transportista=transportista, descripcion="Una", fecha=HOY)

        self.assertEqual(Transportista.objects.get(pk=transportista.pk).advertencias_total, 1)
        self.assertEqual(transportista.advertencias.count(), 1)

    def test_la_oferta_cubierta_no_vuelve_a_disponible_por_cancelar(self):
        transportista = crear_transportista()
        asignacion = crear_asignacion(
            transportista=transportista, oferta=self.oferta, fecha_inicio=HOY
        )

        asignacion.cancelar(HOY)

        asignacion.refresh_from_db()
        self.oferta.refresh_from_db()
        self.assertEqual(asignacion.estado, EstadoAsignacion.CANCELADA)
        self.assertEqual(self.oferta.estado, EstadoOferta.CUBIERTA)
        self.assertIn(
            "ya está cubierta",
            " ".join(
                motivos_no_elegibilidad(
                    crear_transportista(),
                    OfertaCarga.objects.get(pk=self.oferta.pk),
                )
            ),
        )


class VigenciaAlInicioTests(PruebaAutenticada):
    """La vigencia se exige a la fecha de inicio: creada y ruta no se confunden."""

    def test_bloquea_el_inicio_futuro_si_el_soat_vence_antes(self):
        transportista = crear_transportista(fecha_vencimiento_soat=HOY + timedelta(days=10))
        oferta = crear_oferta()
        inicio = HOY + timedelta(days=20)

        self.assertFalse(es_elegible(transportista, oferta, fecha_referencia=inicio))
        self.assertIn(
            "fecha de inicio",
            " ".join(motivos_no_elegibilidad(transportista, oferta, fecha_referencia=inicio)),
        )

        respuesta = self.client.post(
            reverse("asignaciones:nueva"),
            {
                "oferta": oferta.pk,
                "transportista": transportista.pk,
                "fecha_inicio": inicio.isoformat(),
                "fecha_fin": "",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "fecha de inicio")
        self.assertFalse(Asignacion.objects.exists())

    def test_permite_el_inicio_futuro_con_todo_vigente_al_inicio(self):
        transportista = crear_transportista()
        oferta = crear_oferta()
        inicio = HOY + timedelta(days=10)

        asignacion = crear_asignacion(
            transportista=transportista, oferta=oferta, fecha_inicio=inicio
        )

        self.assertEqual(asignacion.estado, EstadoAsignacion.ACTIVA)
        self.assertEqual(asignacion.fecha_inicio, inicio)

    def test_nombra_el_documento_que_falta_al_intentar_iniciar(self):
        transportista = crear_transportista(
            fecha_vencimiento_licencia=HOY - timedelta(days=1)
        )

        self.assertIn(
            "licencia",
            " ".join(motivos_no_elegibilidad(transportista, crear_oferta())).lower(),
        )

    def test_actualizar_fechas_conserva_el_historial(self):
        transportista = crear_transportista()
        oferta = crear_oferta()
        asignacion = crear_asignacion(
            transportista=transportista, oferta=oferta, fecha_inicio=HOY
        )

        transportista.fecha_vencimiento_soat = HOY + timedelta(days=120)
        transportista.save(update_fields=["fecha_vencimiento_soat", "actualizado"])

        asignacion.refresh_from_db()
        oferta.refresh_from_db()
        self.assertEqual(asignacion.estado, EstadoAsignacion.ACTIVA)
        self.assertEqual(asignacion.transportista_id, transportista.pk)
        self.assertEqual(oferta.estado, EstadoOferta.CUBIERTA)


class AlertaDocumentalEnServicioTests(PruebaAutenticada):
    """Si un documento vence durante la ejecución: alerta, sin cambiar estados."""

    def test_la_ficha_de_la_asignacion_avisa_sin_cambiar_nada(self):
        transportista = crear_transportista()
        asignacion = crear_asignacion(
            transportista=transportista, oferta=crear_oferta(), fecha_inicio=HOY
        )

        transportista.fecha_vencimiento_soat = HOY - timedelta(days=1)
        transportista.save(update_fields=["fecha_vencimiento_soat", "actualizado"])

        respuesta = self.client.get(reverse("asignaciones:detalle", args=[asignacion.pk]))

        self.assertContains(respuesta, "Incidencia documental en servicio")
        self.assertContains(respuesta, "SOAT")
        asignacion.refresh_from_db()
        self.assertEqual(asignacion.estado, EstadoAsignacion.ACTIVA)
        self.assertEqual(transportista.advertencias.count(), 0)

    def test_el_panel_resume_las_asignaciones_con_alerta(self):
        transportista = crear_transportista(nombre="Vence en servicio")
        crear_asignacion(
            transportista=transportista, oferta=crear_oferta(), fecha_inicio=HOY
        )
        transportista.fecha_vencimiento_soat = HOY - timedelta(days=1)
        transportista.save(update_fields=["fecha_vencimiento_soat", "actualizado"])

        respuesta = self.client.get(reverse("panel:inicio"))

        self.assertContains(respuesta, "Incidencia documental en servicio")
        self.assertContains(respuesta, "Vence en servicio")

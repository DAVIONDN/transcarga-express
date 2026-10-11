"""Pruebas de las reglas de los modelos de asignaciones.

Complementa `tests.py` con lo nuevo: estado Cancelada, conservación del historial y
cumplimiento de las restricciones en la base de datos (no solo en las reglas de
aplicación).
"""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.utils import IntegrityError
from django.test import TestCase
from django.utils import timezone

from asignaciones.models import Asignacion
from asignaciones.reglas import crear_asignacion
from comun.choices import EstadoAsignacion, EstadoOferta, EstadoTransportista
from comun.pruebas import crear_empresa_cliente, crear_oferta, crear_transportista
from transportistas.models import Advertencia

HOY = timezone.localdate()


class EstadoCanceladaTests(TestCase):
    """La cancelación deja constancia: no borra nada del historial."""

    def setUp(self):
        self.transportista = crear_transportista()
        self.oferta = crear_oferta()
        self.asignacion = crear_asignacion(
            transportista=self.transportista, oferta=self.oferta, fecha_inicio=HOY
        )

    def test_cancelar_conserva_el_historial_y_la_oferta_cubierta(self):
        cambio = self.asignacion.cancelar(HOY)

        self.assertTrue(cambio)
        self.asignacion.refresh_from_db()
        self.oferta.refresh_from_db()
        self.assertTrue(self.asignacion.esta_cancelada)
        self.assertEqual(self.asignacion.estado, EstadoAsignacion.CANCELADA)
        self.assertEqual(self.asignacion.fecha_fin, HOY)
        self.assertEqual(self.asignacion.fecha_inicio, HOY)
        self.assertEqual(Asignacion.objects.count(), 1)
        self.assertEqual(self.transportista.asignaciones.count(), 1)
        self.assertEqual(self.oferta.estado, EstadoOferta.CUBIERTA)

    def test_cancelar_segunda_vez_no_cambia_nada(self):
        self.asignacion.cancelar(HOY)

        self.assertFalse(self.asignacion.cancelar(HOY + timedelta(days=1)))
        self.asignacion.refresh_from_db()
        self.assertEqual(self.asignacion.fecha_fin, HOY)

    def test_cancelar_con_fecha_anterior_al_inicio_no_se_aplica(self):
        with self.assertRaises(ValidationError):
            self.asignacion.cancelar(HOY - timedelta(days=1))

        self.asignacion.refresh_from_db()
        self.assertTrue(self.asignacion.esta_activa)
        self.assertIsNone(self.asignacion.fecha_fin)

    def test_cancelar_libera_al_transportista_para_otra_asignacion(self):
        self.asignacion.cancelar(HOY)
        empresa = crear_empresa_cliente()

        segunda = crear_asignacion(
            transportista=self.transportista,
            oferta=crear_oferta(empresa=empresa, destino="Cusco"),
            fecha_inicio=HOY,
        )

        self.assertTrue(segunda.esta_activa)
        self.assertEqual(self.transportista.asignaciones.count(), 2)  # ambas conservadas

    def test_la_oferta_sigue_cubierta_tras_cancelar_y_no_admite_otra_asignacion(self):
        """Decisión D6 del plan: la oferta cubierta no se reasigna en el MVP."""
        self.asignacion.cancelar(HOY)
        self.oferta.refresh_from_db()

        with self.assertRaises(ValidationError) as contexto:
            crear_asignacion(
                transportista=crear_transportista(), oferta=self.oferta, fecha_inicio=HOY
            )

        self.assertIn("ya está cubierta", str(contexto.exception))
        self.asignacion.refresh_from_db()
        self.assertTrue(self.asignacion.esta_cancelada)


class FinalizacionTests(TestCase):
    def test_finalizar_conserva_el_historial(self):
        transportista = crear_transportista()
        oferta = crear_oferta()
        asignacion = crear_asignacion(
            transportista=transportista, oferta=oferta, fecha_inicio=HOY
        )

        asignacion.finalizar(HOY)

        asignacion.refresh_from_db()
        oferta.refresh_from_db()
        self.assertTrue(asignacion.esta_finalizada)
        self.assertEqual(asignacion.fecha_fin, HOY)
        self.assertEqual(Asignacion.objects.count(), 1)
        self.assertEqual(transportista.asignaciones.count(), 1)
        self.assertEqual(oferta.estado, EstadoOferta.CUBIERTA)


class RestriccionesBaseDeDatosTests(TestCase):
    """Las restricciones críticas se aplican aunque se omitan las reglas de aplicación."""

    def test_una_asignacion_activa_por_transportista_en_la_base_de_datos(self):
        transportista = crear_transportista()
        crear_asignacion(transportista=transportista, oferta=crear_oferta(), fecha_inicio=HOY)

        with self.assertRaises(IntegrityError), transaction.atomic():
            Asignacion.objects.create(
                transportista=transportista,
                oferta=crear_oferta(),
                fecha_inicio=HOY,
                estado=EstadoAsignacion.ACTIVA,
            )

    def test_una_sola_asignacion_por_oferta_en_la_base_de_datos(self):
        oferta = crear_oferta()
        crear_asignacion(transportista=crear_transportista(), oferta=oferta, fecha_inicio=HOY)

        with self.assertRaises(IntegrityError), transaction.atomic():
            Asignacion.objects.create(
                transportista=crear_transportista(), oferta=oferta, fecha_inicio=HOY
            )

    def test_una_asignacion_cancelada_no_bloquea_la_restriccion_activa(self):
        transportista = crear_transportista()
        empresa = crear_empresa_cliente()
        cancelada = crear_asignacion(
            transportista=transportista, oferta=crear_oferta(empresa=empresa), fecha_inicio=HOY
        )
        cancelada.cancelar(HOY)

        activa = Asignacion.objects.create(
            transportista=transportista,
            oferta=crear_oferta(empresa=empresa, destino="Trujillo"),
            fecha_inicio=HOY,
        )

        self.assertTrue(activa.esta_activa)
        self.assertEqual(Asignacion.objects.filter(transportista=transportista).count(), 2)


class HistorialDelTransportistaTests(TestCase):
    """Cambiar el estado del transportista a Baja no borra sus relaciones."""

    def test_pasar_a_baja_conserva_asignaciones_y_advertencias(self):
        transportista = crear_transportista()
        oferta = crear_oferta()
        crear_asignacion(transportista=transportista, oferta=oferta, fecha_inicio=HOY)
        Advertencia.objects.create(transportista=transportista, descripcion="Motivo conservado")

        transportista.estado = EstadoTransportista.BAJA
        transportista.save(update_fields=["estado", "actualizado"])
        transportista.refresh_from_db()

        self.assertEqual(transportista.estado, EstadoTransportista.BAJA)
        self.assertEqual(transportista.asignaciones.count(), 1)
        self.assertEqual(transportista.advertencias.count(), 1)
        self.assertEqual(Asignacion.objects.count(), 1)
        self.assertEqual(Advertencia.objects.count(), 1)
        self.assertEqual(oferta.asignacion.transportista, transportista)

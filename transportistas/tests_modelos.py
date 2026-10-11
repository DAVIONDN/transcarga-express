"""Pruebas de las reglas de los modelos de transportistas.

Complementa `tests.py` con lo que se valida en el propio modelo (no solo en el
formulario): formato y normalización de placa, y documentación obligatoria.
"""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from comun.choices import EstadoTransportista
from comun.pruebas import PruebaAutenticada, crear_transportista, construir_transportista, datos_post_transportista
from transportistas.models import Transportista, normalizar_placa, validar_placa

HOY = timezone.localdate()


class PlacaTests(TestCase):
    """Formato, normalización y unicidad de la placa."""

    def test_formatos_aceptados(self):
        for placa in ("ABC-123", "A1B-234", "ABC123", "abc-123", "abc123"):
            with self.subTest(placa=placa):
                validar_placa(placa)  # no debe lanzar excepción

    def test_formatos_rechazados(self):
        for placa in ("AB-123", "ABCD-123", "ABC-12", "ABC-1234", "12", "ABC@123"):
            with self.subTest(placa=placa):
                with self.assertRaises(ValidationError):
                    validar_placa(placa)

    def test_placa_vacia_la_controla_el_campo_obligatorio(self):
        validar_placa("")  # el validador no opina; el campo es obligatorio
        with self.assertRaises(ValidationError):
            construir_transportista(placa="").full_clean()

    def test_normalizacion(self):
        self.assertEqual(normalizar_placa("abc123"), "ABC-123")
        self.assertEqual(normalizar_placa("abc-123"), "ABC-123")
        self.assertEqual(normalizar_placa(" a1b 234 "), "A1B-234")
        self.assertEqual(normalizar_placa("ABC 123"), "ABC-123")

    def test_la_placa_se_guarda_normalizada(self):
        transportista = crear_transportista(placa="abc123")

        self.assertEqual(Transportista.objects.get(pk=transportista.pk).placa, "ABC-123")
        self.assertEqual(transportista.placa_normalizada, "ABC-123")

    def test_el_modelo_rechaza_una_placa_mal_formada(self):
        transportista = construir_transportista(placa="AB-1")
        with self.assertRaises(ValidationError) as contexto:
            transportista.full_clean()

        self.assertIn("6 caracteres alfanuméricos", str(contexto.exception))

    def test_la_unicidad_tiene_en_cuenta_la_normalizacion(self):
        ya_existe = crear_transportista(placa="XYZ-901")

        repetida = construir_transportista(placa="xyz901")  # mismo vehículo
        with self.assertRaises(ValidationError) as contexto:
            repetida.full_clean()

        self.assertIn("placa", str(contexto.exception))
        self.assertEqual(ya_existe.placa, "XYZ-901")


class DocumentacionObligatoriaTests(TestCase):
    """R1 a nivel de modelo: obligatorios y vigencia según el estado."""

    def test_numero_de_documento_obligatorio(self):
        transportista = construir_transportista(numero_documento="")
        with self.assertRaises(ValidationError) as contexto:
            transportista.full_clean()

        self.assertIn("numero_documento", str(contexto.exception))

    def test_fotografia_obligatoria(self):
        transportista = construir_transportista(fotografia_vehiculo=None)
        with self.assertRaises(ValidationError) as contexto:
            transportista.full_clean()

        self.assertIn("fotografia_vehiculo", str(contexto.exception))

    def test_activo_exige_licencia_vigente(self):
        transportista = construir_transportista(
            estado=EstadoTransportista.ACTIVO,
            fecha_vencimiento_licencia=HOY - timedelta(days=1),
        )
        with self.assertRaises(ValidationError) as contexto:
            transportista.full_clean()

        self.assertIn("licencia de conducir debe estar vigente", str(contexto.exception))

    def test_activo_exige_revision_tecnica_vigente(self):
        transportista = construir_transportista(
            estado=EstadoTransportista.ACTIVO,
            fecha_vencimiento_revision_tecnica=HOY - timedelta(days=1),
        )
        with self.assertRaises(ValidationError) as contexto:
            transportista.full_clean()

        self.assertIn("revisión técnica debe estar vigente", str(contexto.exception))

    def test_el_soat_vencido_no_impide_guardar(self):
        """El SOAT se comprueba al asignar, así que puede estar vencido en el registro."""
        transportista = construir_transportista(
            estado=EstadoTransportista.ACTIVO,
            fecha_vencimiento_soat=HOY - timedelta(days=30),
        )
        transportista.full_clean()

        self.assertFalse(transportista.soat_vigente)
        self.assertTrue(transportista.documentacion_completa)

    def test_en_reserva_o_baja_pueden_guardar_documentacion_vencida(self):
        for estado in (EstadoTransportista.EN_RESERVA, EstadoTransportista.BAJA):
            with self.subTest(estado=estado):
                transportista = construir_transportista(
                    estado=estado,
                    fecha_vencimiento_licencia=HOY - timedelta(days=10),
                    fecha_vencimiento_revision_tecnica=HOY - timedelta(days=10),
                )
                transportista.full_clean()

    def test_capacidad_cero_o_negativa_no_es_valida(self):
        for capacidad in ("0", "-1.50"):
            with self.subTest(capacidad=capacidad):
                transportista = construir_transportista(
                    capacidad_toneladas=Decimal(capacidad)
                )
                with self.assertRaises(ValidationError) as contexto:
                    transportista.full_clean()
                self.assertIn("capacidad_toneladas", str(contexto.exception))


class PlacaDesdeLaInterfazTests(PruebaAutenticada):
    """La normalización también se ve al enviar el formulario."""

    def test_el_formulario_guarda_la_placa_normalizada(self):
        datos = datos_post_transportista(placa="a1b234")
        respuesta = self.client.post(reverse("transportistas:crear"), datos)

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Transportista.objects.get().placa, "A1B-234")

    def test_el_formulario_rechaza_una_placa_invalida(self):
        datos = datos_post_transportista(placa="A-12")
        respuesta = self.client.post(reverse("transportistas:crear"), datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "6 caracteres alfanuméricos")
        self.assertFalse(Transportista.objects.exists())

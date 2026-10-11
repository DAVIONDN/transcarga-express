"""Pruebas de las reglas críticas de transportistas.

Cubre R1 (documentación obligatoria), R2 (nivel derivado de la capacidad),
R3 (certificación de carga peligrosa), R4/R10 (estado y vigencias),
R7 (baja automática por advertencias), R8 (coherencia de la advertencia) y
R9 (no se borran entidades con historial).
"""

import os
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from asignaciones.forms import AsignacionForm
from asignaciones.models import Asignacion
from asignaciones.reglas import crear_asignacion, es_elegible
from comun.choices import (
    EstadoOferta,
    EstadoTransportista,
    NivelCarga,
    TipoDocumento,
    TipoVehiculo,
)
from comun.pruebas import (
    PruebaAutenticada,
    crear_oferta,
    crear_transportista,
    construir_transportista,
    datos_post_transportista,
)
from transportistas.forms import AdvertenciaForm, CambiarEstadoTransportistaForm, TransportistaForm
from transportistas.models import (
    MAXIMO_ADVERTENCIAS,
    PESO_MAXIMO_FOTOGRAFIA,
    Advertencia,
    Transportista,
)

HOY = timezone.localdate()


class NivelPorCapacidadTests(TestCase):
    """R2: el nivel siempre se deriva de la capacidad."""

    def test_limites_de_los_niveles(self):
        casos = [
            ("4.99", NivelCarga.NIVEL_3, False),
            ("5.00", NivelCarga.NIVEL_2, False),
            ("20.00", NivelCarga.NIVEL_2, False),
            ("20.01", NivelCarga.NIVEL_1, True),
        ]
        for capacidad, nivel_esperado, certificacion in casos:
            with self.subTest(capacidad=capacidad):
                transportista = construir_transportista(
                    capacidad_toneladas=Decimal(capacidad),
                    certificacion_carga_peligrosa=certificacion,
                )
                transportista.full_clean()
                self.assertEqual(transportista.nivel, nivel_esperado)

    def test_el_nivel_se_recalcula_al_guardar(self):
        transportista = crear_transportista(capacidad_toneladas=Decimal("3.00"))
        self.assertEqual(transportista.nivel, NivelCarga.NIVEL_3)

        transportista.capacidad_toneladas = Decimal("25.00")
        transportista.certificacion_carga_peligrosa = True
        transportista.save()

        self.assertEqual(transportista.nivel, NivelCarga.NIVEL_1)


class CertificacionTests(TestCase):
    """R3: la capacidad de Nivel 1 exige certificación de carga peligrosa."""

    def test_capacidad_mayor_a_20_sin_certificacion_es_invalida(self):
        transportista = construir_transportista(
            capacidad_toneladas=Decimal("25.00"),
            certificacion_carga_peligrosa=False,
        )
        with self.assertRaises(ValidationError) as contexto:
            transportista.full_clean()
        self.assertIn("certificación de carga peligrosa", str(contexto.exception))

    def test_certificacion_voluntaria_en_nivel_2_es_valida(self):
        transportista = construir_transportista(
            capacidad_toneladas=Decimal("18.00"),
            certificacion_carga_peligrosa=True,
        )
        transportista.full_clean()
        self.assertEqual(transportista.nivel, NivelCarga.NIVEL_2)


class FormularioTransportistaTests(PruebaAutenticada):
    """R1, R2, R10 y R12 a través del formulario (validación del servidor)."""

    def test_el_nivel_no_puede_manipularse_desde_el_cliente(self):
        # T-05
        datos = datos_post_transportista(capacidad_toneladas="3.00")
        datos["nivel"] = "1"
        respuesta = self.client.post(reverse("transportistas:crear"), datos)

        self.assertEqual(respuesta.status_code, 302)
        transportista = Transportista.objects.get()
        self.assertEqual(transportista.nivel, NivelCarga.NIVEL_3)

    def test_no_se_registra_sin_fotografia(self):
        # T-08
        datos = datos_post_transportista()
        datos.pop("fotografia_vehiculo")
        respuesta = self.client.post(reverse("transportistas:crear"), datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Transportista.objects.exists())
        self.assertContains(respuesta, "fotograf")

    def test_no_se_registra_con_licencia_vencida_siendo_activo(self):
        # T-09
        datos = datos_post_transportista(
            fecha_vencimiento_licencia=HOY - timedelta(days=1),
            estado=EstadoTransportista.ACTIVO,
        )
        respuesta = self.client.post(reverse("transportistas:crear"), datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Transportista.objects.exists())
        self.assertContains(respuesta, "licencia de conducir debe estar vigente")

    def test_no_se_registra_con_revision_tecnica_vencida(self):
        # T-10
        datos = datos_post_transportista(
            fecha_vencimiento_revision_tecnica=HOY - timedelta(days=5)
        )
        respuesta = self.client.post(reverse("transportistas:crear"), datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "revisión técnica debe estar vigente")

    def test_el_soat_vencido_no_impide_el_registro(self):
        # T-11 (el SOAT solo se exige antes de asignar)
        datos = datos_post_transportista(fecha_vencimiento_soat=HOY - timedelta(days=10))
        respuesta = self.client.post(reverse("transportistas:crear"), datos)

        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(Transportista.objects.exists())

    def test_se_permite_guardar_vencido_en_reserva(self):
        # T-28
        datos = datos_post_transportista(
            fecha_vencimiento_licencia=HOY - timedelta(days=30),
            estado=EstadoTransportista.EN_RESERVA,
        )
        respuesta = self.client.post(reverse("transportistas:crear"), datos)

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Transportista.objects.get().estado, EstadoTransportista.EN_RESERVA)

    def test_capacidad_mayor_a_20_sin_certificacion_no_se_guarda(self):
        # T-06 a través del formulario
        datos = datos_post_transportista(
            capacidad_toneladas="25.00", certificacion_carga_peligrosa=""
        )
        respuesta = self.client.post(reverse("transportistas:crear"), datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "certificación de carga peligrosa es obligatoria")

    def test_numero_de_documento_segun_tipo(self):
        datos = datos_post_transportista(tipo_documento=TipoDocumento.RUC, numero_documento="123")
        respuesta = self.client.post(reverse("transportistas:crear"), datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "RUC debe tener 11 dígitos")

    def test_la_capacidad_debe_ser_mayor_que_cero(self):
        datos = datos_post_transportista(capacidad_toneladas="0")
        respuesta = self.client.post(reverse("transportistas:crear"), datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Transportista.objects.exists())

    def test_documento_y_placa_son_unicos(self):
        existente = crear_transportista()
        datos = datos_post_transportista(
            numero_documento=existente.numero_documento, placa=existente.placa
        )
        respuesta = self.client.post(reverse("transportistas:crear"), datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Ya existe un transportista")
        self.assertEqual(Transportista.objects.count(), 1)

    def test_nivel_y_tipo_de_vehiculo_se_calculan_y_muestran(self):
        transporte = crear_transportista(capacidad_toneladas=Decimal("25.00"), certificacion_carga_peligrosa=True)
        respuesta = self.client.get(reverse("transportistas:detalle", args=[transporte.pk]))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Nivel 1")


class EstadoTransportistaTests(PruebaAutenticada):
    """R4 y D7: estados, activación y baja."""

    def test_activar_sin_documentacion_vigente_no_es_posible(self):
        transportista = crear_transportista(
            estado=EstadoTransportista.EN_RESERVA,
            fecha_vencimiento_licencia=HOY - timedelta(days=1),
        )
        formulario = CambiarEstadoTransportistaForm(
            data={"estado": EstadoTransportista.ACTIVO}, transportista=transportista
        )

        self.assertFalse(formulario.is_valid())
        self.assertIn("licencia de conducir vigente", str(formulario.errors))

    def test_transportista_de_baja_no_se_reactiva_desde_la_pantalla(self):
        # T-27
        transportista = crear_transportista(estado=EstadoTransportista.BAJA)
        formulario = CambiarEstadoTransportistaForm(
            data={"estado": EstadoTransportista.ACTIVO}, transportista=transportista
        )

        self.assertFalse(formulario.is_valid())
        self.assertIn("no puede reactivarse", str(formulario.errors))

    def test_pasar_a_en_reserva_es_posible_con_documentacion_vencida(self):
        transportista = crear_transportista(fecha_vencimiento_revision_tecnica=HOY - timedelta(days=3))
        respuesta = self.client.post(
            reverse("transportistas:cambiar_estado", args=[transportista.pk]),
            {"estado": EstadoTransportista.EN_RESERVA},
        )

        self.assertEqual(respuesta.status_code, 302)
        transportista.refresh_from_db()
        self.assertEqual(transportista.estado, EstadoTransportista.EN_RESERVA)

    def test_no_se_permite_elegir_el_mismo_estado(self):
        transportista = crear_transportista()
        formulario = CambiarEstadoTransportistaForm(
            data={"estado": EstadoTransportista.ACTIVO}, transportista=transportista
        )

        self.assertFalse(formulario.is_valid())
        self.assertIn("ya se encuentra en estado", str(formulario.errors))


class AdvertenciaTests(PruebaAutenticada):
    """R7 y R8: límite de advertencias y coherencia con la asignación."""

    def test_tercera_advertencia_pasa_a_baja(self):
        transportista = crear_transportista()
        for numero in range(1, MAXIMO_ADVERTENCIAS):
            Advertencia.objects.create(
                transportista=transportista, descripcion=f"Motivo {numero}"
            )
        transportista.refresh_from_db()
        self.assertEqual(transportista.estado, EstadoTransportista.ACTIVO)

        Advertencia.objects.create(transportista=transportista, descripcion="Motivo 3")

        transportista.refresh_from_db()
        self.assertEqual(transportista.estado, EstadoTransportista.BAJA)
        self.assertEqual(transportista.advertencias_total, MAXIMO_ADVERTENCIAS)

    def test_registrar_advertencia_desde_la_pantalla(self):
        transportista = crear_transportista()
        respuesta = self.client.post(
            reverse("transportistas:registrar_advertencia", args=[transportista.pk]),
            {"fecha": HOY.isoformat(), "descripcion": "Incumplimiento del horario pactado"},
        )

        self.assertEqual(respuesta.status_code, 302)
        advertencia = Advertencia.objects.get()
        self.assertEqual(advertencia.transportista, transportista)
        self.assertEqual(advertencia.registrado_por, self.usuario)

    def test_la_advertencia_debe_corresponder_al_mismo_transportista(self):
        # T-22
        primero = crear_transportista()
        segundo = crear_transportista()
        oferta = crear_oferta()
        asignacion = crear_asignacion(
            transportista=primero, oferta=oferta, fecha_inicio=HOY
        )

        advertencia = Advertencia(
            transportista=segundo,
            asignacion=asignacion,
            descripcion="Motivo cruzado",
            fecha=HOY,
        )
        with self.assertRaises(ValidationError):
            advertencia.full_clean()

        formulario = AdvertenciaForm(
            data={
                "fecha": HOY.isoformat(),
                "descripcion": "Motivo cruzado",
                "asignacion": asignacion.pk,
            },
            transportista=segundo,
        )
        self.assertFalse(formulario.is_valid())
        self.assertIn("asignacion", formulario.errors)

    def test_baja_por_advertencias_impide_nuevas_asignaciones(self):
        transportista = crear_transportista()
        for numero in range(MAXIMO_ADVERTENCIAS):
            Advertencia.objects.create(
                transportista=transportista, descripcion=f"Motivo {numero}"
            )
        transportista.refresh_from_db()
        oferta = crear_oferta()

        with self.assertRaises(ValidationError) as contexto:
            crear_asignacion(transportista=transportista, oferta=oferta, fecha_inicio=HOY)

        self.assertIn("dado de baja", str(contexto.exception))
        oferta.refresh_from_db()
        self.assertEqual(oferta.estado, EstadoOferta.DISPONIBLE)


class HistorialProtegidoTests(TestCase):
    """R9: no se borran transportistas con historial."""

    def test_no_se_puede_borrar_un_transportista_con_asignaciones(self):
        # T-23
        transportista = crear_transportista()
        oferta = crear_oferta()
        crear_asignacion(transportista=transportista, oferta=oferta, fecha_inicio=HOY)

        with self.assertRaises(ProtectedError):
            transportista.delete()

    def test_no_se_puede_borrar_un_transportista_con_advertencias(self):
        transportista = crear_transportista()
        Advertencia.objects.create(transportista=transportista, descripcion="Motivo")

        with self.assertRaises(ProtectedError):
            transportista.delete()


class VistasTransportistaTests(PruebaAutenticada):
    """Comprobaciones básicas de las pantallas de transportistas."""

    def test_listado_con_filtros(self):
        crear_transportista(capacidad_toneladas=Decimal("3.00"))
        crear_transportista(
            capacidad_toneladas=Decimal("25.00"),
            certificacion_carga_peligrosa=True,
            tipo_vehiculo=TipoVehiculo.TRAILER,
        )
        respuesta = self.client.get(reverse("transportistas:lista"), {"nivel": "3"})

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.context["transportistas"]), 1)
        self.assertEqual(respuesta.context["transportistas"][0].nivel, NivelCarga.NIVEL_3)

    def test_busqueda_por_placa(self):
        transportista = crear_transportista()
        respuesta = self.client.get(reverse("transportistas:lista"), {"q": transportista.placa})

        self.assertContains(respuesta, transportista.nombre)

    def test_edicion_recalcula_el_nivel(self):
        transportista = crear_transportista(capacidad_toneladas=Decimal("10.00"))
        datos = datos_post_transportista(
            capacidad_toneladas="22.00",
            certificacion_carga_peligrosa="on",
            estado=EstadoTransportista.ACTIVO,
        )
        respuesta = self.client.post(
            reverse("transportistas:editar", args=[transportista.pk]), datos
        )

        self.assertEqual(respuesta.status_code, 302)
        transportista.refresh_from_db()
        self.assertEqual(transportista.nivel, NivelCarga.NIVEL_1)

    def test_formulario_de_transportista_usa_validacion_del_servidor(self):
        formulario = TransportistaForm()
        self.assertNotIn("nivel", formulario.fields)


class ListaAdvertenciasTests(PruebaAutenticada):
    """Listado general de advertencias (sección del menú de navegación)."""

    def test_muestra_las_advertencias_registradas(self):
        transportista = crear_transportista()
        Advertencia.objects.create(
            transportista=transportista, descripcion="Motivo visible", fecha=HOY
        )

        respuesta = self.client.get(reverse("transportistas:advertencias"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Motivo visible")
        self.assertContains(respuesta, transportista.nombre)

    def test_estado_vacio_explica_donde_registrar(self):
        respuesta = self.client.get(reverse("transportistas:advertencias"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Todavía no hay advertencias registradas")
        self.assertContains(respuesta, "Registrar advertencia")

    def test_busqueda_por_transportista(self):
        primero = crear_transportista(nombre="Alberto Uno")
        segundo = crear_transportista(nombre="Beatriz Dos")
        Advertencia.objects.create(transportista=primero, descripcion="Solo del primero", fecha=HOY)
        Advertencia.objects.create(transportista=segundo, descripcion="Solo del segundo", fecha=HOY)

        respuesta = self.client.get(reverse("transportistas:advertencias"), {"q": "Alberto"})

        self.assertContains(respuesta, "Solo del primero")
        self.assertNotContains(respuesta, "Solo del segundo")

    def test_muestra_el_resumen_de_transportistas_con_advertencias(self):
        transportista = crear_transportista()
        Advertencia.objects.create(transportista=transportista, descripcion="Antecedente", fecha=HOY)

        respuesta = self.client.get(reverse("transportistas:advertencias"))

        self.assertContains(respuesta, "Transportistas con advertencias")
        self.assertContains(respuesta, transportista.placa)


class LimiteDeAdvertenciasTests(PruebaAutenticada):
    """La baja automática al llegar a tres advertencias, paso a paso."""

    def registrar(self, transportista, descripcion, follow=False):
        """Registra una advertencia por la interfaz, con el token del formulario."""
        url = reverse("transportistas:registrar_advertencia", args=[transportista.pk])
        self.client.get(url)  # abre el formulario y genera el token
        datos = {
            "fecha": HOY.isoformat(),
            "descripcion": descripcion,
            "token": self.client.session[f"advertencia_token_{transportista.pk}"],
        }
        return self.client.post(url, datos, follow=follow)

    def test_primera_advertencia_no_da_de_baja(self):
        transportista = crear_transportista()

        respuesta = self.registrar(transportista, "Primera advertencia")

        self.assertEqual(respuesta.status_code, 302)
        transportista.refresh_from_db()
        self.assertEqual(transportista.advertencias_total, 1)
        self.assertEqual(transportista.estado, EstadoTransportista.ACTIVO)
        self.assertTrue(es_elegible(transportista, crear_oferta()))

    def test_segunda_advertencia_sigue_habilitado(self):
        transportista = crear_transportista()

        self.registrar(transportista, "Primera advertencia")
        self.registrar(transportista, "Segunda advertencia")

        transportista.refresh_from_db()
        self.assertEqual(transportista.advertencias_total, 2)
        self.assertEqual(transportista.estado, EstadoTransportista.ACTIVO)
        self.assertTrue(es_elegible(transportista, crear_oferta()))

    def test_tercera_advertencia_cambia_a_baja(self):
        transportista = crear_transportista()
        for numero in (1, 2, 3):
            self.registrar(transportista, f"Motivo {numero}")

        transportista.refresh_from_db()
        self.assertEqual(transportista.advertencias_total, 3)
        self.assertEqual(transportista.estado, EstadoTransportista.BAJA)
        self.assertFalse(es_elegible(transportista, crear_oferta()))

    def test_cuarta_advertencia_no_reactiva_al_transportista(self):
        transportista = crear_transportista()
        for numero in (1, 2, 3, 4):
            self.registrar(transportista, f"Motivo {numero}")

        transportista.refresh_from_db()
        self.assertEqual(transportista.advertencias_total, 4)
        self.assertEqual(transportista.estado, EstadoTransportista.BAJA)

    def test_el_sistema_informa_que_quedo_de_baja(self):
        transportista = crear_transportista()
        self.registrar(transportista, "Motivo 1")
        self.registrar(transportista, "Motivo 2")

        respuesta = self.registrar(transportista, "Motivo 3", follow=True)

        self.assertContains(respuesta, "pasó automáticamente a estado «Baja»")
        self.assertContains(respuesta, "no podrá recibir nuevas asignaciones")

    def test_el_doble_envio_no_registra_dos_advertencias(self):
        transportista = crear_transportista()
        url = reverse("transportistas:registrar_advertencia", args=[transportista.pk])
        self.client.get(url)
        datos = {
            "fecha": HOY.isoformat(),
            "descripcion": "Un solo envío",
            "token": self.client.session[f"advertencia_token_{transportista.pk}"],
        }

        primera = self.client.post(url, datos)
        repetida = self.client.post(url, datos)  # el mismo envío, dos veces

        self.assertEqual(primera.status_code, 302)
        self.assertEqual(repetida.status_code, 302)
        self.assertEqual(Advertencia.objects.filter(transportista=transportista).count(), 1)

    def test_el_historial_de_asignaciones_se_conserva_al_dar_de_baja(self):
        transportista = crear_transportista()
        oferta = crear_oferta()
        asignacion = crear_asignacion(
            transportista=transportista, oferta=oferta, fecha_inicio=HOY
        )
        for numero in (1, 2, 3):
            Advertencia.objects.create(transportista=transportista, descripcion=f"Motivo {numero}")

        transportista.refresh_from_db()
        asignacion.refresh_from_db()

        self.assertEqual(transportista.estado, EstadoTransportista.BAJA)
        self.assertEqual(transportista.asignaciones.count(), 1)  # no se borra
        self.assertEqual(transportista.advertencias.count(), 3)
        self.assertTrue(asignacion.esta_activa)
        self.assertEqual(asignacion.oferta, oferta)

    def test_un_transportista_de_baja_no_puede_asignarse_por_ninguna_via(self):
        oferta = crear_oferta()
        de_baja = crear_transportista(estado=EstadoTransportista.BAJA)

        # 1) No aparece entre los transportistas elegibles
        self.assertNotIn(de_baja, AsignacionForm(oferta=oferta).fields["transportista"].queryset)

        # 2) POST directo a la URL de asignación
        directa = self.client.post(
            reverse("ofertas:asignar", args=[oferta.pk]),
            {"transportista": de_baja.pk, "fecha_inicio": HOY.isoformat()},
        )
        self.assertEqual(directa.status_code, 200)
        self.assertIn("transportista", directa.context["form"].errors)
        self.assertFalse(Asignacion.objects.exists())

        # 3) Manipulando la selección guardada en la sesión
        self.client.session["asignacion_pendiente"] = {
            "oferta_id": oferta.pk,
            "transportista_id": de_baja.pk,
            "fecha_inicio": HOY.isoformat(),
            "fecha_fin": None,
        }
        confirmacion = self.client.post(reverse("asignaciones:confirmar"))
        self.assertEqual(confirmacion.status_code, 302)
        self.assertFalse(Asignacion.objects.exists())
        oferta.refresh_from_db()
        self.assertEqual(oferta.estado, EstadoOferta.DISPONIBLE)

        # 4) Y el servicio centralizado también lo rechaza
        with self.assertRaises(ValidationError):
            crear_asignacion(transportista=de_baja, oferta=oferta, fecha_inicio=HOY)


class FiltrosDeAdvertenciasTests(PruebaAutenticada):
    """Filtros del listado general por transportista y por fecha."""

    def test_filtro_por_transportista(self):
        uno = crear_transportista(nombre="Advertido Uno")
        dos = crear_transportista(nombre="Advertido Dos")
        Advertencia.objects.create(transportista=uno, descripcion="Solo del uno", fecha=HOY)
        Advertencia.objects.create(transportista=dos, descripcion="Solo del dos", fecha=HOY)

        respuesta = self.client.get(
            reverse("transportistas:advertencias"), {"transportista": uno.pk}
        )

        self.assertEqual(list(respuesta.context["advertencias"]), list(uno.advertencias.all()))

    def test_filtro_por_rango_de_fechas(self):
        transportista = crear_transportista()
        Advertencia.objects.create(
            transportista=transportista, descripcion="Antigua", fecha=HOY - timedelta(days=40)
        )
        Advertencia.objects.create(transportista=transportista, descripcion="Reciente", fecha=HOY)
        url = reverse("transportistas:advertencias")

        desde = self.client.get(url, {"desde": (HOY - timedelta(days=7)).isoformat()})
        self.assertEqual([a.descripcion for a in desde.context["advertencias"]], ["Reciente"])

        hasta = self.client.get(url, {"hasta": (HOY - timedelta(days=30)).isoformat()})
        self.assertEqual([a.descripcion for a in hasta.context["advertencias"]], ["Antigua"])

        solo_hoy = self.client.get(
            url, {"desde": HOY.isoformat(), "hasta": HOY.isoformat()}
        )
        self.assertEqual([a.descripcion for a in solo_hoy.context["advertencias"]], ["Reciente"])

    def test_una_fecha_invalida_no_rompe_el_listado(self):
        crear_transportista()

        respuesta = self.client.get(
            reverse("transportistas:advertencias"), {"desde": "no-es-una-fecha"}
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["advertencias"].count(), 0)

    def test_el_listado_muestra_el_total_por_transportista(self):
        transportista = crear_transportista()
        for numero in (1, 2):
            Advertencia.objects.create(
                transportista=transportista, descripcion=f"Motivo {numero}", fecha=HOY
            )

        respuesta = self.client.get(reverse("transportistas:advertencias"))

        resumen = {
            fila.pk: fila.total for fila in respuesta.context["transportistas_con_advertencias"]
        }
        self.assertEqual(resumen[transportista.pk], 2)
        self.assertContains(respuesta, "2 de 3")


class RegistroTransportistaTests(PruebaAutenticada):
    """Casos exigidos por el módulo de transportistas en la interfaz."""

    def test_registro_valido_guarda_todos_los_datos(self):
        datos = datos_post_transportista(
            nombre="Sofía Ramírez Loayza",
            numero_documento="45789012",
            direccion="Av. Los Próceres 456, Lima",
            anios_experiencia=8,
            placa="S8T-741",
            tipo_vehiculo=TipoVehiculo.CAMION,
            capacidad_toneladas="14.50",
        )

        respuesta = self.client.post(reverse("transportistas:crear"), datos)

        self.assertEqual(respuesta.status_code, 302)
        transportista = Transportista.objects.get()
        self.assertEqual(transportista.nombre, "Sofía Ramírez Loayza")
        self.assertEqual(transportista.numero_documento, "45789012")
        self.assertEqual(transportista.direccion, "Av. Los Próceres 456, Lima")
        self.assertEqual(transportista.anios_experiencia, 8)
        self.assertEqual(transportista.placa, "S8T-741")
        self.assertEqual(transportista.capacidad_toneladas, Decimal("14.50"))
        self.assertEqual(transportista.nivel, NivelCarga.NIVEL_2)
        self.assertEqual(transportista.estado, EstadoTransportista.ACTIVO)
        self.assertTrue(transportista.documentacion_completa)
        self.assertTrue(transportista.fotografia_vehiculo)

    def test_documento_duplicado_de_otro_transportista_no_se_permite(self):
        existente = crear_transportista()
        datos = datos_post_transportista(numero_documento=existente.numero_documento)

        respuesta = self.client.post(reverse("transportistas:crear"), datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Ya existe un transportista registrado con este número de documento")
        self.assertEqual(Transportista.objects.count(), 1)

    def test_placa_duplicada_de_otro_vehiculo_no_se_permite(self):
        existente = crear_transportista()
        datos = datos_post_transportista(placa=existente.placa)  # documento distinto

        respuesta = self.client.post(reverse("transportistas:crear"), datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Ya existe un transportista registrado con esta placa")
        self.assertEqual(Transportista.objects.count(), 1)

    def test_edicion_conserva_la_fotografia_si_no_se_sube_otra(self):
        transportista = crear_transportista()
        fotografia_original = transportista.fotografia_vehiculo.name
        datos = datos_post_transportista(capacidad_toneladas="11.00")
        datos.pop("fotografia_vehiculo")

        respuesta = self.client.post(
            reverse("transportistas:editar", args=[transportista.pk]), datos
        )

        self.assertEqual(respuesta.status_code, 302)
        transportista.refresh_from_db()
        self.assertEqual(transportista.fotografia_vehiculo.name, fotografia_original)
        self.assertEqual(transportista.capacidad_toneladas, Decimal("11.00"))

    def test_cambiar_a_en_reserva_conserva_el_historial(self):
        transportista = crear_transportista()
        Advertencia.objects.create(transportista=transportista, descripcion="Motivo previo", fecha=HOY)
        asignacion = crear_asignacion(
            transportista=transportista, oferta=crear_oferta(), fecha_inicio=HOY
        )

        respuesta = self.client.post(
            reverse("transportistas:cambiar_estado", args=[transportista.pk]),
            {"estado": EstadoTransportista.EN_RESERVA},
        )

        self.assertEqual(respuesta.status_code, 302)
        transportista.refresh_from_db()
        asignacion.refresh_from_db()
        self.assertEqual(transportista.estado, EstadoTransportista.EN_RESERVA)
        self.assertEqual(transportista.advertencias.count(), 1)   # historial intacto
        self.assertEqual(transportista.asignaciones.count(), 1)
        self.assertTrue(asignacion.esta_activa)

        # En Reserva ya no puede recibir una nueva asignación
        with self.assertRaises(ValidationError) as contexto:
            crear_asignacion(
                transportista=transportista,
                oferta=crear_oferta(destino="Cusco"),
                fecha_inicio=HOY,
            )
        self.assertIn("En Reserva", str(contexto.exception))

    def test_la_ficha_muestra_fotografia_documentos_y_advertencias(self):
        transportista = crear_transportista()
        Advertencia.objects.create(transportista=transportista, descripcion="Antecedente visible", fecha=HOY)

        respuesta = self.client.get(reverse("transportistas:detalle", args=[transportista.pk]))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, transportista.fotografia_vehiculo.url)
        self.assertContains(respuesta, "Licencia de conducir")
        self.assertContains(respuesta, "Revisión técnica")
        self.assertContains(respuesta, "SOAT")
        self.assertContains(respuesta, transportista.fecha_vencimiento_soat.strftime("%d/%m/%Y"))
        self.assertContains(respuesta, transportista.fecha_vencimiento_licencia.strftime("%d/%m/%Y"))
        self.assertContains(respuesta, "Antecedente visible")
        self.assertContains(respuesta, "1 de 3")

    def test_el_listado_muestra_los_campos_utiles_y_deja_el_detalle_para_la_ficha(self):
        transportista = crear_transportista()

        respuesta = self.client.get(reverse("transportistas:lista"))

        self.assertContains(respuesta, transportista.nombre)
        self.assertContains(respuesta, transportista.numero_documento)
        self.assertContains(respuesta, transportista.placa)
        self.assertContains(respuesta, "Nivel 2")
        self.assertContains(respuesta, "Activo")
        self.assertNotContains(respuesta, transportista.direccion)

    def test_busqueda_por_documento(self):
        buscado = crear_transportista(numero_documento="45678901")
        crear_transportista(numero_documento="45999999")

        respuesta = self.client.get(reverse("transportistas:lista"), {"q": "45678901"})

        self.assertEqual(len(respuesta.context["transportistas"]), 1)
        self.assertEqual(respuesta.context["transportistas"][0].pk, buscado.pk)

    def test_filtro_por_estado(self):
        activo = crear_transportista()
        de_baja = crear_transportista(estado=EstadoTransportista.BAJA)

        respuesta = self.client.get(
            reverse("transportistas:lista"), {"estado": EstadoTransportista.BAJA}
        )

        self.assertEqual(list(respuesta.context["transportistas"]), [de_baja])
        self.assertNotIn(activo, respuesta.context["transportistas"])


class FotografiaVehiculoTests(PruebaAutenticada):
    """Validación del archivo en el servidor: obligatorio, formato y tamaño."""

    def contenido_imagen_grande(self):
        """PNG válido de más de 5 MB (ruido aleatorio, que no se comprime)."""
        lado = 1600
        buffer = BytesIO()
        Image.frombytes("RGB", (lado, lado), os.urandom(lado * lado * 3)).save(buffer, format="PNG")
        return buffer.getvalue()

    def test_la_fotografia_es_obligatoria(self):
        datos = datos_post_transportista()
        datos.pop("fotografia_vehiculo")

        respuesta = self.client.post(reverse("transportistas:crear"), datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("fotografia_vehiculo", respuesta.context["form"].errors)
        self.assertFalse(Transportista.objects.exists())

    def test_rechaza_un_archivo_que_no_es_imagen(self):
        datos = datos_post_transportista()
        datos["fotografia_vehiculo"] = SimpleUploadedFile(
            "documento.pdf", b"%PDF-1.4 esto no es una imagen", content_type="application/pdf"
        )

        respuesta = self.client.post(reverse("transportistas:crear"), datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("fotografia_vehiculo", respuesta.context["form"].errors)
        self.assertFalse(Transportista.objects.exists())

    def test_rechaza_un_formato_de_imagen_no_permitido(self):
        buffer = BytesIO()
        Image.new("RGB", (8, 8), "white").save(buffer, format="GIF")
        datos = datos_post_transportista()
        datos["fotografia_vehiculo"] = SimpleUploadedFile(
            "vehiculo.gif", buffer.getvalue(), content_type="image/gif"
        )

        respuesta = self.client.post(reverse("transportistas:crear"), datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "debe estar en formato JPG o PNG")
        self.assertFalse(Transportista.objects.exists())

    def test_rechaza_una_fotografia_demasiado_grande(self):
        contenido = self.contenido_imagen_grande()
        self.assertGreater(len(contenido), PESO_MAXIMO_FOTOGRAFIA)  # supuesto del caso
        datos = datos_post_transportista()
        datos["fotografia_vehiculo"] = SimpleUploadedFile(
            "vehiculo_grande.png", contenido, content_type="image/png"
        )

        respuesta = self.client.post(reverse("transportistas:crear"), datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "no debe pesar más de 5 MB")
        self.assertFalse(Transportista.objects.exists())

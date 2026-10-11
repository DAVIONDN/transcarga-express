"""Pruebas de las reglas críticas de asignaciones (R5, R6, R11 y R12)."""

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

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
from asignaciones.forms import AsignacionForm, FinalizarAsignacionForm
from asignaciones.models import Asignacion
from asignaciones.reglas import candidatos, crear_asignacion, es_elegible, motivos_no_elegibilidad
from ofertas.models import OfertaCarga

HOY = timezone.localdate()


class CrearAsignacionTests(TestCase):
    def test_asignacion_valida_marca_la_oferta_como_cubierta(self):
        # T-19
        transportista = crear_transportista()
        oferta = crear_oferta()

        asignacion = crear_asignacion(
            transportista=transportista, oferta=oferta, fecha_inicio=HOY
        )

        self.assertEqual(asignacion.estado, EstadoAsignacion.ACTIVA)
        oferta.refresh_from_db()
        self.assertEqual(oferta.estado, EstadoOferta.CUBIERTA)

    def test_un_fallo_al_crear_no_deja_cambios_parciales(self):
        """La transacción garantiza que no quede una asignación ni una oferta a medias."""
        transportista = crear_transportista()
        oferta = crear_oferta()

        with mock.patch.object(OfertaCarga, "save", side_effect=RuntimeError("fallo simulado")):
            with self.assertRaises(RuntimeError):
                crear_asignacion(transportista=transportista, oferta=oferta, fecha_inicio=HOY)

        self.assertFalse(Asignacion.objects.exists())
        oferta.refresh_from_db()
        self.assertEqual(oferta.estado, EstadoOferta.DISPONIBLE)

    def test_no_se_asigna_con_soat_vencido(self):
        # T-12
        transportista = crear_transportista(fecha_vencimiento_soat=HOY - timedelta(days=1))
        oferta = crear_oferta()

        with self.assertRaises(ValidationError) as contexto:
            crear_asignacion(transportista=transportista, oferta=oferta, fecha_inicio=HOY)

        self.assertIn("SOAT", str(contexto.exception))
        self.assertFalse(Asignacion.objects.exists())
        oferta.refresh_from_db()
        self.assertEqual(oferta.estado, EstadoOferta.DISPONIBLE)

    def test_una_oferta_cubierta_no_recibe_otra_asignacion(self):
        # T-13
        primera = crear_transportista()
        segunda = crear_transportista()
        oferta = crear_oferta()
        crear_asignacion(transportista=primera, oferta=oferta, fecha_inicio=HOY)

        with self.assertRaises(ValidationError) as contexto:
            crear_asignacion(transportista=segunda, oferta=oferta, fecha_inicio=HOY)

        self.assertIn("ya está cubierta", str(contexto.exception))
        self.assertEqual(Asignacion.objects.count(), 1)

    def test_un_transportista_no_puede_tener_dos_asignaciones_activas(self):
        # T-14
        transportista = crear_transportista()
        empresa = crear_empresa_cliente()
        crear_asignacion(transportista=transportista, oferta=crear_oferta(empresa=empresa), fecha_inicio=HOY)

        with self.assertRaises(ValidationError) as contexto:
            crear_asignacion(
                transportista=transportista, oferta=crear_oferta(empresa=empresa), fecha_inicio=HOY
            )

        self.assertIn("ya tiene una asignación activa", str(contexto.exception))

    def test_no_se_asigna_a_un_transportista_de_baja(self):
        # T-15
        transportista = crear_transportista(estado=EstadoTransportista.BAJA)
        oferta = crear_oferta()

        with self.assertRaises(ValidationError) as contexto:
            crear_asignacion(transportista=transportista, oferta=oferta, fecha_inicio=HOY)

        self.assertIn("dado de baja", str(contexto.exception))

    def test_no_se_asigna_a_un_transportista_en_reserva(self):
        # T-16
        transportista = crear_transportista(estado=EstadoTransportista.EN_RESERVA)
        oferta = crear_oferta()

        with self.assertRaises(ValidationError) as contexto:
            crear_asignacion(transportista=transportista, oferta=oferta, fecha_inicio=HOY)

        self.assertIn("En Reserva", str(contexto.exception))

    def test_el_nivel_debe_coincidir_exactamente(self):
        # T-17
        transportista = crear_transportista(capacidad_toneladas=Decimal("25.00"), certificacion_carga_peligrosa=True)
        oferta = crear_oferta(nivel_requerido=NivelCarga.NIVEL_2)

        with self.assertRaises(ValidationError) as contexto:
            crear_asignacion(transportista=transportista, oferta=oferta, fecha_inicio=HOY)

        self.assertIn("no coincide con el nivel requerido", str(contexto.exception))

        transportista_nivel_3 = crear_transportista(capacidad_toneladas=Decimal("3.00"))
        with self.assertRaises(ValidationError):
            crear_asignacion(
                transportista=transportista_nivel_3,
                oferta=crear_oferta(nivel_requerido=NivelCarga.NIVEL_2),
                fecha_inicio=HOY,
            )

    def test_el_tipo_de_vehiculo_debe_coincidir(self):
        # T-18
        transportista = crear_transportista(tipo_vehiculo=TipoVehiculo.CISTERNA)
        oferta = crear_oferta(tipo_vehiculo_requerido=TipoVehiculo.CAMION)

        with self.assertRaises(ValidationError) as contexto:
            crear_asignacion(transportista=transportista, oferta=oferta, fecha_inicio=HOY)

        self.assertIn("tipo de vehículo", str(contexto.exception))

    def test_una_oferta_de_nivel_1_exige_certificacion(self):
        # Transportista Nivel 1 inconsistente a propósito (creado sin validación completa)
        transportista = crear_transportista(
            capacidad_toneladas=Decimal("25.00"), certificacion_carga_peligrosa=False
        )
        oferta = crear_oferta(
            nivel_requerido=NivelCarga.NIVEL_1, tipo_vehiculo_requerido=TipoVehiculo.CAMION
        )

        with self.assertRaises(ValidationError) as contexto:
            crear_asignacion(transportista=transportista, oferta=oferta, fecha_inicio=HOY)

        self.assertIn("certificación de carga peligrosa", str(contexto.exception))

    def test_la_fecha_de_fin_no_puede_ser_anterior_al_inicio(self):
        # T-24
        transportista = crear_transportista()
        oferta = crear_oferta()

        with self.assertRaises(ValidationError) as contexto:
            crear_asignacion(
                transportista=transportista,
                oferta=oferta,
                fecha_inicio=HOY,
                fecha_fin=HOY - timedelta(days=1),
            )

        self.assertIn("no puede ser anterior", str(contexto.exception))

    def test_finalizar_libera_al_transportista_para_otra_asignacion(self):
        # T-20
        transportista = crear_transportista()
        empresa = crear_empresa_cliente()
        primera = crear_asignacion(
            transportista=transportista, oferta=crear_oferta(empresa=empresa), fecha_inicio=HOY
        )
        primera.estado = EstadoAsignacion.FINALIZADA
        primera.fecha_fin = HOY
        primera.save()

        segunda = crear_asignacion(
            transportista=transportista, oferta=crear_oferta(empresa=empresa), fecha_inicio=HOY
        )

        self.assertEqual(segunda.estado, EstadoAsignacion.ACTIVA)
        self.assertEqual(Asignacion.objects.count(), 2)

    def test_un_cliente_puede_asignar_distintos_transportistas_a_distintas_ofertas(self):
        empresa = crear_empresa_cliente()
        primero = crear_transportista()
        segundo = crear_transportista()

        una = crear_asignacion(
            transportista=primero, oferta=crear_oferta(empresa=empresa, destino="Trujillo"), fecha_inicio=HOY
        )
        otra = crear_asignacion(
            transportista=segundo, oferta=crear_oferta(empresa=empresa, destino="Cusco"), fecha_inicio=HOY
        )

        self.assertEqual(una.oferta.empresa_cliente, otra.oferta.empresa_cliente)
        self.assertNotEqual(una.transportista, otra.transportista)


class ReglasDeElegibilidadTests(TestCase):
    def test_candidatos_incluye_motivos_y_elegibles(self):
        oferta = crear_oferta()
        elegible = crear_transportista()
        sin_soat = crear_transportista(fecha_vencimiento_soat=HOY - timedelta(days=2))
        de_baja = crear_transportista(estado=EstadoTransportista.BAJA)

        evaluados = candidatos(oferta)

        self.assertEqual(len(evaluados), 2)  # el transportista de baja no se lista
        resultado = {fila["transportista"].pk: fila for fila in evaluados}
        self.assertTrue(resultado[elegible.pk]["elegible"])
        self.assertFalse(resultado[sin_soat.pk]["elegible"])
        self.assertNotIn(de_baja.pk, resultado)
        self.assertTrue(candidatos(oferta, incluir_baja=True)[-1]["transportista"] is not None)

    def test_es_elegible_devuelve_falso_con_oferta_cubierta(self):
        transportista = crear_transportista()
        oferta = crear_oferta()
        crear_asignacion(transportista=transportista, oferta=oferta, fecha_inicio=HOY)
        oferta.refresh_from_db()

        self.assertFalse(es_elegible(transportista, oferta))
        self.assertIn("ya está cubierta", " ".join(motivos_no_elegibilidad(transportista, oferta)))


class VistasAsignacionTests(PruebaAutenticada):
    def test_asignar_desde_la_oferta_se_confirma_en_dos_pasos(self):
        oferta = crear_oferta()
        transportista = crear_transportista()

        primer_paso = self.client.post(
            reverse("ofertas:asignar", args=[oferta.pk]),
            {
                "transportista": transportista.pk,
                "fecha_inicio": HOY.isoformat(),
                "fecha_fin": "",
            },
        )

        # Todavía no se crea nada: primero se confirma
        self.assertEqual(primer_paso.status_code, 302)
        self.assertEqual(primer_paso.url, reverse("asignaciones:confirmar"))
        self.assertFalse(Asignacion.objects.exists())
        oferta.refresh_from_db()
        self.assertEqual(oferta.estado, EstadoOferta.DISPONIBLE)

        # El resumen muestra oferta, empresa cliente, transportista y vehículo
        resumen = self.client.get(reverse("asignaciones:confirmar"))
        self.assertEqual(resumen.status_code, 200)
        for dato in (
            oferta.codigo,
            oferta.empresa_cliente.razon_social,
            transportista.nombre,
            transportista.placa,
            transportista.get_tipo_vehiculo_display(),
        ):
            with self.subTest(dato=dato):
                self.assertContains(resumen, dato)

        confirmacion = self.client.post(reverse("asignaciones:confirmar"))

        asignacion = Asignacion.objects.get()
        self.assertEqual(confirmacion.url, reverse("asignaciones:detalle", args=[asignacion.pk]))
        self.assertEqual(asignacion.estado, EstadoAsignacion.ACTIVA)
        oferta.refresh_from_db()
        self.assertEqual(oferta.estado, EstadoOferta.CUBIERTA)

    def test_flujo_general_eligiendo_la_oferta_disponible(self):
        oferta = crear_oferta()
        transportista = crear_transportista()

        primer_paso = self.client.post(
            reverse("asignaciones:nueva"),
            {
                "oferta": oferta.pk,
                "transportista": transportista.pk,
                "fecha_inicio": HOY.isoformat(),
            },
        )

        self.assertEqual(primer_paso.status_code, 302)
        self.assertEqual(primer_paso.url, reverse("asignaciones:confirmar"))
        self.assertFalse(Asignacion.objects.exists())

        self.client.post(reverse("asignaciones:confirmar"))

        asignacion = Asignacion.objects.get()
        self.assertEqual(asignacion.oferta, oferta)
        oferta.refresh_from_db()
        self.assertEqual(oferta.estado, EstadoOferta.CUBIERTA)

    def test_el_formulario_general_solo_ofrece_ofertas_disponibles(self):
        disponible = crear_oferta()
        cubierta = crear_oferta(destino="Cusco")
        crear_asignacion(transportista=crear_transportista(), oferta=cubierta, fecha_inicio=HOY)

        respuesta = self.client.get(reverse("asignaciones:nueva"))

        ofertas = list(respuesta.context["form"].fields["oferta"].queryset)
        self.assertIn(disponible, ofertas)
        self.assertNotIn(cubierta, ofertas)

    def test_confirmar_sin_seleccion_pendiente(self):
        respuesta = self.client.get(reverse("asignaciones:confirmar"))

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta.url, reverse("asignaciones:nueva"))

    def test_no_se_asigna_si_la_documentacion_no_esta_completa_ni_vigente(self):
        oferta = crear_oferta()
        casos = {
            "licencia vencida": {"fecha_vencimiento_licencia": HOY - timedelta(days=1)},
            "revisión técnica vencida": {
                "fecha_vencimiento_revision_tecnica": HOY - timedelta(days=1)
            },
            "sin fotografía": {"fotografia_vehiculo": ""},
        }
        for descripcion, cambios in casos.items():
            with self.subTest(caso=descripcion):
                transportista = crear_transportista(**cambios)
                formulario = AsignacionForm(
                    data={"transportista": transportista.pk, "fecha_inicio": HOY.isoformat()},
                    oferta=oferta,
                )
                self.assertFalse(formulario.is_valid())
                self.assertIn("no está vigente" if "sin" not in descripcion else "fotografía",
                              str(formulario.errors))

    def test_la_pantalla_rechaza_un_transportista_no_elegible(self):
        oferta = crear_oferta()
        transportista = crear_transportista(fecha_vencimiento_soat=HOY - timedelta(days=1))

        respuesta = self.client.post(
            reverse("ofertas:asignar", args=[oferta.pk]),
            {"transportista": transportista.pk, "fecha_inicio": HOY.isoformat()},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "SOAT del transportista está vencido")
        self.assertFalse(Asignacion.objects.exists())

    def test_no_se_ofrece_asignar_una_oferta_ya_cubierta(self):
        oferta = crear_oferta()
        crear_asignacion(transportista=crear_transportista(), oferta=oferta, fecha_inicio=HOY)

        respuesta = self.client.get(reverse("ofertas:asignar", args=[oferta.pk]))

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta.url, reverse("ofertas:detalle", args=[oferta.pk]))

    def test_finalizar_desde_la_pantalla_con_confirmacion(self):
        oferta = crear_oferta()
        asignacion = crear_asignacion(
            transportista=crear_transportista(), oferta=oferta, fecha_inicio=HOY
        )

        confirmacion = self.client.get(reverse("asignaciones:finalizar", args=[asignacion.pk]))
        self.assertEqual(confirmacion.status_code, 200)
        self.assertContains(confirmacion, "Confirmar finalización")

        respuesta = self.client.post(
            reverse("asignaciones:finalizar", args=[asignacion.pk]),
            {"fecha_fin": HOY.isoformat()},
        )

        self.assertEqual(respuesta.status_code, 302)
        asignacion.refresh_from_db()
        self.assertEqual(asignacion.estado, EstadoAsignacion.FINALIZADA)
        self.assertEqual(asignacion.fecha_fin, HOY)
        oferta.refresh_from_db()
        self.assertEqual(oferta.estado, EstadoOferta.CUBIERTA)

    def test_no_se_finaliza_con_fecha_anterior_al_inicio(self):
        asignacion = crear_asignacion(
            transportista=crear_transportista(),
            oferta=crear_oferta(),
            fecha_inicio=HOY,
        )

        respuesta = self.client.post(
            reverse("asignaciones:finalizar", args=[asignacion.pk]),
            {"fecha_fin": (HOY - timedelta(days=3)).isoformat()},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "no puede ser anterior")
        asignacion.refresh_from_db()
        self.assertEqual(asignacion.estado, EstadoAsignacion.ACTIVA)

    def test_cancelar_desde_la_pantalla_conserva_el_historial(self):
        oferta = crear_oferta()
        asignacion = crear_asignacion(
            transportista=crear_transportista(), oferta=oferta, fecha_inicio=HOY
        )

        confirmacion = self.client.get(reverse("asignaciones:cancelar", args=[asignacion.pk]))
        self.assertEqual(confirmacion.status_code, 200)
        self.assertContains(confirmacion, "Confirmar cancelación")

        respuesta = self.client.post(
            reverse("asignaciones:cancelar", args=[asignacion.pk]),
            {"fecha": HOY.isoformat(), "motivo": "El cliente anuló la carga"},
        )

        self.assertEqual(respuesta.status_code, 302)
        asignacion.refresh_from_db()
        oferta.refresh_from_db()
        self.assertTrue(asignacion.esta_cancelada)
        self.assertEqual(asignacion.motivo_cancelacion, "El cliente anuló la carga")
        self.assertEqual(asignacion.fecha_fin, HOY)
        self.assertEqual(Asignacion.objects.count(), 1)
        self.assertEqual(asignacion.transportista.asignaciones.count(), 1)
        self.assertEqual(oferta.estado, EstadoOferta.CUBIERTA)

    def test_no_se_cancela_con_fecha_anterior_al_inicio(self):
        asignacion = crear_asignacion(
            transportista=crear_transportista(), oferta=crear_oferta(), fecha_inicio=HOY
        )

        respuesta = self.client.post(
            reverse("asignaciones:cancelar", args=[asignacion.pk]),
            {"fecha": (HOY - timedelta(days=2)).isoformat()},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "no puede ser anterior")
        asignacion.refresh_from_db()
        self.assertTrue(asignacion.esta_activa)

    def test_una_asignacion_cerrada_no_se_finaliza_ni_cancela_de_nuevo(self):
        asignacion = crear_asignacion(
            transportista=crear_transportista(), oferta=crear_oferta(), fecha_inicio=HOY
        )
        asignacion.finalizar(HOY)

        for nombre in ("asignaciones:finalizar", "asignaciones:cancelar"):
            with self.subTest(ruta=nombre):
                respuesta = self.client.get(reverse(nombre, args=[asignacion.pk]))
                self.assertEqual(respuesta.status_code, 302)
                self.assertEqual(
                    respuesta.url, reverse("asignaciones:detalle", args=[asignacion.pk])
                )

    def test_el_listado_muestra_los_conteos_por_estado(self):
        crear_asignacion(transportista=crear_transportista(), oferta=crear_oferta(), fecha_inicio=HOY)
        cancelada = crear_asignacion(
            transportista=crear_transportista(),
            oferta=crear_oferta(destino="Cusco"),
            fecha_inicio=HOY,
        )
        cancelada.cancelar(HOY)
        finalizada = crear_asignacion(
            transportista=crear_transportista(),
            oferta=crear_oferta(destino="Piura"),
            fecha_inicio=HOY,
        )
        finalizada.finalizar(HOY)

        respuesta = self.client.get(reverse("asignaciones:lista"))

        conteos = {fila["valor"]: fila["total"] for fila in respuesta.context["conteos"]}
        self.assertEqual(conteos[EstadoAsignacion.ACTIVA], 1)
        self.assertEqual(conteos[EstadoAsignacion.FINALIZADA], 1)
        self.assertEqual(conteos[EstadoAsignacion.CANCELADA], 1)
        self.assertContains(respuesta, "Cancelada")

    def test_listado_filtra_por_estado(self):
        empresa = crear_empresa_cliente()
        activa = crear_asignacion(
            transportista=crear_transportista(),
            oferta=crear_oferta(empresa=empresa),
            fecha_inicio=HOY,
        )
        finalizada = crear_asignacion(
            transportista=crear_transportista(),
            oferta=crear_oferta(empresa=empresa),
            fecha_inicio=HOY,
            fecha_fin=HOY,
        )
        finalizada.estado = EstadoAsignacion.FINALIZADA
        finalizada.save()

        respuesta = self.client.get(reverse("asignaciones:lista"), {"estado": EstadoAsignacion.FINALIZADA})

        self.assertEqual(list(respuesta.context["asignaciones"]), [finalizada])
        self.assertNotIn(activa, respuesta.context["asignaciones"])

    def test_el_detalle_muestra_las_advertencias_de_la_asignacion(self):
        asignacion = crear_asignacion(
            transportista=crear_transportista(), oferta=crear_oferta(), fecha_inicio=HOY
        )
        from transportistas.models import Advertencia

        Advertencia.objects.create(
            transportista=asignacion.transportista,
            asignacion=asignacion,
            descripcion="Demora injustificada en la entrega",
            fecha=HOY,
        )

        respuesta = self.client.get(reverse("asignaciones:detalle", args=[asignacion.pk]))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Demora injustificada")


class FormulariosAsignacionTests(TestCase):
    def test_el_formulario_no_ofrece_transportistas_de_baja(self):
        oferta = crear_oferta()
        activo = crear_transportista()
        de_baja = crear_transportista(estado=EstadoTransportista.BAJA)

        formulario = AsignacionForm(oferta=oferta)

        self.assertIn(activo, formulario.fields["transportista"].queryset)
        self.assertNotIn(de_baja, formulario.fields["transportista"].queryset)

    def test_el_formulario_explica_los_motivos_de_no_elegibilidad(self):
        oferta = crear_oferta()
        transportista = crear_transportista(estado=EstadoTransportista.EN_RESERVA)

        formulario = AsignacionForm(
            data={"transportista": transportista.pk, "fecha_inicio": HOY.isoformat()},
            oferta=oferta,
        )

        self.assertFalse(formulario.is_valid())
        self.assertIn("En Reserva", str(formulario.errors))

    def test_finalizar_exige_fecha_no_anterior_al_inicio(self):
        asignacion = crear_asignacion(
            transportista=crear_transportista(), oferta=crear_oferta(), fecha_inicio=HOY
        )
        formulario = FinalizarAsignacionForm(
            data={"fecha_fin": (HOY - timedelta(days=1)).isoformat()}, asignacion=asignacion
        )

        self.assertFalse(formulario.is_valid())
        self.assertIn("no puede ser anterior", str(formulario.errors))


class CicloDeVidaTests(PruebaAutenticada):
    """Transiciones válidas e inválidas del ciclo oferta → asignación → cierre."""

    def test_no_se_puede_finalizar_dos_veces_ni_por_post(self):
        asignacion = crear_asignacion(
            transportista=crear_transportista(), oferta=crear_oferta(), fecha_inicio=HOY
        )
        asignacion.finalizar(HOY)

        for metodo in ("get", "post"):
            with self.subTest(metodo=metodo):
                respuesta = getattr(self.client, metodo)(
                    reverse("asignaciones:finalizar", args=[asignacion.pk]),
                    {"fecha_fin": HOY.isoformat()},
                )
                self.assertEqual(respuesta.status_code, 302)
                self.assertEqual(
                    respuesta.url, reverse("asignaciones:detalle", args=[asignacion.pk])
                )
        asignacion.refresh_from_db()
        self.assertTrue(asignacion.esta_finalizada)

    def test_cancelar_exige_motivo_y_lo_conserva_en_el_historial(self):
        asignacion = crear_asignacion(
            transportista=crear_transportista(), oferta=crear_oferta(), fecha_inicio=HOY
        )

        sin_motivo = self.client.post(
            reverse("asignaciones:cancelar", args=[asignacion.pk]),
            {"fecha": HOY.isoformat(), "motivo": "  "},
        )
        self.assertEqual(sin_motivo.status_code, 200)
        self.assertIn("motivo", sin_motivo.context["form"].errors)
        asignacion.refresh_from_db()
        self.assertTrue(asignacion.esta_activa)

        con_motivo = self.client.post(
            reverse("asignaciones:cancelar", args=[asignacion.pk]),
            {"fecha": HOY.isoformat(), "motivo": "El cliente anuló la carga"},
        )
        self.assertEqual(con_motivo.status_code, 302)
        asignacion.refresh_from_db()
        self.assertTrue(asignacion.esta_cancelada)
        self.assertEqual(asignacion.motivo_cancelacion, "El cliente anuló la carga")

        detalle = self.client.get(reverse("asignaciones:detalle", args=[asignacion.pk]))
        self.assertContains(detalle, "El cliente anuló la carga")
        self.assertContains(detalle, "Última actualización")

    def test_cancelar_sin_permiso_no_cambia_nada(self):
        from django.contrib.auth.models import Group

        from comun.permisos import GRUPO_CONSULTA

        self.usuario.groups.set([Group.objects.get(name=GRUPO_CONSULTA)])
        asignacion = crear_asignacion(
            transportista=crear_transportista(), oferta=crear_oferta(), fecha_inicio=HOY
        )

        respuesta = self.client.post(
            reverse("asignaciones:cancelar", args=[asignacion.pk]),
            {"fecha": HOY.isoformat(), "motivo": "Intento sin permiso"},
        )

        self.assertEqual(respuesta.status_code, 403)
        asignacion.refresh_from_db()
        self.assertTrue(asignacion.esta_activa)

    def test_segunda_asignacion_sobre_la_misma_oferta_falla_sin_cambios_parciales(self):
        """Simula dos solicitudes que compiten por la misma oferta disponible."""
        oferta = crear_oferta()
        primera = crear_asignacion(
            transportista=crear_transportista(), oferta=oferta, fecha_inicio=HOY
        )

        with self.assertRaises(ValidationError):
            crear_asignacion(
                transportista=crear_transportista(), oferta=oferta, fecha_inicio=HOY
            )

        self.assertEqual(Asignacion.objects.count(), 1)
        self.assertEqual(Asignacion.objects.get().pk, primera.pk)
        oferta.refresh_from_db()
        self.assertEqual(oferta.estado, EstadoOferta.CUBIERTA)

    def test_transportista_con_asignacion_activa_no_recibe_otra(self):
        transportista = crear_transportista()
        crear_asignacion(
            transportista=transportista, oferta=crear_oferta(), fecha_inicio=HOY
        )

        with self.assertRaises(ValidationError):
            crear_asignacion(
                transportista=transportista,
                oferta=crear_oferta(destino="Cusco"),
                fecha_inicio=HOY,
            )

        self.assertEqual(transportista.asignaciones.count(), 1)

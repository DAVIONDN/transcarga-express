"""Pruebas de la baja diferida por excepción del cliente (baja pendiente).

Cubren los casos obligatorios: baja inmediata sin excepción, baja pendiente con
rechazo documentado, bloqueo de nuevas asignaciones, aplicación al terminar el
servicio, cuarta advertencia sin reactivación, procedimiento normal cuando el
cliente acepta, permisos y conservación del historial.
"""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from asignaciones.models import Asignacion
from asignaciones.reglas import crear_asignacion, es_elegible
from comun.choices import EstadoAsignacion, EstadoOferta, EstadoTransportista, TipoIncidencia
from comun.pruebas import (
    PruebaAutenticada,
    PruebaConsulta,
    crear_empresa_cliente,
    crear_oferta,
    crear_transportista,
)
from transportistas.models import Advertencia, Incidencia

HOY = timezone.localdate()


def crear_excepcion(transportista, asignacion, usuario=None):
    """Registra el rechazo documentado del reemplazo inmediato."""
    return Incidencia.objects.create(
        tipo=TipoIncidencia.EXCEPCION_BAJA,
        fecha=HOY,
        descripcion="El cliente rechaza el reemplazo inmediato hasta terminar el contrato",
        empresa_cliente=asignacion.oferta.empresa_cliente,
        transportista=transportista,
        asignacion=asignacion,
        registrado_por=usuario,
    )


def aplicar_advertencias(transportista, cantidad=3):
    for numero in range(cantidad):
        Advertencia.objects.create(
            transportista=transportista, descripcion=f"Motivo {numero}", fecha=HOY
        )
    transportista.refresh_from_db()
    return transportista


def escenario_pendiente(usuario=None, nombre="Baja pendiente"):
    """Transportista con servicio en curso, excepción y tres advertencias."""
    transportista = crear_transportista(nombre=nombre)
    asignacion = crear_asignacion(
        transportista=transportista, oferta=crear_oferta(), fecha_inicio=HOY
    )
    excepcion = crear_excepcion(transportista, asignacion, usuario)
    aplicar_advertencias(transportista, 3)
    asignacion.refresh_from_db()
    return transportista, asignacion, excepcion


class BajaDiferidaTests(PruebaAutenticada):
    def test_a_tercera_sin_excepcion_baja_inmediata(self):
        transportista = crear_transportista()
        aplicar_advertencias(transportista, 3)

        self.assertEqual(transportista.estado, EstadoTransportista.BAJA)

    def test_b_tercera_con_rechazo_baja_pendiente_y_servicio_intacto(self):
        transportista, asignacion, _ = escenario_pendiente(self.usuario)

        self.assertEqual(transportista.estado, EstadoTransportista.BAJA_PENDIENTE)
        self.assertEqual(asignacion.estado, EstadoAsignacion.ACTIVA)
        self.assertEqual(transportista.advertencias.count(), 3)

        ficha = self.client.get(reverse("transportistas:detalle", args=[transportista.pk]))
        self.assertContains(ficha, "Baja pendiente")
        self.assertContains(ficha, asignacion.oferta.codigo)

    def test_c_pendiente_no_recibe_nuevas_asignaciones(self):
        transportista, _, _ = escenario_pendiente(self.usuario)
        oferta = crear_oferta(destino="Cusco")

        self.assertFalse(es_elegible(transportista, oferta))

        respuesta = self.client.post(
            reverse("asignaciones:nueva"),
            {
                "oferta": oferta.pk,
                "transportista": transportista.pk,
                "fecha_inicio": HOY.isoformat(),
                "fecha_fin": "",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Baja pendiente")
        self.assertEqual(transportista.asignaciones.count(), 1)

        candidatos = self.client.get(reverse("ofertas:asignar", args=[oferta.pk]))
        self.assertContains(candidatos, "Baja pendiente")

    def test_d_al_terminar_aplica_la_baja_formal(self):
        transportista, asignacion, excepcion = escenario_pendiente(self.usuario)

        # Con el contrato en curso, la aplicación se rechaza sin cambios.
        confirmacion = self.client.get(
            reverse("transportistas:aplicar_baja", args=[transportista.pk])
        )
        self.assertEqual(confirmacion.status_code, 200)
        self.assertContains(confirmacion, "sigue en curso")

        rechazo = self.client.post(
            reverse("transportistas:aplicar_baja", args=[transportista.pk])
        )
        self.assertEqual(rechazo.status_code, 302)
        transportista.refresh_from_db()
        self.assertEqual(transportista.estado, EstadoTransportista.BAJA_PENDIENTE)

        # Terminado el servicio, la acción autorizada aplica la baja.
        asignacion.finalizar(HOY)
        aplicado = self.client.post(
            reverse("transportistas:aplicar_baja", args=[transportista.pk]), follow=True
        )

        transportista.refresh_from_db()
        excepcion.refresh_from_db()
        self.assertContains(aplicado, "Baja formal aplicada")
        self.assertEqual(transportista.estado, EstadoTransportista.BAJA)
        self.assertEqual(excepcion.estado_revision, "REVISADA")

        panel = self.client.get(reverse("panel:inicio"))
        self.assertNotContains(panel, "Bajas pendientes de aplicar")

    def test_e_cuarta_advertencia_no_reactiva(self):
        transportista, _, _ = escenario_pendiente(self.usuario)
        aplicar_advertencias(transportista, 1)

        self.assertEqual(transportista.estado, EstadoTransportista.BAJA_PENDIENTE)
        self.assertEqual(transportista.advertencias.count(), 4)

    def test_f_cliente_que_acepta_baja_normal_y_sustitucion(self):
        sustituido = crear_transportista(nombre="Baja normal")
        original = crear_asignacion(
            transportista=sustituido, oferta=crear_oferta(), fecha_inicio=HOY
        )
        aplicar_advertencias(sustituido, 3)
        self.assertEqual(sustituido.estado, EstadoTransportista.BAJA)

        original.cancelar(HOY, motivo="Baja del transportista; entra reemplazo")
        reemplazo = crear_transportista(nombre="Reemplazo aceptado")
        oferta_nueva = crear_oferta(destino="Cusco")
        self.assertTrue(es_elegible(reemplazo, oferta_nueva))
        nueva = crear_asignacion(
            transportista=reemplazo,
            oferta=oferta_nueva,
            fecha_inicio=HOY,
        )

        self.assertEqual(nueva.estado, EstadoAsignacion.ACTIVA)
        original.refresh_from_db()
        self.assertEqual(original.estado, EstadoAsignacion.CANCELADA)
        self.assertEqual(original.motivo_cancelacion, "Baja del transportista; entra reemplazo")

    def test_h_historial_conservado_tras_la_baja_diferida(self):
        transportista, asignacion, excepcion = escenario_pendiente(self.usuario)
        oferta = asignacion.oferta

        self.assertEqual(transportista.advertencias.count(), 3)
        self.assertEqual(transportista.asignaciones.count(), 1)
        oferta.refresh_from_db()
        self.assertEqual(oferta.estado, EstadoOferta.CUBIERTA)

        asignacion.finalizar(HOY)
        self.client.post(reverse("transportistas:aplicar_baja", args=[transportista.pk]))

        transportista.refresh_from_db()
        self.assertEqual(transportista.estado, EstadoTransportista.BAJA)
        self.assertEqual(transportista.advertencias.count(), 3)
        self.assertEqual(transportista.asignaciones.count(), 1)
        self.assertTrue(
            Incidencia.objects.filter(pk=excepcion.pk).exists()
        )

    def test_no_se_fija_baja_pendiente_manualmente_ni_se_reactiva(self):
        transportista, _, _ = escenario_pendiente(self.usuario)

        for estado in (EstadoTransportista.ACTIVO, EstadoTransportista.EN_RESERVA):
            with self.subTest(estado=estado):
                respuesta = self.client.post(
                    reverse("transportistas:cambiar_estado", args=[transportista.pk]),
                    {"estado": estado},
                )
                self.assertEqual(respuesta.status_code, 200)
                transportista.refresh_from_db()
                self.assertEqual(
                    transportista.estado, EstadoTransportista.BAJA_PENDIENTE
                )

        otro = crear_transportista(nombre="Intento manual")
        respuesta = self.client.post(
            reverse("transportistas:cambiar_estado", args=[otro.pk]),
            {"estado": EstadoTransportista.BAJA_PENDIENTE},
        )
        self.assertEqual(respuesta.status_code, 200)
        otro.refresh_from_db()
        self.assertEqual(otro.estado, EstadoTransportista.ACTIVO)

    def test_segunda_asignacion_para_pendiente_falla_sin_cambios_parciales(self):
        transportista, _, _ = escenario_pendiente(self.usuario)

        with self.assertRaises(ValidationError):
            crear_asignacion(
                transportista=transportista,
                oferta=crear_oferta(destino="Cusco"),
                fecha_inicio=HOY,
            )

        self.assertEqual(transportista.asignaciones.count(), 1)


class PermisosBajaDiferidaTests(PruebaConsulta):
    def test_g_sin_permiso_no_modifica_ni_aplica(self):
        transportista = crear_transportista(nombre="Pendiente ajeno")
        asignacion = crear_asignacion(
            transportista=transportista, oferta=crear_oferta(), fecha_inicio=HOY
        )
        crear_excepcion(transportista, asignacion)
        aplicar_advertencias(transportista, 3)
        self.assertEqual(transportista.estado, EstadoTransportista.BAJA_PENDIENTE)

        ruta = reverse("transportistas:aplicar_baja", args=[transportista.pk])
        self.assertEqual(self.client.get(ruta).status_code, 403)
        self.assertEqual(self.client.post(ruta).status_code, 403)

        transportista.refresh_from_db()
        self.assertEqual(transportista.estado, EstadoTransportista.BAJA_PENDIENTE)

    def test_g_consulta_si_ve_la_ficha_y_el_panel(self):
        transportista = crear_transportista(nombre="Pendiente visible")
        asignacion = crear_asignacion(
            transportista=transportista, oferta=crear_oferta(), fecha_inicio=HOY
        )
        crear_excepcion(transportista, asignacion)
        aplicar_advertencias(transportista, 3)

        ficha = self.client.get(reverse("transportistas:detalle", args=[transportista.pk]))
        self.assertContains(ficha, "Baja pendiente")
        self.assertNotContains(ficha, "Aplicar baja formal")

        panel = self.client.get(reverse("panel:inicio"))
        self.assertContains(panel, "Bajas pendientes de aplicar")

"""Pruebas del módulo de incidencias: quejas, advertencias, renuncia y reemplazos.

Comprueban que la queja no es una advertencia formal, la progresión 1-2-3 con
baja inmediata y conservación del historial, la cuarta advertencia sin
reactivación, la excepción registrada de forma explícita, la renuncia con y sin
asignación activa, el reemplazo válido e inválido, la manipulación directa de
estados y los permisos por rol.
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


class QuejaTests(PruebaAutenticada):
    """La queja recibida no es una advertencia formal."""

    def test_queja_sin_advertencia_formal(self):
        empresa = crear_empresa_cliente()
        transportista = crear_transportista()

        respuesta = self.client.post(
            reverse("transportistas:incidencias_crear"),
            {
                "tipo": TipoIncidencia.QUEJA,
                "fecha": HOY.isoformat(),
                "descripcion": "Entrega con retraso reportada por el cliente",
                "empresa_cliente": empresa.pk,
                "transportista": transportista.pk,
                "asignacion": "",
                "acuerdo_reemplazo": "",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        incidencia = Incidencia.objects.get()
        self.assertEqual(incidencia.estado_revision, "PENDIENTE")
        self.assertFalse(Advertencia.objects.exists())
        self.assertEqual(transportista.advertencias.count(), 0)

        ficha = self.client.get(reverse("transportistas:detalle", args=[transportista.pk]))
        self.assertContains(ficha, "Entrega con retraso reportada por el cliente")

        detalle = self.client.get(
            reverse("transportistas:incidencias_detalle", args=[incidencia.pk])
        )
        self.assertContains(detalle, "Sin advertencia formal")

    def test_queja_sin_cliente_se_rechaza(self):
        respuesta = self.client.post(
            reverse("transportistas:incidencias_crear"),
            {
                "tipo": TipoIncidencia.QUEJA,
                "fecha": HOY.isoformat(),
                "descripcion": "Queja sin cliente",
                "transportista": crear_transportista().pk,
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("empresa_cliente", respuesta.context["form"].errors)
        self.assertFalse(Incidencia.objects.exists())


class TresAdvertenciasTests(PruebaAutenticada):
    """Primera, segunda y tercera advertencia, con baja inmediata."""

    def _convertir(self, incidencia):
        confirmacion = self.client.get(
            reverse("transportistas:incidencias_convertir", args=[incidencia.pk])
        )
        self.assertEqual(confirmacion.status_code, 200)
        return self.client.post(
            reverse("transportistas:incidencias_convertir", args=[incidencia.pk]),
            {"token": confirmacion.context["token"]},
            follow=True,
        )

    def _queja(self, transportista, descripcion):
        return Incidencia.objects.create(
            tipo=TipoIncidencia.QUEJA,
            fecha=HOY,
            descripcion=descripcion,
            empresa_cliente=crear_empresa_cliente(),
            transportista=transportista,
            registrado_por=self.usuario,
        )

    def test_primera_segunda_y_tercera_con_baja_inmediata(self):
        transportista = crear_transportista(nombre="Acumula tres")
        asignacion = crear_asignacion(
            transportista=transportista, oferta=crear_oferta(), fecha_inicio=HOY
        )
        oferta = asignacion.oferta

        for numero in (1, 2):
            respuesta = self._convertir(self._queja(transportista, f"Motivo {numero}"))
            transportista.refresh_from_db()
            self.assertContains(respuesta, f"{numero} de 3")
            self.assertEqual(transportista.estado, EstadoTransportista.ACTIVO)

        respuesta = self._convertir(self._queja(transportista, "Motivo 3"))

        transportista.refresh_from_db()
        self.assertContains(respuesta, "pasó automáticamente")
        self.assertEqual(transportista.estado, EstadoTransportista.BAJA)
        self.assertEqual(transportista.advertencias.count(), 3)

        # Se conserva todo el historial previo.
        self.assertEqual(transportista.asignaciones.count(), 1)
        asignacion.refresh_from_db()
        self.assertEqual(asignacion.estado, EstadoAsignacion.ACTIVA)
        oferta.refresh_from_db()
        self.assertEqual(oferta.estado, EstadoOferta.CUBIERTA)

        # La baja impide nuevas asignaciones.
        with self.assertRaises(ValidationError):
            crear_asignacion(
                transportista=transportista,
                oferta=crear_oferta(destino="Cusco"),
                fecha_inicio=HOY,
            )
        self.assertFalse(es_elegible(transportista, crear_oferta(destino="Piura")))

    def test_cuarta_advertencia_no_reactiva_ni_cambia_nada(self):
        transportista = crear_transportista(nombre="Ya de baja")
        for numero in range(3):
            self._convertir(self._queja(transportista, f"Motivo {numero}"))
        transportista.refresh_from_db()
        self.assertEqual(transportista.estado, EstadoTransportista.BAJA)

        self._convertir(self._queja(transportista, "Motivo 4"))

        transportista.refresh_from_db()
        self.assertEqual(transportista.estado, EstadoTransportista.BAJA)
        self.assertEqual(transportista.advertencias.count(), 4)

    def test_convertir_dos_veces_no_duplica_la_advertencia(self):
        incidencia = self._queja(crear_transportista(), "Motivo único")
        self._convertir(incidencia)

        confirmacion = self.client.get(
            reverse("transportistas:incidencias_convertir", args=[incidencia.pk])
        )
        self.assertEqual(confirmacion.status_code, 302)

        self.assertEqual(Advertencia.objects.count(), 1)


class ExcepcionClienteTests(PruebaAutenticada):
    """La excepción queda registrada de forma explícita."""

    def test_excepcion_registra_decision_fecha_responsable_y_asignacion(self):
        transportista = crear_transportista(nombre="Con contrato en curso")
        asignacion = crear_asignacion(
            transportista=transportista, oferta=crear_oferta(), fecha_inicio=HOY
        )

        respuesta = self.client.post(
            reverse("transportistas:incidencias_crear"),
            {
                "tipo": TipoIncidencia.EXCEPCION_BAJA,
                "fecha": HOY.isoformat(),
                "descripcion": "El cliente rechaza el reemplazo inmediato hasta terminar el contrato",
                "transportista": transportista.pk,
                "asignacion": asignacion.pk,
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        incidencia = Incidencia.objects.get()
        self.assertEqual(incidencia.transportista, transportista)
        self.assertEqual(incidencia.asignacion, asignacion)
        self.assertEqual(incidencia.registrado_por, self.usuario)
        self.assertEqual(incidencia.fecha, HOY)

        detalle = self.client.get(
            reverse("transportistas:incidencias_detalle", args=[incidencia.pk])
        )
        self.assertContains(detalle, "rechaza el reemplazo inmediato")
        self.assertContains(detalle, "pendiente de confirmación")

    def test_excepcion_sin_asignacion_afectada_se_rechaza(self):
        respuesta = self.client.post(
            reverse("transportistas:incidencias_crear"),
            {
                "tipo": TipoIncidencia.EXCEPCION_BAJA,
                "fecha": HOY.isoformat(),
                "descripcion": "Excepción sin contrato",
                "transportista": crear_transportista().pk,
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("asignacion", respuesta.context["form"].errors)


class RenunciaTests(PruebaAutenticada):
    """La renuncia se registra sin cambiar estados por sí sola."""

    def test_renuncia_con_asignacion_activa_y_acuerdo(self):
        transportista = crear_transportista(nombre="Renuncia con servicio")
        asignacion = crear_asignacion(
            transportista=transportista, oferta=crear_oferta(), fecha_inicio=HOY
        )

        respuesta = self.client.post(
            reverse("transportistas:incidencias_crear"),
            {
                "tipo": TipoIncidencia.RENUNCIA,
                "fecha": HOY.isoformat(),
                "descripcion": "Renuncia voluntaria por motivos personales",
                "transportista": transportista.pk,
                "asignacion": asignacion.pk,
                "acuerdo_reemplazo": "Se acuerda buscar reemplazo esta semana",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        incidencia = Incidencia.objects.get()
        self.assertEqual(
            incidencia.acuerdo_reemplazo, "Se acuerda buscar reemplazo esta semana"
        )

        # La solicitud no es la finalización: todo sigue igual.
        transportista.refresh_from_db()
        asignacion.refresh_from_db()
        self.assertEqual(transportista.estado, EstadoTransportista.ACTIVO)
        self.assertEqual(asignacion.estado, EstadoAsignacion.ACTIVA)

    def test_renuncia_sin_asignacion_activa(self):
        transportista = crear_transportista(nombre="Renuncia sin servicio")

        respuesta = self.client.post(
            reverse("transportistas:incidencias_crear"),
            {
                "tipo": TipoIncidencia.RENUNCIA,
                "fecha": HOY.isoformat(),
                "descripcion": "Renuncia voluntaria",
                "transportista": transportista.pk,
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Incidencia.objects.count(), 1)


class ReemplazoTests(PruebaAutenticada):
    """El reemplazo se vincula sobre una oferta independiente y verificada."""

    def _escenario(self):
        sustituido = crear_transportista(nombre="Sustituido")
        original = crear_asignacion(
            transportista=sustituido, oferta=crear_oferta(), fecha_inicio=HOY
        )
        original.cancelar(HOY, motivo="Renuncia del transportista")
        reemplazo = crear_transportista(nombre="Reemplazo válido")
        nueva = crear_asignacion(
            transportista=reemplazo,
            oferta=crear_oferta(destino="Cusco"),
            fecha_inicio=HOY,
        )
        incidencia = Incidencia.objects.create(
            tipo=TipoIncidencia.RENUNCIA,
            fecha=HOY,
            descripcion="Renuncia con acuerdo",
            transportista=sustituido,
            asignacion=original,
            registrado_por=self.usuario,
        )
        return sustituido, original, reemplazo, nueva, incidencia

    def test_reemplazo_valido_conserva_la_asignacion_original(self):
        sustituido, original, reemplazo, nueva, incidencia = self._escenario()

        respuesta = self.client.post(
            reverse("transportistas:incidencias_vincular", args=[incidencia.pk]),
            {"nueva_asignacion": nueva.pk},
        )

        self.assertEqual(respuesta.status_code, 302)
        incidencia.refresh_from_db()
        self.assertEqual(incidencia.nueva_asignacion, nueva)
        self.assertEqual(incidencia.transportista_reemplazo, reemplazo)

        detalle = self.client.get(
            reverse("transportistas:incidencias_detalle", args=[incidencia.pk])
        )
        self.assertContains(detalle, "Reemplazo vinculado")
        self.assertContains(detalle, nueva.oferta.codigo)

        original.refresh_from_db()
        self.assertEqual(original.transportista, sustituido)
        self.assertEqual(original.estado, EstadoAsignacion.CANCELADA)

    def test_no_vincula_al_mismo_transportista(self):
        sustituido, original, _, _, incidencia = self._escenario()
        propia = crear_asignacion(
            transportista=sustituido,
            oferta=crear_oferta(destino="Piura"),
            fecha_inicio=HOY,
        )

        respuesta = self.client.post(
            reverse("transportistas:incidencias_vincular", args=[incidencia.pk]),
            {"nueva_asignacion": propia.pk},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "otro transportista")
        incidencia.refresh_from_db()
        self.assertIsNone(incidencia.nueva_asignacion)

    def test_no_vincula_un_reemplazo_que_perdio_vigencia(self):
        _, _, _, nueva, incidencia = self._escenario()
        reemplazo = nueva.transportista
        reemplazo.fecha_vencimiento_soat = HOY - timedelta(days=1)
        reemplazo.save(update_fields=["fecha_vencimiento_soat", "actualizado"])

        respuesta = self.client.post(
            reverse("transportistas:incidencias_vincular", args=[incidencia.pk]),
            {"nueva_asignacion": nueva.pk},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "no es válido")
        incidencia.refresh_from_db()
        self.assertIsNone(incidencia.nueva_asignacion)

    def test_no_vincula_sin_asignacion_original(self):
        incidencia = Incidencia.objects.create(
            tipo=TipoIncidencia.RENUNCIA,
            fecha=HOY,
            descripcion="Sin asignación",
            transportista=crear_transportista(),
            registrado_por=self.usuario,
        )
        nueva = crear_asignacion(
            transportista=crear_transportista(),
            oferta=crear_oferta(),
            fecha_inicio=HOY,
        )

        respuesta = self.client.post(
            reverse("transportistas:incidencias_vincular", args=[incidencia.pk]),
            {"nueva_asignacion": nueva.pk},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "asignación original")


class PermisosIncidenciasTests(PruebaConsulta):
    """Consulta lee; operar exige permiso de advertencias."""

    def test_consulta_lee_pero_no_opera(self):
        incidencia = Incidencia.objects.create(
            tipo=TipoIncidencia.QUEJA,
            fecha=HOY,
            descripcion="Queja visible",
            empresa_cliente=crear_empresa_cliente(),
            transportista=crear_transportista(),
        )

        self.assertEqual(
            self.client.get(reverse("transportistas:incidencias")).status_code, 200
        )
        self.assertEqual(
            self.client.get(
                reverse("transportistas:incidencias_detalle", args=[incidencia.pk])
            ).status_code,
            200,
        )
        for nombre in (
            "transportistas:incidencias_crear",
            "transportistas:incidencias_revisar",
            "transportistas:incidencias_convertir",
            "transportistas:incidencias_vincular",
        ):
            with self.subTest(ruta=nombre):
                args = () if nombre == "transportistas:incidencias_crear" else (incidencia.pk,)
                self.assertEqual(
                    self.client.get(reverse(nombre, args=args)).status_code, 403
                )
                self.assertEqual(
                    self.client.post(reverse(nombre, args=args), {}).status_code, 403
                )


class ManipulacionDeEstadosTests(PruebaAutenticada):
    """Los estados no se manipulan por vías directas."""

    def test_baja_no_se_reactiva_desde_la_pantalla_de_estado(self):
        transportista = crear_transportista(nombre="De baja con tres")
        for numero in range(3):
            Advertencia.objects.create(
                transportista=transportista, descripcion=f"Motivo {numero}", fecha=HOY
            )
        transportista.refresh_from_db()
        self.assertEqual(transportista.estado, EstadoTransportista.BAJA)

        respuesta = self.client.post(
            reverse("transportistas:cambiar_estado", args=[transportista.pk]),
            {"estado": EstadoTransportista.ACTIVO},
        )

        self.assertEqual(respuesta.status_code, 200)
        transportista.refresh_from_db()
        self.assertEqual(transportista.estado, EstadoTransportista.BAJA)

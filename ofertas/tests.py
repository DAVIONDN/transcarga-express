"""Pruebas de ofertas de carga."""

from decimal import Decimal

from django.db.utils import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from asignaciones.reglas import crear_asignacion
from clientes.models import EmpresaCliente
from comun.choices import EstadoOferta, NivelCarga, TipoVehiculo
from comun.pruebas import PruebaAutenticada, crear_empresa_cliente, crear_oferta, crear_transportista
from ofertas.forms import OfertaCargaForm
from ofertas.models import OfertaCarga


class CodigoDeOfertaTests(TestCase):
    def test_codigo_autogenerado_consecutivo(self):
        # T-29
        empresa = crear_empresa_cliente()
        primera = crear_oferta(empresa=empresa)
        segunda = crear_oferta(empresa=empresa)

        self.assertEqual(primera.codigo, "OF-00001")
        self.assertEqual(segunda.codigo, "OF-00002")

    def test_el_codigo_es_unico(self):
        empresa = crear_empresa_cliente()
        crear_oferta(empresa=empresa)
        with self.assertRaises(IntegrityError):
            OfertaCarga.objects.create(
                codigo="OF-00001",
                empresa_cliente=empresa,
                origen="Lima",
                destino="Piura",
                tipo_vehiculo_requerido=TipoVehiculo.CAMION,
                nivel_requerido=NivelCarga.NIVEL_2,
                remuneracion=Decimal("1000.00"),
            )


class OfertaCargaTests(PruebaAutenticada):
    def test_remuneracion_mayor_que_cero(self):
        formulario = OfertaCargaForm(
            data={
                "empresa_cliente": crear_empresa_cliente().pk,
                "origen": "Lima",
                "destino": "Ica",
                "tipo_vehiculo_requerido": TipoVehiculo.CAMION,
                "nivel_requerido": NivelCarga.NIVEL_2,
                "remuneracion": "0",
                "estado": EstadoOferta.DISPONIBLE,
            }
        )

        self.assertFalse(formulario.is_valid())
        self.assertIn("remuneracion", formulario.errors)

    def test_alta_desde_la_pantalla(self):
        empresa = crear_empresa_cliente()
        respuesta = self.client.post(
            reverse("ofertas:crear"),
            {
                "empresa_cliente": empresa.pk,
                "origen": "Lima",
                "destino": "Piura",
                "tipo_vehiculo_requerido": TipoVehiculo.CAMION,
                "nivel_requerido": NivelCarga.NIVEL_2,
                "remuneracion": "1800.50",
                "estado": EstadoOferta.DISPONIBLE,
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        oferta = OfertaCarga.objects.get()
        self.assertEqual(oferta.codigo, "OF-00001")
        self.assertEqual(oferta.estado, EstadoOferta.DISPONIBLE)

    def test_una_oferta_con_asignacion_no_vuelve_a_disponible(self):
        oferta = crear_oferta()
        transportista = crear_transportista()
        crear_asignacion(
            transportista=transportista, oferta=oferta, fecha_inicio=timezone.localdate()
        )

        respuesta = self.client.post(
            reverse("ofertas:cambiar_estado", args=[oferta.pk]),
            {"estado": EstadoOferta.DISPONIBLE},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "no puede volver a «Disponible»")
        oferta.refresh_from_db()
        self.assertEqual(oferta.estado, EstadoOferta.CUBIERTA)

    def test_listado_filtra_por_nivel_y_estado(self):
        empresa = crear_empresa_cliente()
        crear_oferta(empresa=empresa, nivel_requerido=NivelCarga.NIVEL_2)
        crear_oferta(empresa=empresa, nivel_requerido=NivelCarga.NIVEL_3)

        respuesta = self.client.get(reverse("ofertas:lista"), {"nivel": "3"})

        self.assertEqual(len(respuesta.context["ofertas"]), 1)
        self.assertEqual(respuesta.context["ofertas"][0].nivel_requerido, NivelCarga.NIVEL_3)

    def test_el_detalle_muestra_los_candidatos_evaluados(self):
        oferta = crear_oferta()
        crear_transportista()
        crear_transportista(capacidad_toneladas=Decimal("3.00"))

        respuesta = self.client.get(reverse("ofertas:detalle", args=[oferta.pk]))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.context["candidatos"]), 2)
        self.assertEqual(len(respuesta.context["elegibles"]), 1)


class ModuloOfertasTests(PruebaAutenticada):
    """Ciclo del módulo de ofertas: creación, edición, filtros, importes y reglas."""

    def datos_oferta(self, oferta, **cambios):
        datos = {
            "empresa_cliente": oferta.empresa_cliente_id,
            "origen": oferta.origen,
            "destino": oferta.destino,
            "tipo_vehiculo_requerido": oferta.tipo_vehiculo_requerido,
            "nivel_requerido": oferta.nivel_requerido,
            "remuneracion": str(oferta.remuneracion),
        }
        datos.update(cambios)
        return datos

    def test_edicion_de_una_oferta_disponible(self):
        oferta = crear_oferta()

        respuesta = self.client.post(
            reverse("ofertas:editar", args=[oferta.pk]),
            self.datos_oferta(oferta, destino="Trujillo", remuneracion="1999.90"),
        )

        self.assertEqual(respuesta.status_code, 302)
        oferta.refresh_from_db()
        self.assertEqual(oferta.destino, "Trujillo")
        self.assertEqual(oferta.remuneracion, Decimal("1999.90"))
        self.assertEqual(oferta.estado, EstadoOferta.DISPONIBLE)  # el estado no se toca aquí

    def test_la_relacion_con_una_empresa_es_obligatoria(self):
        respuesta = self.client.post(
            reverse("ofertas:crear"),
            {
                "empresa_cliente": "",
                "origen": "Lima",
                "destino": "Piura",
                "tipo_vehiculo_requerido": TipoVehiculo.CAMION,
                "nivel_requerido": NivelCarga.NIVEL_2,
                "remuneracion": "1500.00",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("empresa_cliente", respuesta.context["form"].errors)
        self.assertFalse(OfertaCarga.objects.exists())

    def test_importe_negativo_es_rechazado(self):
        empresa = crear_empresa_cliente()

        respuesta = self.client.post(
            reverse("ofertas:crear"),
            {
                "empresa_cliente": empresa.pk,
                "origen": "Lima",
                "destino": "Piura",
                "tipo_vehiculo_requerido": TipoVehiculo.CAMION,
                "nivel_requerido": NivelCarga.NIVEL_2,
                "remuneracion": "-100.00",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("remuneracion", respuesta.context["form"].errors)
        self.assertFalse(OfertaCarga.objects.exists())

    def test_importe_con_letras_es_rechazado(self):
        empresa = crear_empresa_cliente()

        respuesta = self.client.post(
            reverse("ofertas:crear"),
            {
                "empresa_cliente": empresa.pk,
                "origen": "Lima",
                "destino": "Piura",
                "tipo_vehiculo_requerido": TipoVehiculo.CAMION,
                "nivel_requerido": NivelCarga.NIVEL_2,
                "remuneracion": "mil soles",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("remuneracion", respuesta.context["form"].errors)

    def test_no_se_puede_cambiar_el_nivel_de_una_oferta_asignada(self):
        oferta = crear_oferta(nivel_requerido=NivelCarga.NIVEL_2)
        crear_asignacion(
            transportista=crear_transportista(), oferta=oferta, fecha_inicio=timezone.localdate()
        )

        respuesta = self.client.post(
            reverse("ofertas:editar", args=[oferta.pk]),
            self.datos_oferta(oferta, nivel_requerido=NivelCarga.NIVEL_3),
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "invalidaría la asignación existente")
        self.assertIn("nivel_requerido", respuesta.context["form"].errors)
        oferta.refresh_from_db()
        self.assertEqual(oferta.nivel_requerido, NivelCarga.NIVEL_2)

    def test_no_se_puede_cambiar_el_vehiculo_de_una_oferta_asignada(self):
        oferta = crear_oferta(tipo_vehiculo_requerido=TipoVehiculo.CAMION)
        crear_asignacion(
            transportista=crear_transportista(), oferta=oferta, fecha_inicio=timezone.localdate()
        )

        respuesta = self.client.post(
            reverse("ofertas:editar", args=[oferta.pk]),
            self.datos_oferta(oferta, tipo_vehiculo_requerido=TipoVehiculo.CISTERNA),
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("tipo_vehiculo_requerido", respuesta.context["form"].errors)

    def test_con_asignacion_si_se_ajustan_origen_destino_y_remuneracion(self):
        oferta = crear_oferta()
        crear_asignacion(
            transportista=crear_transportista(), oferta=oferta, fecha_inicio=timezone.localdate()
        )

        respuesta = self.client.post(
            reverse("ofertas:editar", args=[oferta.pk]),
            self.datos_oferta(oferta, destino="Cusco", remuneracion="2600.00"),
        )

        self.assertEqual(respuesta.status_code, 302)
        oferta.refresh_from_db()
        self.assertEqual(oferta.destino, "Cusco")
        self.assertEqual(oferta.remuneracion, Decimal("2600.00"))

    def test_cambio_de_estado_confirmado(self):
        oferta = crear_oferta()

        confirmacion = self.client.get(reverse("ofertas:cambiar_estado", args=[oferta.pk]))
        self.assertEqual(confirmacion.status_code, 200)
        self.assertContains(confirmacion, "Confirmar cambio de estado")

        respuesta = self.client.post(
            reverse("ofertas:cambiar_estado", args=[oferta.pk]),
            {"estado": EstadoOferta.CUBIERTA},
        )
        self.assertEqual(respuesta.status_code, 302)
        oferta.refresh_from_db()
        self.assertEqual(oferta.estado, EstadoOferta.CUBIERTA)

        vuelta = self.client.post(
            reverse("ofertas:cambiar_estado", args=[oferta.pk]),
            {"estado": EstadoOferta.DISPONIBLE},
        )
        self.assertEqual(vuelta.status_code, 302)
        oferta.refresh_from_db()
        self.assertEqual(oferta.estado, EstadoOferta.DISPONIBLE)

    def test_no_se_permite_elegir_el_mismo_estado(self):
        oferta = crear_oferta()

        respuesta = self.client.post(
            reverse("ofertas:cambiar_estado", args=[oferta.pk]),
            {"estado": EstadoOferta.DISPONIBLE},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "ya se encuentra en estado")

    def test_el_listado_filtra_por_empresa_cliente(self):
        primera = crear_empresa_cliente(razon_social="Primera S.A.C.")
        segunda = crear_empresa_cliente(razon_social="Segunda S.A.C.")
        propia = crear_oferta(empresa=primera, destino="Trujillo")
        crear_oferta(empresa=segunda, destino="Cusco")

        respuesta = self.client.get(reverse("ofertas:lista"), {"empresa": primera.pk})

        self.assertEqual(list(respuesta.context["ofertas"]), [propia])

    def test_el_listado_filtra_por_estado(self):
        disponible = crear_oferta()
        cubierta = crear_oferta(destino="Cusco")
        crear_asignacion(
            transportista=crear_transportista(), oferta=cubierta, fecha_inicio=timezone.localdate()
        )

        respuesta = self.client.get(reverse("ofertas:lista"), {"estado": EstadoOferta.CUBIERTA})

        self.assertEqual(list(respuesta.context["ofertas"]), [cubierta])
        self.assertNotIn(disponible, respuesta.context["ofertas"])

    def test_busqueda_por_codigo_origen_y_destino(self):
        buscada = crear_oferta(origen="Lima", destino="Arequipa")
        crear_oferta(origen="Ica", destino="Piura")

        por_codigo = self.client.get(reverse("ofertas:lista"), {"q": buscada.codigo})
        self.assertEqual(list(por_codigo.context["ofertas"]), [buscada])

        por_origen = self.client.get(reverse("ofertas:lista"), {"q": "Ica"})
        self.assertEqual(len(por_origen.context["ofertas"]), 1)

        por_destino = self.client.get(reverse("ofertas:lista"), {"q": "Arequipa"})
        self.assertEqual(list(por_destino.context["ofertas"]), [buscada])

    def test_el_listado_distingue_disponible_de_cubierta(self):
        crear_oferta()
        cubierta = crear_oferta(destino="Cusco")
        crear_asignacion(
            transportista=crear_transportista(), oferta=cubierta, fecha_inicio=timezone.localdate()
        )

        respuesta = self.client.get(reverse("ofertas:lista"))

        self.assertContains(respuesta, "Disponible")
        self.assertContains(respuesta, "Cubierta")

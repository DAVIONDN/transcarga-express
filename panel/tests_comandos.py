"""Pruebas del comando de datos ficticios de demostración.

Comprueba lo que la auditoría exige al comando: que sea idempotente, que no cree
usuarios con contraseña, que no borre nada de lo que ya existía y que deje un
conjunto de datos que cubra todos los casos del MVP (niveles, estados,
documentación vigente/por vencer/vencida y asignaciones en los tres estados),
más los módulos de capacitación, incidencias, formatos y liquidaciones.
"""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from asignaciones.models import Asignacion
from asignaciones.reglas import es_elegible
from auditoria.models import RegistroAuditoria
from capacitacion.models import Curso, Participacion
from clientes.models import EmpresaCliente
from comun import fechas
from comun.choices import (
    EstadoAsignacion,
    EstadoOferta,
    EstadoParticipacion,
    EstadoTransportista,
    NivelCarga,
    TipoDocumento,
    TipoIncidencia,
    TipoVehiculo,
)
from comun.pruebas import crear_empresa_cliente, crear_transportista
from liquidaciones.models import EstadoFormato, EstadoLiquidacion, FormatoSemanal, Liquidacion
from ofertas.models import OfertaCarga
from transportistas.models import (
    MAXIMO_ADVERTENCIAS,
    Advertencia,
    Incidencia,
    Transportista,
)

HOY = timezone.localdate()


class DatosDemoTests(TestCase):
    def ejecutar(self):
        salida = StringIO()
        call_command("cargar_datos_demo", stdout=salida)
        return salida.getvalue()

    def conteos(self):
        return {
            "empresas": EmpresaCliente.objects.count(),
            "transportistas": Transportista.objects.count(),
            "ofertas": OfertaCarga.objects.count(),
            "asignaciones": Asignacion.objects.count(),
            "advertencias": Advertencia.objects.count(),
        }

    def test_carga_el_estado_de_demostracion_esperado(self):
        self.ejecutar()

        self.assertEqual(
            self.conteos(),
            {
                "empresas": 6,
                "transportistas": 17,
                "ofertas": 18,
                "asignaciones": 7,
                "advertencias": 10,
            },
        )

    def test_es_idempotente(self):
        self.ejecutar()
        primera = self.conteos()

        salida = self.ejecutar()

        self.assertEqual(self.conteos(), primera)
        self.assertIn("0 nuevo(s)", salida)

    def test_no_borra_ni_modifica_registros_existentes(self):
        propio = crear_transportista(nombre="Registro propio del operador")
        cliente_propio = crear_empresa_cliente(razon_social="Empresa propia del operador")

        self.ejecutar()
        self.ejecutar()

        self.assertTrue(Transportista.objects.filter(pk=propio.pk).exists())
        self.assertTrue(EmpresaCliente.objects.filter(pk=cliente_propio.pk).exists())
        propio.refresh_from_db()
        cliente_propio.refresh_from_db()
        self.assertEqual(propio.nombre, "Registro propio del operador")
        self.assertEqual(cliente_propio.razon_social, "Empresa propia del operador")

    def test_no_crea_usuarios_ni_contrasenas(self):
        self.ejecutar()

        self.assertFalse(get_user_model().objects.exists())

    # ------------------------------------------------------- cobertura de casos
    def test_el_conjunto_cubre_los_tres_niveles_y_los_tres_estados(self):
        self.ejecutar()

        for nivel in NivelCarga:
            with self.subTest(nivel=nivel):
                self.assertTrue(Transportista.objects.filter(nivel=nivel.value).exists())
        # El conjunto demo cubre los tres estados base; «Baja pendiente» solo
        # nace del flujo real (tercera advertencia con excepción del cliente).
        for estado in (
            EstadoTransportista.ACTIVO,
            EstadoTransportista.EN_RESERVA,
            EstadoTransportista.BAJA,
        ):
            with self.subTest(estado=estado):
                self.assertTrue(Transportista.objects.filter(estado=estado.value).exists())

        self.assertEqual(
            Transportista.objects.filter(estado=EstadoTransportista.BAJA).count(), 3
        )
        self.assertEqual(
            Transportista.objects.filter(estado=EstadoTransportista.EN_RESERVA).count(), 2
        )

    def test_el_conjunto_cubre_todos_los_tipos_de_vehiculo(self):
        self.ejecutar()

        for tipo in TipoVehiculo:
            with self.subTest(tipo=tipo):
                self.assertTrue(Transportista.objects.filter(tipo_vehiculo=tipo.value).exists())
                self.assertTrue(
                    OfertaCarga.objects.filter(tipo_vehiculo_requerido=tipo.value).exists()
                )

    def test_el_conjunto_incluye_documentacion_vencida_y_por_vencer(self):
        self.ejecutar()

        vencidos = [
            t
            for t in Transportista.objects.all()
            if not (t.licencia_vigente and t.revision_tecnica_vigente and t.soat_vigente)
        ]
        self.assertGreaterEqual(len(vencidos), 2)

        por_vencer = [
            (t, etiqueta, fecha)
            for t in Transportista.objects.all()
            for etiqueta, fecha in t.documentos_por_vencer()
        ]
        self.assertGreater(len(por_vencer), 5)
        for _, _, fecha in por_vencer:
            with self.subTest(fecha=fecha):
                self.assertLessEqual(fecha, fechas.hoy() + timezone.timedelta(days=30))

    def test_el_conjunto_cubre_todos_los_estados_de_asignacion(self):
        self.ejecutar()

        for estado in EstadoAsignacion:
            with self.subTest(estado=estado):
                self.assertTrue(Asignacion.objects.filter(estado=estado.value).exists())

        # Toda asignación deja su oferta cubierta y conserva el historial
        for asignacion in Asignacion.objects.all():
            with self.subTest(asignacion=asignacion.pk):
                self.assertEqual(asignacion.oferta.estado, EstadoOferta.CUBIERTA)

    def test_las_advertencias_dejan_dos_transportistas_de_baja_por_limite(self):
        self.ejecutar()

        con_tres = [
            t
            for t in Transportista.objects.all()
            if t.advertencias_total >= MAXIMO_ADVERTENCIAS
        ]
        self.assertEqual(len(con_tres), 2)
        for transportista in con_tres:
            with self.subTest(transportista=transportista.pk):
                self.assertEqual(transportista.estado, EstadoTransportista.BAJA)

        # Un transportista con dos advertencias sigue habilitado (caso del recorrido)
        self.assertTrue(
            Transportista.objects.filter(
                estado=EstadoTransportista.ACTIVO, advertencias__isnull=False
            ).exists()
        )

    def test_hay_ofertas_disponibles_y_transportistas_elegibles(self):
        """El conjunto permite hacer el recorrido de demostración completo."""
        self.ejecutar()

        self.assertEqual(
            OfertaCarga.objects.filter(estado=EstadoOferta.DISPONIBLE).count(), 11
        )
        self.assertEqual(OfertaCarga.objects.filter(estado=EstadoOferta.CUBIERTA).count(), 7)

        oferta_nivel_1 = OfertaCarga.objects.filter(
            estado=EstadoOferta.DISPONIBLE,
            nivel_requerido=NivelCarga.NIVEL_1,
            tipo_vehiculo_requerido=TipoVehiculo.CISTERNA,
        ).first()
        self.assertIsNotNone(oferta_nivel_1)
        elegibles = [
            t
            for t in Transportista.objects.filter(
                estado=EstadoTransportista.ACTIVO,
                nivel=oferta_nivel_1.nivel_requerido,
                tipo_vehiculo=oferta_nivel_1.tipo_vehiculo_requerido,
                certificacion_carga_peligrosa=True,
            )
            if not t.tiene_asignacion_activa and t.soat_vigente
        ]
        self.assertTrue(elegibles, "debe existir al menos un transportista elegible")

    def test_el_recorrido_documentado_tiene_los_candidatos_esperados(self):
        """Protege el recorrido de cinco minutos del README."""
        self.ejecutar()

        oferta_1 = OfertaCarga.objects.get(codigo="OF-00001")
        oferta_5 = OfertaCarga.objects.get(codigo="OF-00005")
        carlos = Transportista.objects.get(numero_documento="40123456")
        ana = Transportista.objects.get(numero_documento="45678901")
        jorge = Transportista.objects.get(numero_documento="46789012")

        # OF-00005 (Nivel 1, tráiler) puede asignarse a Carlos Mendoza
        self.assertTrue(es_elegible(carlos, oferta_5))
        # Ana Lucía puede cubrir OF-00001 mientras no acumule la tercera advertencia
        self.assertTrue(es_elegible(ana, oferta_1))
        self.assertEqual(ana.advertencias_total, 2)
        # Jorge ya está de baja por advertencias y no es elegible para nada
        self.assertEqual(jorge.advertencias_total, 3)
        self.assertEqual(jorge.estado, EstadoTransportista.BAJA)
        self.assertFalse(es_elegible(jorge, oferta_1))

    def test_la_asignacion_de_demostracion_cubre_su_oferta(self):
        self.ejecutar()

        asignacion = Asignacion.objects.filter(oferta__codigo="OF-00006").get()

        self.assertEqual(asignacion.oferta.estado, EstadoOferta.CUBIERTA)
        self.assertEqual(asignacion.transportista.estado, EstadoTransportista.ACTIVO)
        self.assertEqual(asignacion.estado, EstadoAsignacion.ACTIVA)

    def test_una_asignacion_cancelada_no_libera_la_oferta(self):
        self.ejecutar()

        cancelada = Asignacion.objects.filter(estado=EstadoAsignacion.CANCELADA).get()

        self.assertEqual(cancelada.oferta.estado, EstadoOferta.CUBIERTA)
        self.assertEqual(cancelada.oferta.asignacion.pk, cancelada.pk)

    def test_no_hay_dos_asignaciones_activas_para_el_mismo_transportista(self):
        self.ejecutar()

        activas = Asignacion.objects.filter(estado=EstadoAsignacion.ACTIVA)
        transportistas = list(activas.values_list("transportista_id", flat=True))

        self.assertEqual(len(transportistas), len(set(transportistas)))

    def test_los_identificadores_de_demostracion_tienen_el_formato_esperado(self):
        """Los documentos de demostración son marcadores válidos del formato peruano."""
        self.ejecutar()

        for transportista in Transportista.objects.all():
            with self.subTest(transportista=transportista.pk):
                esperado = 8 if transportista.tipo_documento == TipoDocumento.DNI else 11
                self.assertRegex(transportista.numero_documento, rf"^\d{{{esperado}}}$")
        for empresa in EmpresaCliente.objects.all():
            with self.subTest(empresa=empresa.pk):
                self.assertRegex(empresa.ruc, r"^\d{11}$")
                self.assertTrue(empresa.razon_social.endswith(("S.A.C.", "S.R.L.", "S.A.")))

    def test_las_fotografias_de_los_vehiculos_se_guardan(self):
        self.ejecutar()

        for transportista in Transportista.objects.all():
            with self.subTest(transportista=transportista.pk):
                self.assertTrue(transportista.fotografia_vehiculo)
                self.assertTrue(transportista.fotografia_vehiculo.name.endswith(".png"))

    def test_el_comando_avisa_que_hay_que_crear_un_usuario(self):
        salida = self.ejecutar()

        self.assertIn("createsuperuser", salida)

    def test_el_comando_informa_las_bajas_por_advertencias(self):
        salida = self.ejecutar()

        self.assertIn(f"{MAXIMO_ADVERTENCIAS} advertencias", salida)
        self.assertIn("Baja", salida)


class DemoAmpliadoTests(TestCase):
    """El demo cubre capacitación, incidencias, formatos y liquidaciones."""

    def ejecutar(self):
        salida = StringIO()
        call_command("cargar_datos_demo", stdout=salida)
        return salida.getvalue()

    def test_cursos_y_participaciones(self):
        self.ejecutar()

        self.assertEqual(Curso.objects.count(), 2)
        self.assertEqual(Participacion.objects.count(), 3)
        self.assertEqual(
            Participacion.objects.filter(estado=EstadoParticipacion.COMPLETADO).count(),
            1,
        )
        # Idempotencia: segunda ejecución no duplica.
        self.ejecutar()
        self.assertEqual(Curso.objects.count(), 2)
        self.assertEqual(Participacion.objects.count(), 3)

    def test_incidencias_sin_advertencias_nuevas(self):
        self.ejecutar()

        self.assertEqual(Incidencia.objects.count(), 2)
        self.assertTrue(
            Incidencia.objects.filter(
                tipo=TipoIncidencia.QUEJA, estado_revision="PENDIENTE"
            ).exists()
        )
        # El demo no convierte quejas: las 10 advertencias no cambian.
        self.assertEqual(Advertencia.objects.count(), 10)
        self.ejecutar()
        self.assertEqual(Incidencia.objects.count(), 2)

    def test_formatos_firmados_y_borradores_sin_cierre(self):
        self.ejecutar()

        formatos = FormatoSemanal.objects.all()
        self.assertGreater(formatos.count(), 0)
        self.assertTrue(all(f.esta_firmado for f in formatos))
        self.assertTrue(
            formatos.filter(estado=EstadoFormato.REGULARIZADO).exists()
        )
        borradores = Liquidacion.objects.filter(estado=EstadoLiquidacion.BORRADOR)
        self.assertEqual(borradores.count(), formatos.count())
        self.assertFalse(
            Liquidacion.objects.filter(estado=EstadoLiquidacion.CERRADA).exists()
        )
        # Sin parámetros comerciales: el cierre sigue bloqueado.
        from liquidaciones.models import ParametrosLiquidacion

        self.assertFalse(ParametrosLiquidacion.obtener().configurados)
        self.ejecutar()
        self.assertEqual(FormatoSemanal.objects.count(), formatos.count())
        self.assertEqual(Liquidacion.objects.count(), borradores.count())

    def test_demo_no_crea_auditoria_ni_usuarios(self):
        self.ejecutar()

        self.assertEqual(RegistroAuditoria.objects.count(), 0)
        self.assertEqual(get_user_model().objects.count(), 0)
        self.ejecutar()
        self.assertEqual(get_user_model().objects.count(), 0)

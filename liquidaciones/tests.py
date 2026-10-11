"""Pruebas del módulo de formatos semanales y liquidaciones.

Cubren la firma del viernes, el pendiente sin pago, la regularización con
penalidad, los contratos que terminan antes del viernes, la exención de los
contratos inferiores a una semana, el reproceso sin duplicados, los parámetros
sin configurar, la inmutabilidad de la cerrada y los permisos por rol.
"""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from asignaciones.reglas import crear_asignacion
from comun.pruebas import (
    PruebaAutenticada,
    PruebaConsulta,
    crear_oferta,
    crear_transportista,
)
from liquidaciones import calculos
from liquidaciones.models import (
    EstadoFormato,
    EstadoLiquidacion,
    FormatoSemanal,
    Liquidacion,
    ParametrosLiquidacion,
)

HOY = timezone.localdate()
LUNES_PASADO = HOY - timedelta(days=HOY.weekday() + 7)
VIERNES_PASADO = LUNES_PASADO + timedelta(days=4)
DOMINGO_PASADO = LUNES_PASADO + timedelta(days=6)


def configurar(comision="10.00", penalidad="50.00"):
    parametros = ParametrosLiquidacion.obtener()
    parametros.comision_pct = Decimal(comision)
    parametros.penalidad_semanal = Decimal(penalidad)
    parametros.save()
    return parametros


def crear_asignacion_semanal(inicio=LUNES_PASADO, fin=DOMINGO_PASADO, **cambios):
    return crear_asignacion(
        transportista=crear_transportista(),
        oferta=crear_oferta(**cambios),
        fecha_inicio=inicio,
        fecha_fin=fin,
    )


def generar_formatos(asignacion):
    creados = []
    for lunes, domingo, viernes in calculos.semanas_servicio(
        asignacion.fecha_inicio, asignacion.fecha_fin
    ):
        formato, _ = FormatoSemanal.objects.get_or_create(
            asignacion=asignacion,
            periodo_inicio=lunes,
            defaults={"periodo_fin": domingo, "fecha_prevista": viernes},
        )
        creados.append(formato)
    return creados


class FirmaTests(PruebaAutenticada):
    def test_formato_firmado_el_viernes_queda_presentado(self):
        asignacion = crear_asignacion_semanal()
        formato = generar_formatos(asignacion)[0]

        respuesta = self.client.post(
            reverse("liquidaciones:formato_firmar", args=[formato.pk]),
            {"fecha_firma": VIERNES_PASADO.isoformat()},
        )

        self.assertEqual(respuesta.status_code, 302)
        formato.refresh_from_db()
        self.assertEqual(formato.estado, EstadoFormato.PRESENTADO)
        self.assertEqual(formato.semanas_retraso, 0)

    def test_formato_pendiente_no_se_paga(self):
        asignacion = crear_asignacion_semanal()
        formato = generar_formatos(asignacion)[0]

        self.assertTrue(formato.esta_atrasado)
        self.assertEqual(formato.etiqueta_estado, "Atrasado")

        respuesta = self.client.post(
            reverse("liquidaciones:liquidacion_generar", args=[formato.pk])
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertFalse(Liquidacion.objects.exists())

    def test_entrega_atrasada_se_regulariza_con_penalidad(self):
        configurar()
        asignacion = crear_asignacion_semanal()
        formato = generar_formatos(asignacion)[0]

        self.client.post(
            reverse("liquidaciones:formato_firmar", args=[formato.pk]),
            {"fecha_firma": (VIERNES_PASADO + timedelta(days=3)).isoformat()},
        )
        formato.refresh_from_db()

        self.assertEqual(formato.estado, EstadoFormato.REGULARIZADO)
        self.assertEqual(formato.semanas_retraso, 1)

        self.client.post(reverse("liquidaciones:liquidacion_generar", args=[formato.pk]))
        liquidacion = Liquidacion.objects.get()
        self.client.post(
            reverse("liquidaciones:liquidacion_cerrar", args=[liquidacion.pk])
        )

        liquidacion.refresh_from_db()
        self.assertEqual(liquidacion.estado, EstadoLiquidacion.CERRADA)
        self.assertEqual(liquidacion.penalidad_monto, Decimal("50.00"))
        self.assertEqual(liquidacion.total, Decimal("2500.00") - Decimal("250.00") - Decimal("50.00"))

        detalle = self.client.get(
            reverse("liquidaciones:liquidacion_detalle", args=[liquidacion.pk])
        )
        self.assertContains(detalle, "Base semanal")
        self.assertContains(detalle, "Comisión")
        self.assertContains(detalle, "1 semana(s) de retraso")
        self.assertContains(detalle, "Neto a pagar")

    def test_contrato_que_finaliza_antes_del_viernes_espera_al_viernes(self):
        miercoles = LUNES_PASADO + timedelta(days=2)
        asignacion = crear_asignacion_semanal(fin=miercoles)
        (formato,) = generar_formatos(asignacion)

        self.assertEqual(formato.fecha_prevista, VIERNES_PASADO)
        self.assertGreater(formato.fecha_prevista, miercoles)

        self.client.post(
            reverse("liquidaciones:formato_firmar", args=[formato.pk]),
            {"fecha_firma": VIERNES_PASADO.isoformat()},
        )
        formato.refresh_from_db()
        self.assertEqual(formato.estado, EstadoFormato.PRESENTADO)

    def test_contrato_inferior_a_una_semana_sin_penalidad(self):
        jueves = LUNES_PASADO + timedelta(days=3)
        asignacion = crear_asignacion_semanal(fin=jueves)
        (formato,) = generar_formatos(asignacion)

        self.client.post(
            reverse("liquidaciones:formato_firmar", args=[formato.pk]),
            {"fecha_firma": HOY.isoformat()},
        )
        formato.refresh_from_db()

        self.assertEqual(formato.estado, EstadoFormato.REGULARIZADO)
        self.assertEqual(formato.semanas_retraso, 0)

        ficha = self.client.get(
            reverse("liquidaciones:formato_detalle", args=[formato.pk])
        )
        self.assertContains(ficha, "Exento")


class LiquidacionTests(PruebaAutenticada):
    def test_reprocesar_no_duplica_la_penalidad(self):
        configurar()
        asignacion = crear_asignacion_semanal()
        formato = generar_formatos(asignacion)[0]
        formato.firmar(VIERNES_PASADO + timedelta(days=3))
        liquidacion = Liquidacion.objects.create(formato=formato)
        liquidacion.recalcular()
        primero = (liquidacion.penalidad_monto, liquidacion.total)

        liquidacion.recalcular()

        self.assertEqual((liquidacion.penalidad_monto, liquidacion.total), primero)
        self.assertEqual(Liquidacion.objects.count(), 1)

    def test_sin_parametros_no_hay_cierre_definitivo(self):
        asignacion = crear_asignacion_semanal()
        formato = generar_formatos(asignacion)[0]
        formato.firmar(VIERNES_PASADO)
        liquidacion = Liquidacion.objects.create(formato=formato)
        liquidacion.recalcular()

        respuesta = self.client.post(
            reverse("liquidaciones:liquidacion_cerrar", args=[liquidacion.pk])
        )

        self.assertEqual(respuesta.status_code, 302)
        liquidacion.refresh_from_db()
        self.assertEqual(liquidacion.estado, EstadoLiquidacion.BORRADOR)

    def test_cerrada_no_admite_cambios_ni_reproceso(self):
        configurar()
        asignacion = crear_asignacion_semanal()
        formato = generar_formatos(asignacion)[0]
        formato.firmar(VIERNES_PASADO)
        liquidacion = Liquidacion.objects.create(formato=formato)
        liquidacion.recalcular()
        liquidacion.cerrar()

        with self.assertRaises(ValidationError):
            liquidacion.recalcular()
        with self.assertRaises(ValidationError):
            formato.firmar(VIERNES_PASADO)

        respuesta = self.client.post(
            reverse("liquidaciones:formato_firmar", args=[formato.pk]),
            {"fecha_firma": VIERNES_PASADO.isoformat()},
        )
        self.assertEqual(respuesta.status_code, 200)
        formato.refresh_from_db()
        self.assertEqual(formato.estado, EstadoFormato.LIQUIDADO)

    def test_prorrateo_exacto_entre_semanas(self):
        asignacion = crear_asignacion_semanal(
            inicio=LUNES_PASADO - timedelta(days=7), fin=DOMINGO_PASADO
        )
        formatos = generar_formatos(asignacion)

        self.assertEqual(len(formatos), 2)
        bases = calculos.bases_semanales(asignacion.oferta.remuneracion, 2)

        self.assertEqual(sum(bases), asignacion.oferta.remuneracion)

    def test_generar_es_idempotente(self):
        asignacion = crear_asignacion_semanal()

        for _ in range(2):
            respuesta = self.client.post(
                reverse("liquidaciones:formatos_generar", args=[asignacion.pk])
            )
            self.assertEqual(respuesta.status_code, 302)

        self.assertEqual(asignacion.formatos.count(), 1)


class PermisosLiquidacionesTests(PruebaConsulta):
    def test_consulta_lee_pero_no_opera_finanzas(self):
        asignacion = crear_asignacion_semanal()
        formato = generar_formatos(asignacion)[0]

        self.assertEqual(
            self.client.get(reverse("liquidaciones:formatos_lista")).status_code, 200
        )
        self.assertEqual(
            self.client.get(
                reverse("liquidaciones:formato_detalle", args=[formato.pk])
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("liquidaciones:liquidaciones_lista")).status_code,
            200,
        )
        for nombre, args in (
            ("liquidaciones:formatos_generar", (asignacion.pk,)),
            ("liquidaciones:formato_firmar", (formato.pk,)),
            ("liquidaciones:liquidacion_generar", (formato.pk,)),
            ("liquidaciones:parametros", ()),
        ):
            with self.subTest(ruta=nombre):
                self.assertEqual(
                    self.client.get(reverse(nombre, args=args)).status_code, 403
                )
                self.assertEqual(
                    self.client.post(reverse(nombre, args=args), {}).status_code, 403
                )

    def test_operador_opera_finanzas(self):
        from django.contrib.auth.models import Group

        from comun.permisos import GRUPO_OPERADOR

        self.usuario.groups.set([Group.objects.get(name=GRUPO_OPERADOR)])
        asignacion = crear_asignacion_semanal()

        self.assertEqual(
            self.client.get(
                reverse("liquidaciones:formatos_generar", args=[asignacion.pk])
            ).status_code,
            200,
        )

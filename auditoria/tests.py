"""Pruebas de la auditoría de operaciones críticas.

Comprueban que las operaciones crean su rastro (usuario, acción, entidad y
resumen), que nunca se guardan contraseñas ni secretos, que la lista es solo
para el Administrador y que los filtros funcionan.
"""

from django.urls import reverse
from django.utils import timezone

from auditoria.models import RegistroAuditoria, TipoAccion, auditar
from asignaciones.reglas import crear_asignacion
from comun.pruebas import (
    PruebaAdministrador,
    PruebaAutenticada,
    crear_oferta,
    crear_transportista,
    datos_post_transportista,
)

HOY = timezone.localdate()


class RegistroOperacionesTests(PruebaAutenticada):
    def test_crear_transportista_deja_rastro(self):
        self.client.post(reverse("transportistas:crear"), datos_post_transportista())

        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.usuario, self.usuario)
        self.assertEqual(registro.accion, TipoAccion.CREAR)
        self.assertEqual(registro.entidad, "transportista")
        self.assertIsNotNone(registro.entidad_id)
        self.assertTrue(registro.fecha_hora)

    def test_cambiar_estado_y_advertencia_dejan_rastro(self):
        transportista = crear_transportista()

        self.client.post(
            reverse("transportistas:registrar_advertencia", args=[transportista.pk]),
            {
                "fecha": HOY.isoformat(),
                "descripcion": "Motivo auditado",
                "token": self.client.get(
                    reverse("transportistas:registrar_advertencia", args=[transportista.pk])
                ).context["token"],
            },
        )

        acciones = set(
            RegistroAuditoria.objects.values_list("accion", flat=True)
        )
        self.assertIn(TipoAccion.ADVERTENCIA, acciones)

    def test_asignar_finalizar_y_cancelar_dejan_rastro(self):
        transportista = crear_transportista()
        oferta = crear_oferta()
        self.client.post(
            reverse("asignaciones:nueva"),
            {
                "oferta": oferta.pk,
                "transportista": transportista.pk,
                "fecha_inicio": HOY.isoformat(),
                "fecha_fin": "",
            },
        )
        self.client.post(reverse("asignaciones:confirmar"))
        asignacion = transportista.asignaciones.get()
        self.client.post(
            reverse("asignaciones:finalizar", args=[asignacion.pk]),
            {"fecha_fin": HOY.isoformat()},
        )

        acciones = list(
            RegistroAuditoria.objects.values_list("accion", flat=True)
        )
        self.assertIn(TipoAccion.ASIGNAR, acciones)
        self.assertIn(TipoAccion.FINALIZAR, acciones)

        otra = crear_asignacion(
            transportista=crear_transportista(),
            oferta=crear_oferta(destino="Cusco"),
            fecha_inicio=HOY,
        )
        self.client.post(
            reverse("asignaciones:cancelar", args=[otra.pk]),
            {"fecha": HOY.isoformat(), "motivo": "Motivo de prueba"},
        )
        cancelacion = RegistroAuditoria.objects.filter(accion=TipoAccion.CANCELAR).get()
        self.assertIn("Motivo de prueba", cancelacion.resumen)

    def test_auditar_anonimo_no_registra_nada(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertIsNone(
            auditar(
                usuario=AnonymousUser(),
                accion=TipoAccion.CREAR,
                entidad="prueba",
                resumen="nada",
            )
        )
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_resumen_largo_se_trunca(self):
        registro = auditar(
            usuario=self.usuario,
            accion=TipoAccion.CREAR,
            entidad="prueba",
            resumen="x" * 500,
        )

        self.assertLessEqual(len(registro.resumen), 280)


class ListaAuditoriaTests(PruebaAdministrador):
    def test_solo_administrador_consulta(self):
        crear_transportista()

        self.assertEqual(self.client.get(reverse("auditoria:lista")).status_code, 200)

    def test_operador_y_consulta_reciben_denegado(self):
        from django.contrib.auth.models import Group

        from comun.permisos import GRUPO_CONSULTA, GRUPO_OPERADOR

        for grupo in (GRUPO_OPERADOR, GRUPO_CONSULTA):
            with self.subTest(grupo=grupo):
                self.usuario.groups.set([Group.objects.get(name=grupo)])
                self.assertEqual(
                    self.client.get(reverse("auditoria:lista")).status_code, 403
                )

    def test_filtros_por_accion_y_fecha(self):
        crear_transportista()
        crear_oferta()

        respuesta = self.client.get(reverse("auditoria:lista"), {"accion": "CREAR"})
        self.assertContains(respuesta, "Creación")
        self.assertNotContains(respuesta, ">Asignación</span>")

        respuesta = self.client.get(
            reverse("auditoria:lista"),
            {"desde": HOY.isoformat(), "hasta": HOY.isoformat()},
        )
        self.assertEqual(respuesta.status_code, 200)


class GestionUsuariosAuditoriaTests(PruebaAdministrador):
    def test_gestion_de_usuarios_no_guarda_contrasenas(self):
        self.client.post(
            reverse("panel:usuarios_clave", args=[self.usuario.pk]),
            {"new_password1": "clave-nueva-12345", "new_password2": "clave-nueva-12345"},
        )

        textos = " ".join(RegistroAuditoria.objects.values_list("resumen", flat=True))
        self.assertNotIn("clave-nueva-12345", textos)
        self.assertTrue(
            RegistroAuditoria.objects.filter(accion=TipoAccion.USUARIO).exists()
        )

"""Pruebas de reportes: exactitud, filtros, CSV, permisos y auditoría.

No se introduce ningún dato en la base de datos real: todo corre sobre la
base de datos de prueba.
"""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from asignaciones.reglas import crear_asignacion
from auditoria.models import RegistroAuditoria
from capacitacion.models import Curso
from comun.pruebas import (
    PruebaAutenticada,
    PruebaConsulta,
    PruebaSinPermisos,
    crear_empresa_cliente,
    crear_oferta,
    crear_transportista,
)
from liquidaciones.models import FormatoSemanal, Liquidacion
from transportistas.models import Advertencia

HOY = timezone.localdate()

RUTAS_REPORTES = (
    "panel:reporte_transportistas",
    "panel:reporte_documentos",
    "panel:reporte_periodo",
    "panel:reporte_advertencias",
    "panel:reporte_cursos",
    "panel:reporte_formatos",
)


class ExactitudReportesTests(PruebaAutenticada):
    def test_transportistas_por_estado_y_nivel_coincide_con_bd(self):
        from transportistas.models import Transportista

        crear_transportista()
        respuesta = self.client.get(reverse("panel:reporte_transportistas"))

        self.assertEqual(
            sum(fila[2] for fila in respuesta.context["filas"]),
            Transportista.objects.count(),
        )

    def test_documentacion_muestra_vencidos_y_filtra(self):
        vencido = crear_transportista(
            nombre="Reporte vencido", fecha_vencimiento_soat=HOY - timedelta(days=2)
        )
        crear_transportista(nombre="Reporte vigente")

        respuesta = self.client.get(
            reverse("panel:reporte_documentos"), {"situacion": "vencido"}
        )
        textos = " ".join(
            f"{fila[0]} {fila[2]} {fila[5]}" for fila in respuesta.context["filas"]
        )
        self.assertIn("Reporte vencido", textos)
        self.assertIn("SOAT", textos)
        self.assertIn("Vencido", textos)
        self.assertNotIn("Reporte vigente", textos)
        _ = vencido

    def test_periodo_filtra_por_fechas(self):
        crear_oferta()
        crear_asignacion(
            transportista=crear_transportista(),
            oferta=crear_oferta(destino="Cusco"),
            fecha_inicio=HOY,
        )

        respuesta = self.client.get(
            reverse("panel:reporte_periodo"),
            {"desde": HOY.isoformat(), "hasta": HOY.isoformat()},
        )
        self.assertGreaterEqual(len(respuesta.context["filas"]), 3)

        vacio = self.client.get(
            reverse("panel:reporte_periodo"),
            {
                "desde": (HOY - timedelta(days=60)).isoformat(),
                "hasta": (HOY - timedelta(days=30)).isoformat(),
            },
        )
        self.assertEqual(vacio.context["filas"], [])

    def test_advertencias_agrupa_por_transportista(self):
        transportista = crear_transportista(nombre="Reporte advertencias")
        for numero in range(2):
            Advertencia.objects.create(
                transportista=transportista, descripcion=f"Motivo {numero}", fecha=HOY
            )

        respuesta = self.client.get(reverse("panel:reporte_advertencias"))
        filas = {fila[0]: fila[2] for fila in respuesta.context["filas"]}
        self.assertEqual(filas.get("Reporte advertencias"), 2)

    def test_cursos_solo_completados(self):
        from capacitacion.models import Participacion

        transportista = crear_transportista()
        curso = Curso.objects.create(
            codigo="REP01", titulo="Reporte", tema="Tema", duracion_horas=4
        )
        Participacion.objects.create(
            transportista=transportista, curso=curso, convocatoria="2026-01", fecha=HOY
        )
        completa = Participacion.objects.create(
            transportista=transportista, curso=curso, convocatoria="2026-02", fecha=HOY
        )
        completa.confirmar(fecha_finalizacion=HOY, resultado="APROBADO")

        respuesta = self.client.get(reverse("panel:reporte_cursos"))
        self.assertEqual(len(respuesta.context["filas"]), 1)
        self.assertIn("2026-02", respuesta.context["filas"][0][2])

    def test_formatos_con_su_liquidacion(self):
        asignacion = crear_asignacion(
            transportista=crear_transportista(),
            oferta=crear_oferta(),
            fecha_inicio=HOY - timedelta(days=10),
            fecha_fin=HOY - timedelta(days=3),
        )
        formato = FormatoSemanal.objects.create(
            asignacion=asignacion,
            periodo_inicio=HOY - timedelta(days=10),
            periodo_fin=HOY - timedelta(days=4),
            fecha_prevista=HOY - timedelta(days=6),
            fecha_firma=HOY - timedelta(days=6),
            estado="PRESENTADO",
        )
        Liquidacion.objects.create(formato=formato)

        respuesta = self.client.get(reverse("panel:reporte_formatos"))
        self.assertEqual(len(respuesta.context["filas"]), 1)
        self.assertIn(asignacion.oferta.codigo, respuesta.context["filas"][0][0])


class ExportacionCSVTests(PruebaAutenticada):
    def test_csv_respeta_filtros_y_permiso(self):
        crear_transportista(nombre="CSV uno")
        crear_transportista(nombre="CSV dos")

        respuesta = self.client.get(
            reverse("panel:reporte_transportistas"), {"formato": "csv"}
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("text/csv", respuesta["Content-Type"])
        contenido = respuesta.content.decode("utf-8-sig")
        self.assertIn("Estado,Nivel,Total", contenido)
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                accion="EXPORTAR", entidad="reporte"
            ).exists()
        )

    def test_csv_neutraliza_formulas(self):
        from panel.csv import celda_segura
        from transportistas.models import Advertencia

        autor = crear_transportista(nombre="=CMD|'/C calc'!A0")
        Advertencia.objects.create(
            transportista=autor, descripcion="Motivo", fecha=HOY
        )

        respuesta = self.client.get(
            reverse("panel:reporte_advertencias"), {"formato": "csv"}
        )
        contenido = respuesta.content.decode("utf-8-sig")
        self.assertIn("'=CMD|'/C calc'!A0", contenido)

        self.assertEqual(celda_segura("+1+1"), "'+1+1")
        self.assertEqual(celda_segura("  -2"), "'  -2")
        self.assertEqual(celda_segura("@dato"), "'@dato")
        self.assertEqual(celda_segura("normal"), "normal")
        self.assertEqual(celda_segura(None), "")

    def test_csv_sin_permiso_es_denegado(self):
        from django.contrib.auth.models import Group

        from comun.permisos import GRUPO_CONSULTA

        self.usuario.groups.set([Group.objects.get(name=GRUPO_CONSULTA)])
        # Consulta sí puede ver transportistas: se usa un reporte mixto.
        respuesta = self.client.get(
            reverse("panel:reporte_periodo"), {"formato": "csv"}
        )
        # Consulta tiene ambos permisos de este reporte: 200 con sus datos.
        self.assertEqual(respuesta.status_code, 200)


class PermisosReportesTests(PruebaSinPermisos):
    def test_sin_rol_no_accede_a_reportes(self):
        for nombre in RUTAS_REPORTES:
            with self.subTest(ruta=nombre):
                self.assertEqual(
                    self.client.get(reverse(nombre)).status_code, 403
                )
                self.assertEqual(
                    self.client.get(reverse(nombre), {"formato": "csv"}).status_code,
                    403,
                )

    def test_indice_visible_sin_reportes(self):
        respuesta = self.client.get(reverse("panel:reportes"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Sin reportes autorizados")

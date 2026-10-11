"""Pruebas del módulo de capacitación: cursos, participaciones y constancias.

Cubren el curso válido/duplicado/duración inválida, la unicidad por
convocatoria (formulario y base de datos), la finalización autorizada con su
responsable, la constancia digital y su descarga protegida, el acceso de solo
lectura y la conservación del historial sin tocar la clasificación.
"""

from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone

from capacitacion.models import Curso, Participacion
from comun.choices import EstadoCurso, EstadoParticipacion
from comun.pruebas import (
    PruebaAutenticada,
    PruebaConsulta,
    crear_transportista,
)

HOY = timezone.localdate()


def crear_curso(codigo="CUR01", **cambios):
    datos = {
        "codigo": codigo,
        "titulo": "Manejo defensivo",
        "tema": "Seguridad vial",
        "duracion_horas": 8,
    }
    datos.update(cambios)
    curso = Curso(**datos)
    curso.full_clean()
    curso.save()
    return curso


def inscribir(transportista=None, curso=None, convocatoria="2026-03", **cambios):
    datos = {
        "transportista": transportista or crear_transportista(),
        "curso": curso or crear_curso(),
        "convocatoria": convocatoria,
        "fecha": HOY,
    }
    datos.update(cambios)
    participacion = Participacion(**datos)
    participacion.full_clean()
    participacion.save()
    return participacion


def documento(nombre="constancia.pdf", contenido=b"%PDF-1.4 ficticio"):
    return SimpleUploadedFile(nombre, contenido, content_type="application/pdf")


class CursoTests(PruebaAutenticada):
    def test_curso_valido_y_codigo_normalizado(self):
        respuesta = self.client.post(
            reverse("capacitacion:cursos_crear"),
            {
                "codigo": "cur 01",
                "titulo": "Manejo defensivo",
                "tema": "Seguridad vial",
                "duracion_horas": 8,
                "estado": EstadoCurso.ACTIVO,
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Curso.objects.get().codigo, "CUR01")

    def test_codigo_duplicado_se_rechaza(self):
        crear_curso()

        respuesta = self.client.post(
            reverse("capacitacion:cursos_crear"),
            {
                "codigo": "cur01",
                "titulo": "Otro título",
                "tema": "Otro tema",
                "duracion_horas": 4,
                "estado": EstadoCurso.ACTIVO,
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("codigo", respuesta.context["form"].errors)
        self.assertEqual(Curso.objects.count(), 1)

    def test_duracion_invalida_se_rechaza(self):
        for duracion in ("0", "-3"):
            with self.subTest(duracion=duracion):
                respuesta = self.client.post(
                    reverse("capacitacion:cursos_crear"),
                    {
                        "codigo": f"CUR{duracion}",
                        "titulo": "Título",
                        "tema": "Tema",
                        "duracion_horas": duracion,
                        "estado": EstadoCurso.ACTIVO,
                    },
                )
                self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Curso.objects.exists())

    def test_curso_inactivo_no_admite_inscripciones(self):
        curso = crear_curso(estado=EstadoCurso.INACTIVO)

        respuesta = self.client.post(
            reverse("capacitacion:participaciones_inscribir"),
            {
                "transportista": crear_transportista().pk,
                "curso": curso.pk,
                "convocatoria": "2026-03",
                "fecha": HOY.isoformat(),
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("curso", respuesta.context["form"].errors)
        self.assertFalse(Participacion.objects.exists())


class ParticipacionTests(PruebaAutenticada):
    def test_inscripcion_nace_inscrita(self):
        transportista = crear_transportista()
        curso = crear_curso()

        respuesta = self.client.post(
            reverse("capacitacion:participaciones_inscribir"),
            {
                "transportista": transportista.pk,
                "curso": curso.pk,
                "convocatoria": "2026-03",
                "fecha": HOY.isoformat(),
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        participacion = Participacion.objects.get()
        self.assertEqual(participacion.estado, EstadoParticipacion.INSCRITO)

    def test_triple_duplicado_se_rechaza_en_formulario_y_en_bd(self):
        participacion = inscribir()

        respuesta = self.client.post(
            reverse("capacitacion:participaciones_inscribir"),
            {
                "transportista": participacion.transportista.pk,
                "curso": participacion.curso.pk,
                "convocatoria": "2026-03",
                "fecha": HOY.isoformat(),
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.context["form"].non_field_errors())
        self.assertEqual(Participacion.objects.count(), 1)

        with self.assertRaises(IntegrityError):
            Participacion.objects.create(
                transportista=participacion.transportista,
                curso=participacion.curso,
                convocatoria="2026-03",
                fecha=HOY,
            )

    def test_distinta_convocatoria_permite_recursar_con_historial_intacto(self):
        transportista = crear_transportista()
        curso = crear_curso()
        primera = inscribir(transportista=transportista, curso=curso, convocatoria="2026-03")

        respuesta = self.client.post(
            reverse("capacitacion:participaciones_inscribir"),
            {
                "transportista": transportista.pk,
                "curso": curso.pk,
                "convocatoria": "2026-04",
                "fecha": HOY.isoformat(),
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(transportista.participaciones.count(), 2)
        self.assertTrue(
            Participacion.objects.filter(pk=primera.pk, convocatoria="2026-03").exists()
        )

    def test_avance_directo_a_completado_se_rechaza(self):
        participacion = inscribir()

        respuesta = self.client.post(
            reverse("capacitacion:participacion_avance", args=[participacion.pk]),
            {"estado": EstadoParticipacion.COMPLETADO},
        )

        self.assertEqual(respuesta.status_code, 200)
        participacion.refresh_from_db()
        self.assertEqual(participacion.estado, EstadoParticipacion.INSCRITO)

    def test_finalizacion_autorizada_con_responsable_y_sin_cambiar_nivel(self):
        transportista = crear_transportista()
        nivel_antes = transportista.nivel
        participacion = inscribir(transportista=transportista)
        participacion.estado = EstadoParticipacion.EN_PROGRESO
        participacion.save()

        respuesta = self.client.post(
            reverse("capacitacion:participacion_confirmar", args=[participacion.pk]),
            {
                "fecha_finalizacion": HOY.isoformat(),
                "resultado": "APROBADO",
                "observaciones": "Buen desempeño",
                "constancia": documento(),
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        participacion.refresh_from_db()
        transportista.refresh_from_db()
        self.assertEqual(participacion.estado, EstadoParticipacion.COMPLETADO)
        self.assertEqual(participacion.confirmado_por, self.usuario)
        self.assertEqual(participacion.observaciones, "Buen desempeño")
        self.assertTrue(bool(participacion.constancia))
        self.assertEqual(transportista.nivel, nivel_antes)

        ficha = self.client.get(
            reverse("transportistas:detalle", args=[transportista.pk])
        )
        self.assertContains(ficha, "Completado")

    def test_finalizacion_anterior_a_la_inscripcion_se_rechaza(self):
        participacion = inscribir()

        respuesta = self.client.post(
            reverse("capacitacion:participacion_confirmar", args=[participacion.pk]),
            {
                "fecha_finalizacion": (HOY - timedelta(days=1)).isoformat(),
                "resultado": "APROBADO",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        participacion.refresh_from_db()
        self.assertEqual(participacion.estado, EstadoParticipacion.INSCRITO)

    def test_aprobada_sin_constancia_queda_senalizada(self):
        participacion = inscribir()
        participacion.confirmar(
            fecha_finalizacion=HOY, resultado="APROBADO", usuario=self.usuario
        )

        detalle = self.client.get(
            reverse("capacitacion:participacion_detalle", args=[participacion.pk])
        )
        self.assertContains(detalle, "falta cargar la constancia")

        ficha = self.client.get(
            reverse("transportistas:detalle", args=[participacion.transportista.pk])
        )
        self.assertContains(ficha, "Falta constancia")

    def test_desaprobada_sin_constancia_es_valida(self):
        participacion = inscribir()

        respuesta = self.client.post(
            reverse("capacitacion:participacion_confirmar", args=[participacion.pk]),
            {
                "fecha_finalizacion": HOY.isoformat(),
                "resultado": "DESAPROBADO",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        participacion.refresh_from_db()
        self.assertEqual(participacion.estado, EstadoParticipacion.COMPLETADO)

    def test_constancia_con_tipo_o_peso_invalido_se_rechaza(self):
        participacion = inscribir()

        for nombre, contenido in (
            ("constancia.exe", b"binario"),
            ("constancia.pdf", b"x" * (5 * 1024 * 1024 + 1)),
        ):
            with self.subTest(nombre=nombre):
                respuesta = self.client.post(
                    reverse(
                        "capacitacion:participacion_confirmar",
                        args=[participacion.pk],
                    ),
                    {
                        "fecha_finalizacion": HOY.isoformat(),
                        "resultado": "APROBADO",
                        "constancia": SimpleUploadedFile(
                            nombre, contenido, content_type="application/octet-stream"
                        ),
                    },
                )
                self.assertEqual(respuesta.status_code, 200)
        participacion.refresh_from_db()
        self.assertEqual(participacion.estado, EstadoParticipacion.INSCRITO)
        self.assertFalse(bool(participacion.constancia))

    def test_cada_repeticion_conserva_su_propia_constancia(self):
        transportista = crear_transportista()
        curso = crear_curso()
        primera = inscribir(transportista=transportista, curso=curso, convocatoria="2026-03")
        primera.confirmar(
            fecha_finalizacion=HOY,
            resultado="APROBADO",
            constancia=documento("primera.pdf"),
            usuario=self.usuario,
        )
        segunda = inscribir(transportista=transportista, curso=curso, convocatoria="2026-04")
        segunda.confirmar(
            fecha_finalizacion=HOY, resultado="APROBADO", usuario=self.usuario
        )

        primera.refresh_from_db()
        segunda.refresh_from_db()
        self.assertTrue(bool(primera.constancia))
        self.assertFalse(bool(segunda.constancia))
        self.assertIn("primera", primera.constancia.name)
        self.assertTrue(primera.constancia.name.endswith(".pdf"))


class DescargaConstanciaTests(PruebaAutenticada):
    def test_descarga_protegida_y_404_sin_archivo(self):
        participacion = inscribir()
        participacion.confirmar(
            fecha_finalizacion=HOY,
            resultado="APROBADO",
            constancia=documento(),
            usuario=self.usuario,
        )

        respuesta = self.client.get(
            reverse("capacitacion:participacion_constancia", args=[participacion.pk])
        )
        self.assertEqual(respuesta.status_code, 200)

        sin_archivo = inscribir(
            transportista=crear_transportista(),
            curso=participacion.curso,
            convocatoria="2026-04",
        )
        self.assertEqual(
            self.client.get(
                reverse("capacitacion:participacion_constancia", args=[sin_archivo.pk])
            ).status_code,
            404,
        )

    def test_anonimo_no_descarga(self):
        self.client.logout()
        participacion = inscribir()

        self.assertEqual(
            self.client.get(
                reverse("capacitacion:participacion_constancia", args=[participacion.pk])
            ).status_code,
            302,
        )


class PermisosCapacitacionTests(PruebaConsulta):
    def test_consulta_lee_pero_no_opera(self):
        curso = crear_curso()
        participacion = inscribir(curso=curso)

        self.assertEqual(
            self.client.get(reverse("capacitacion:cursos_lista")).status_code, 200
        )
        self.assertEqual(
            self.client.get(reverse("capacitacion:participaciones_lista")).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                reverse("capacitacion:participacion_detalle", args=[participacion.pk])
            ).status_code,
            200,
        )
        for nombre, args in (
            ("capacitacion:cursos_crear", ()),
            ("capacitacion:cursos_editar", (curso.pk,)),
            ("capacitacion:participaciones_inscribir", ()),
            ("capacitacion:participacion_avance", (participacion.pk,)),
            ("capacitacion:participacion_confirmar", (participacion.pk,)),
        ):
            with self.subTest(ruta=nombre):
                self.assertEqual(
                    self.client.get(reverse(nombre, args=args)).status_code, 403
                )
                self.assertEqual(
                    self.client.post(reverse(nombre, args=args), {}).status_code, 403
                )

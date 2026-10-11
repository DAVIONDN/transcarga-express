"""Vistas de capacitación: cursos e historial de participaciones.

Administran cursos quienes tienen `add/change_curso`; inscriben y confirman
quienes tienen `add_participacion` y `finalizar_participacion` (Operador y
Administrador). Consulta solo lee. Completar exige la confirmación explícita.
"""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import CreateView, DetailView, FormView, ListView, UpdateView, View

from auditoria.models import TipoAccion, auditar
from comun.choices import EstadoCurso, EstadoParticipacion
from comun.permisos import PermisoRequeridoMixin
from transportistas.models import Transportista

from .forms import (
    AvanzarParticipacionForm,
    ConfirmarParticipacionForm,
    CursoForm,
    InscribirParticipacionForm,
)
from .models import Curso, Participacion


class ListaCursosView(PermisoRequeridoMixin, ListView):
    permiso_requerido = "capacitacion.view_curso"
    model = Curso
    template_name = "capacitacion/cursos_lista.html"
    context_object_name = "cursos"
    paginate_by = 15

    def get_queryset(self):
        consulta = super().get_queryset()
        texto = (self.request.GET.get("q") or "").strip()
        if texto:
            consulta = consulta.filter(
                Q(codigo__icontains=texto)
                | Q(titulo__icontains=texto)
                | Q(tema__icontains=texto)
            )
        estado = self.request.GET.get("estado", "")
        if estado:
            consulta = consulta.filter(estado=estado)
        return consulta.annotate(total_participaciones=Count("participaciones"))

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Cursos"
        contexto["estados"] = EstadoCurso.choices
        contexto["filtros"] = {
            "q": self.request.GET.get("q", ""),
            "estado": self.request.GET.get("estado", ""),
        }
        contexto["hay_filtros"] = any(contexto["filtros"].values())
        return contexto


class CrearCursoView(PermisoRequeridoMixin, CreateView):
    permiso_requerido = "capacitacion.add_curso"
    model = Curso
    form_class = CursoForm
    template_name = "capacitacion/curso_formulario.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Nuevo curso"
        contexto["texto_boton"] = "Registrar curso"
        return contexto

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        auditar(
            usuario=self.request.user,
            accion=TipoAccion.CURSO,
            entidad="curso",
            entidad_id=self.object.pk,
            resumen=f"Alta de {self.object.codigo}.",
        )
        messages.success(
            self.request, f"Curso «{self.object.codigo}» registrado correctamente."
        )
        return respuesta

    def get_success_url(self):
        return reverse("capacitacion:cursos_lista")


class EditarCursoView(PermisoRequeridoMixin, UpdateView):
    permiso_requerido = "capacitacion.change_curso"
    model = Curso
    form_class = CursoForm
    template_name = "capacitacion/curso_formulario.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = f"Editar curso: {self.object.codigo}"
        contexto["texto_boton"] = "Guardar cambios"
        return contexto

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        auditar(
            usuario=self.request.user,
            accion=TipoAccion.CURSO,
            entidad="curso",
            entidad_id=self.object.pk,
            resumen=f"Edición de {self.object.codigo}.",
        )
        messages.success(self.request, "Cambios del curso guardados.")
        return respuesta

    def get_success_url(self):
        return reverse("capacitacion:cursos_lista")


class ListaParticipacionesView(PermisoRequeridoMixin, ListView):
    permiso_requerido = "capacitacion.view_participacion"
    model = Participacion
    template_name = "capacitacion/participaciones_lista.html"
    context_object_name = "participaciones"
    paginate_by = 15

    def get_queryset(self):
        consulta = super().get_queryset().select_related("transportista", "curso")
        texto = (self.request.GET.get("q") or "").strip()
        if texto:
            consulta = consulta.filter(
                Q(transportista__nombre__icontains=texto)
                | Q(curso__codigo__icontains=texto)
                | Q(curso__titulo__icontains=texto)
                | Q(convocatoria__icontains=texto)
            )
        curso = self.request.GET.get("curso", "")
        if curso.isdigit():
            consulta = consulta.filter(curso_id=int(curso))
        estado = self.request.GET.get("estado", "")
        if estado:
            consulta = consulta.filter(estado=estado)
        return consulta

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Participaciones"
        contexto["cursos"] = Curso.objects.order_by("codigo")
        contexto["estados"] = EstadoParticipacion.choices
        contexto["completadas"] = (
            self.get_queryset().filter(estado=EstadoParticipacion.COMPLETADO).count()
        )
        contexto["filtros"] = {
            "q": self.request.GET.get("q", ""),
            "curso": self.request.GET.get("curso", ""),
            "estado": self.request.GET.get("estado", ""),
        }
        contexto["hay_filtros"] = any(contexto["filtros"].values())
        return contexto


class InscribirView(PermisoRequeridoMixin, CreateView):
    permiso_requerido = "capacitacion.add_participacion"
    model = Participacion
    form_class = InscribirParticipacionForm
    template_name = "capacitacion/participacion_inscribir.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Inscribir participación"
        contexto["texto_boton"] = "Registrar inscripción"
        return contexto

    def form_valid(self, form):
        try:
            respuesta = super().form_valid(form)
        except IntegrityError:
            form.add_error(
                None,
                "Ese transportista ya está inscrito en este curso y convocatoria.",
            )
            return self.form_invalid(form)
        messages.success(
            self.request,
            f"Inscripción registrada: {self.object.transportista.nombre} en "
            f"{self.object.curso.codigo} ({self.object.convocatoria}).",
        )
        auditar(
            usuario=self.request.user,
            accion=TipoAccion.CURSO,
            entidad="participacion",
            entidad_id=self.object.pk,
            resumen=f"Inscripción de {self.object.transportista.nombre} en {self.object.curso.codigo}.",
        )
        return respuesta

    def get_success_url(self):
        return reverse(
            "capacitacion:participacion_detalle", args=[self.object.pk]
        )


class DetalleParticipacionView(PermisoRequeridoMixin, DetailView):
    permiso_requerido = "capacitacion.view_participacion"
    model = Participacion
    template_name = "capacitacion/participacion_detalle.html"
    context_object_name = "participacion"

    def get_queryset(self):
        return super().get_queryset().select_related(
            "transportista", "curso", "confirmado_por"
        )

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = f"Participación en {self.object.curso.codigo}"
        return contexto


class AvanzarParticipacionView(PermisoRequeridoMixin, UpdateView):
    permiso_requerido = "capacitacion.add_participacion"
    model = Participacion
    form_class = AvanzarParticipacionForm
    template_name = "capacitacion/participacion_avanzar.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["participacion"] = self.object
        contexto["titulo"] = "Actualizar avance"
        contexto["texto_boton"] = "Guardar avance"
        return contexto

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        auditar(
            usuario=self.request.user,
            accion=TipoAccion.CURSO,
            entidad="participacion",
            entidad_id=self.object.pk,
            resumen=f"Avance a «{self.object.get_estado_display()}».",
        )
        messages.success(self.request, "Avance de la participación actualizado.")
        return respuesta

    def get_success_url(self):
        return reverse(
            "capacitacion:participacion_detalle", args=[self.object.pk]
        )


class ConfirmarParticipacionView(PermisoRequeridoMixin, FormView):
    permiso_requerido = "capacitacion.finalizar_participacion"
    form_class = ConfirmarParticipacionForm
    template_name = "capacitacion/participacion_confirmar.html"

    def get_participacion(self):
        if not hasattr(self, "_participacion"):
            self._participacion = get_object_or_404(Participacion, pk=self.kwargs["pk"])
        return self._participacion

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["participacion"] = self.get_participacion()
        return kwargs

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["participacion"] = self.get_participacion()
        contexto["titulo"] = "Confirmar finalización"
        return contexto

    def form_valid(self, form):
        participacion = self.get_participacion()
        try:
            participacion.confirmar(
                fecha_finalizacion=form.cleaned_data["fecha_finalizacion"],
                resultado=form.cleaned_data["resultado"],
                observaciones=form.cleaned_data["observaciones"],
                constancia=form.cleaned_data["constancia"],
                usuario=self.request.user,
            )
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        messages.success(
            self.request,
            f"Finalización confirmada: {participacion.transportista.nombre} "
            f"completó {participacion.curso.codigo} "
            f"({participacion.get_resultado_display().lower()}).",
        )
        auditar(
            usuario=self.request.user,
            accion=TipoAccion.CURSO,
            entidad="participacion",
            entidad_id=participacion.pk,
            resumen=f"Finalización {participacion.get_resultado_display().lower()} de {participacion.curso.codigo}.",
        )
        return redirect(
            "capacitacion:participacion_detalle", pk=participacion.pk
        )


class DescargarConstanciaView(PermisoRequeridoMixin, View):
    """Descarga protegida de la constancia (según permisos de consulta)."""

    permiso_requerido = "capacitacion.view_participacion"

    def get(self, request, *args, **kwargs):
        participacion = get_object_or_404(Participacion, pk=self.kwargs["pk"])
        if not participacion.constancia:
            raise Http404("Esta participación no tiene constancia cargada.")
        return FileResponse(
            participacion.constancia.open("rb"),
            as_attachment=True,
            filename=participacion.constancia.name.rsplit("/", 1)[-1],
        )

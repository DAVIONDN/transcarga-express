"""Vistas de quejas, renuncias y excepciones a la baja (incidencias).

Todas exigen sesión iniciada y permiso en el servidor, en GET y POST. Se
reutilizan los permisos de advertencias: quien puede registrar advertencias
opera las incidencias; quien puede verlas las consulta. Registrar una
incidencia nunca cambia estados ni crea advertencias solas.
"""

import secrets

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import CreateView, DetailView, FormView, ListView, View

from auditoria.models import TipoAccion, auditar
from comun.choices import EstadoRevision, TipoIncidencia
from comun.permisos import PermisoRequeridoMixin

from .forms import IncidenciaForm, VincularReemplazoForm
from .models import Advertencia, Incidencia


class IncidenciaMixin:
    """Obtiene la incidencia indicada en la URL."""

    def get_incidencia(self):
        if not hasattr(self, "_incidencia"):
            self._incidencia = get_object_or_404(
                Incidencia.objects.select_related(
                    "transportista",
                    "empresa_cliente",
                    "asignacion",
                    "asignacion__oferta",
                    "registrado_por",
                    "advertencia_generada",
                    "transportista_reemplazo",
                    "nueva_asignacion",
                    "nueva_asignacion__oferta",
                    "nueva_asignacion__transportista",
                ),
                pk=self.kwargs["pk"],
            )
        return self._incidencia


class ListaIncidenciasView(PermisoRequeridoMixin, ListView):
    """Historial consultable de incidencias, con filtros por tipo y revisión."""

    permiso_requerido = "transportistas.view_advertencia"
    model = Incidencia
    template_name = "transportistas/incidencias/lista.html"
    context_object_name = "incidencias"
    paginate_by = 15

    def get_queryset(self):
        consulta = super().get_queryset().select_related(
            "transportista", "empresa_cliente", "asignacion", "registrado_por"
        )
        texto = (self.request.GET.get("q") or "").strip()
        if texto:
            consulta = consulta.filter(
                Q(descripcion__icontains=texto)
                | Q(transportista__nombre__icontains=texto)
                | Q(empresa_cliente__razon_social__icontains=texto)
            )
        tipo = self.request.GET.get("tipo")
        if tipo:
            consulta = consulta.filter(tipo=tipo)
        revision = self.request.GET.get("revision")
        if revision:
            consulta = consulta.filter(estado_revision=revision)
        return consulta

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Quejas e incidencias"
        contexto["tipos"] = TipoIncidencia.choices
        contexto["revisiones"] = EstadoRevision.choices
        contexto["filtros"] = {
            "q": self.request.GET.get("q", ""),
            "tipo": self.request.GET.get("tipo", ""),
            "revision": self.request.GET.get("revision", ""),
        }
        contexto["hay_filtros"] = any(contexto["filtros"].values())
        return contexto


class CrearIncidenciaView(PermisoRequeridoMixin, CreateView):
    permiso_requerido = "transportistas.add_advertencia"
    model = Incidencia
    form_class = IncidenciaForm
    template_name = "transportistas/incidencias/formulario.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Registrar incidencia"
        contexto["texto_boton"] = "Registrar incidencia"
        return contexto

    def form_valid(self, form):
        incidencia = form.save(commit=False)
        if self.request.user.is_authenticated:
            incidencia.registrado_por = self.request.user
        incidencia.save()
        auditar(
            usuario=self.request.user,
            accion=TipoAccion.CREAR,
            entidad="incidencia",
            entidad_id=incidencia.pk,
            resumen=f"{incidencia.get_tipo_display()} a {incidencia.transportista.nombre}.",
        )
        messages.success(
            self.request,
            f"Incidencia registrada ({incidencia.get_tipo_display().lower()}). "
            "No genera advertencias ni cambia estados por sí sola.",
        )
        return redirect("transportistas:incidencias_detalle", pk=incidencia.pk)


class DetalleIncidenciaView(IncidenciaMixin, PermisoRequeridoMixin, DetailView):
    permiso_requerido = "transportistas.view_advertencia"
    model = Incidencia
    template_name = "transportistas/incidencias/detalle.html"
    context_object_name = "incidencia"

    def get_object(self, queryset=None):
        return self.get_incidencia()

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = f"Incidencia: {self.object.get_tipo_display()}"
        return contexto


class RevisarIncidenciaView(IncidenciaMixin, PermisoRequeridoMixin, View):
    """Marca la incidencia como revisada, con confirmación."""

    permiso_requerido = "transportistas.add_advertencia"
    template_name = "transportistas/incidencias/confirmar_accion.html"

    def get(self, request, *args, **kwargs):
        return render(
            request,
            self.template_name,
            {
                "incidencia": self.get_incidencia(),
                "titulo": "Marcar incidencia como revisada",
                "texto_boton": "Confirmar revisión",
                "descripcion_accion": "La incidencia quedará marcada como revisada. "
                "No se crea ninguna advertencia.",
            },
        )

    def post(self, request, *args, **kwargs):
        incidencia = self.get_incidencia()
        incidencia.estado_revision = EstadoRevision.REVISADA
        incidencia.save(update_fields=["estado_revision"])
        auditar(
            usuario=request.user,
            accion=TipoAccion.ACTUALIZAR,
            entidad="incidencia",
            entidad_id=incidencia.pk,
            resumen="Marcada como revisada.",
        )
        messages.success(request, "Incidencia marcada como revisada.")
        return redirect("transportistas:incidencias_detalle", pk=incidencia.pk)


class ConvertirEnAdvertenciaView(IncidenciaMixin, PermisoRequeridoMixin, View):
    """Registra la advertencia formal a partir de la incidencia, con confirmación.

    Como máximo una advertencia por incidencia (enlace uno a uno): un segundo
    envío no crea otra. La baja por tres advertencias se aplica por la vía
    habitual, contando siempre desde la base de datos.
    """

    permiso_requerido = "transportistas.add_advertencia"
    template_name = "transportistas/incidencias/confirmar_accion.html"

    def clave_token(self):
        return f"incidencia_convertir_{self.get_incidencia().pk}"

    def token(self):
        if not self.request.session.get(self.clave_token()):
            self.request.session[self.clave_token()] = secrets.token_urlsafe(16)
        return self.request.session[self.clave_token()]

    def get(self, request, *args, **kwargs):
        incidencia = self.get_incidencia()
        if incidencia.advertencia_generada_id:
            messages.info(
                request, "Esta incidencia ya generó su advertencia formal."
            )
            return redirect("transportistas:incidencias_detalle", pk=incidencia.pk)
        return render(
            request,
            self.template_name,
            {
                "incidencia": incidencia,
                "titulo": "Convertir en advertencia formal",
                "texto_boton": "Registrar advertencia",
                "descripcion_accion": "Se registrará una advertencia formal al "
                "transportista (cuenta hacia la baja por tres advertencias).",
                "token": self.token(),
            },
        )

    def post(self, request, *args, **kwargs):
        incidencia = self.get_incidencia()
        if (
            request.POST.get("token") != request.session.get(self.clave_token())
            or incidencia.advertencia_generada_id
        ):
            messages.warning(
                request,
                "Esta conversión ya fue registrada y no se volvió a guardar.",
            )
            return redirect("transportistas:incidencias_detalle", pk=incidencia.pk)

        advertencia = Advertencia(
            transportista=incidencia.transportista,
            fecha=incidencia.fecha,
            descripcion=incidencia.descripcion,
            asignacion=incidencia.asignacion,
        )
        if request.user.is_authenticated:
            advertencia.registrado_por = request.user
        advertencia.full_clean()
        advertencia.save()
        request.session.pop(self.clave_token(), None)

        incidencia.advertencia_generada = advertencia
        incidencia.estado_revision = EstadoRevision.REVISADA
        incidencia.save(update_fields=["advertencia_generada", "estado_revision"])
        auditar(
            usuario=request.user,
            accion=TipoAccion.ADVERTENCIA,
            entidad="advertencia",
            entidad_id=advertencia.pk,
            resumen=f"Desde incidencia #{incidencia.pk} a {incidencia.transportista.nombre}.",
        )

        from .forms import AdvertenciaForm
        from .models import Transportista

        aviso = AdvertenciaForm(transportista=incidencia.transportista).aviso_acumulado()
        transportista = Transportista.objects.get(pk=incidencia.transportista_id)
        if transportista.esta_de_baja or transportista.esta_baja_pendiente:
            messages.warning(request, aviso)
        else:
            messages.success(request, aviso)
        return redirect("transportistas:incidencias_detalle", pk=incidencia.pk)


class VincularReemplazoView(IncidenciaMixin, PermisoRequeridoMixin, FormView):
    """Vincula la nueva asignación que cubre el reemplazo, verificándola."""

    permiso_requerido = "transportistas.add_advertencia"
    form_class = VincularReemplazoForm
    template_name = "transportistas/incidencias/vincular.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["incidencia"] = self.get_incidencia()
        return kwargs

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["incidencia"] = self.get_incidencia()
        contexto["titulo"] = "Vincular reemplazo"
        return contexto

    def form_valid(self, form):
        incidencia = self.get_incidencia()
        nueva = form.cleaned_data["nueva_asignacion"]
        incidencia.nueva_asignacion = nueva
        incidencia.transportista_reemplazo = nueva.transportista
        incidencia.save(update_fields=["nueva_asignacion", "transportista_reemplazo"])
        auditar(
            usuario=self.request.user,
            accion=TipoAccion.ACTUALIZAR,
            entidad="incidencia",
            entidad_id=incidencia.pk,
            resumen=f"Reemplazo vinculado: {nueva.transportista.nombre} en {nueva.oferta.codigo}.",
        )
        messages.success(
            self.request,
            f"Reemplazo vinculado: {nueva.transportista.nombre} continúa el servicio "
            f"en la asignación {nueva.oferta.codigo}. La asignación original se conserva.",
        )
        return redirect("transportistas:incidencias_detalle", pk=incidencia.pk)

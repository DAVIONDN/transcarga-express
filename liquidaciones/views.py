"""Vistas de formatos semanales y liquidaciones.

Las acciones financieras exigen su permiso en el servidor (GET y POST):
generar y firmar formatos, generar y cerrar liquidaciones (Operador y
Administrador) y configurar parámetros (solo Administrador). Consulta solo lee.
"""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import DetailView, FormView, ListView, UpdateView, View

from asignaciones.models import Asignacion
from auditoria.models import TipoAccion, auditar
from comun import fechas
from comun.permisos import PermisoRequeridoMixin

from . import calculos
from .forms import FirmarFormatoForm, ParametrosForm
from .models import EstadoFormato, EstadoLiquidacion, FormatoSemanal, Liquidacion, ParametrosLiquidacion


class FormatoMixin:
    def get_formato(self):
        if not hasattr(self, "_formato"):
            self._formato = get_object_or_404(
                FormatoSemanal.objects.select_related(
                    "asignacion", "asignacion__oferta", "asignacion__transportista"
                ),
                pk=self.kwargs["pk"],
            )
        return self._formato


class LiquidacionMixin:
    def get_liquidacion(self):
        if not hasattr(self, "_liquidacion"):
            self._liquidacion = get_object_or_404(
                Liquidacion.objects.select_related(
                    "formato",
                    "formato__asignacion",
                    "formato__asignacion__oferta",
                    "formato__asignacion__transportista",
                ),
                pk=self.kwargs["pk"],
            )
        return self._liquidacion


class ListaFormatosView(PermisoRequeridoMixin, ListView):
    permiso_requerido = "liquidaciones.view_formatosemanal"
    model = FormatoSemanal
    template_name = "liquidaciones/formatos_lista.html"
    context_object_name = "formatos"
    paginate_by = 15

    FILTROS_ESTADO = (
        ("", "Todos"),
        ("pendiente", "Pendientes (incluye atrasados)"),
        ("atrasado", "Atrasados"),
        ("presentado", "Presentados"),
        ("regularizado", "Regularizados"),
        ("liquidado", "Liquidados"),
    )

    def get_queryset(self):
        consulta = super().get_queryset().select_related(
            "asignacion", "asignacion__oferta", "asignacion__transportista"
        )
        texto = (self.request.GET.get("q") or "").strip()
        if texto:
            consulta = consulta.filter(
                Q(asignacion__oferta__codigo__icontains=texto)
                | Q(asignacion__transportista__nombre__icontains=texto)
                | Q(asignacion__transportista__placa__icontains=texto)
            )
        estado = self.request.GET.get("estado", "")
        if estado == "atrasado":
            consulta = consulta.filter(
                estado=EstadoFormato.PENDIENTE, fecha_prevista__lt=fechas.hoy()
            )
        elif estado:
            consulta = consulta.filter(estado=estado.upper())
        return consulta

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Formatos semanales"
        contexto["filtros_estado"] = self.FILTROS_ESTADO
        contexto["filtros"] = {
            "q": self.request.GET.get("q", ""),
            "estado": self.request.GET.get("estado", ""),
        }
        contexto["hay_filtros"] = any(contexto["filtros"].values())
        return contexto


class GenerarFormatosView(PermisoRequeridoMixin, View):
    """Genera los formatos semanales de una asignación (idempotente)."""

    permiso_requerido = "liquidaciones.generar_formatos"
    template_name = "liquidaciones/formatos_generar.html"

    def get_asignacion(self):
        return get_object_or_404(
            Asignacion.objects.select_related("oferta", "transportista"),
            pk=self.kwargs["asignacion_pk"],
        )

    def _pendientes(self, asignacion):
        existentes = set(
            asignacion.formatos.values_list("periodo_inicio", flat=True)
        )
        return [
            semana
            for semana in calculos.semanas_servicio(
                asignacion.fecha_inicio, asignacion.fecha_fin
            )
            if semana[0] not in existentes
        ]

    def get(self, request, *args, **kwargs):
        asignacion = self.get_asignacion()
        return render(
            request,
            self.template_name,
            {
                "asignacion": asignacion,
                "titulo": f"Generar formatos de {asignacion.oferta.codigo}",
                "semanas": self._pendientes(asignacion),
            },
        )

    def post(self, request, *args, **kwargs):
        asignacion = self.get_asignacion()
        creados = 0
        with transaction.atomic():
            for lunes, domingo, viernes in self._pendientes(asignacion):
                _, creado = FormatoSemanal.objects.get_or_create(
                    asignacion=asignacion,
                    periodo_inicio=lunes,
                    defaults={
                        "periodo_fin": domingo,
                        "fecha_prevista": viernes,
                    },
                )
                creados += int(creado)
        auditar(
            usuario=request.user,
            accion=TipoAccion.FORMATO,
            entidad="asignacion",
            entidad_id=asignacion.pk,
            resumen=f"Generados {creados} formato(s) de {asignacion.oferta.codigo}.",
        )
        if creados:
            messages.success(request, f"Se generaron {creados} formato(s) semanal(es).")
        else:
            messages.info(request, "No había semanas nuevas: todo ya estaba generado.")
        return redirect("liquidaciones:formatos_lista")


class DetalleFormatoView(FormatoMixin, PermisoRequeridoMixin, DetailView):
    permiso_requerido = "liquidaciones.view_formatosemanal"
    model = FormatoSemanal
    template_name = "liquidaciones/formato_detalle.html"
    context_object_name = "formato"

    def get_object(self, queryset=None):
        return self.get_formato()

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = f"Formato semanal {self.object}"
        return contexto


class FirmarFormatoView(FormatoMixin, PermisoRequeridoMixin, FormView):
    permiso_requerido = "liquidaciones.firmar_formato"
    form_class = FirmarFormatoForm
    template_name = "liquidaciones/formato_firmar.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["formato"] = self.get_formato()
        contexto["titulo"] = f"Firmar formato {self.get_formato()}"
        return contexto

    def form_valid(self, form):
        formato = self.get_formato()
        try:
            estado = formato.firmar(form.cleaned_data["fecha_firma"])
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        if estado == EstadoFormato.REGULARIZADO:
            messages.warning(
                self.request,
                f"Formato regularizado con {formato.semanas_retraso} semana(s) de retraso. "
                "La penalidad se calcula al liquidar.",
            )
        else:
            messages.success(self.request, "Formato firmado dentro del plazo.")
        auditar(
            usuario=self.request.user,
            accion=TipoAccion.FORMATO,
            entidad="formato",
            entidad_id=formato.pk,
            resumen=f"Firma {formato.fecha_firma} ({formato.get_estado_display().lower()}).",
        )
        return redirect("liquidaciones:formato_detalle", pk=formato.pk)


class ListaLiquidacionesView(PermisoRequeridoMixin, ListView):
    permiso_requerido = "liquidaciones.view_liquidacion"
    model = Liquidacion
    template_name = "liquidaciones/liquidaciones_lista.html"
    context_object_name = "liquidaciones"
    paginate_by = 15

    def get_queryset(self):
        consulta = super().get_queryset().select_related(
            "formato",
            "formato__asignacion",
            "formato__asignacion__oferta",
            "formato__asignacion__transportista",
        )
        texto = (self.request.GET.get("q") or "").strip()
        if texto:
            consulta = consulta.filter(
                Q(formato__asignacion__oferta__codigo__icontains=texto)
                | Q(formato__asignacion__transportista__nombre__icontains=texto)
            )
        estado = self.request.GET.get("estado", "")
        if estado:
            consulta = consulta.filter(estado=estado.upper())
        return consulta

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Liquidaciones"
        contexto["filtros"] = {
            "q": self.request.GET.get("q", ""),
            "estado": self.request.GET.get("estado", ""),
        }
        contexto["hay_filtros"] = any(contexto["filtros"].values())
        return contexto


class DetalleLiquidacionView(LiquidacionMixin, PermisoRequeridoMixin, DetailView):
    permiso_requerido = "liquidaciones.view_liquidacion"
    model = Liquidacion
    template_name = "liquidaciones/liquidacion_detalle.html"
    context_object_name = "liquidacion"

    def get_object(self, queryset=None):
        return self.get_liquidacion()

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = f"Liquidación {self.object.formato}"
        contexto["parametros"] = ParametrosLiquidacion.obtener()
        return contexto


class GenerarLiquidacionView(FormatoMixin, PermisoRequeridoMixin, View):
    """Crea o reprocesa el borrador de un formato firmado (nunca duplica)."""

    permiso_requerido = "liquidaciones.generar_liquidacion"
    template_name = "liquidaciones/confirmar.html"

    def get(self, request, *args, **kwargs):
        formato = self.get_formato()
        return render(
            request,
            self.template_name,
            {"formato": formato, "titulo": f"Liquidar {formato}"},
        )

    def post(self, request, *args, **kwargs):
        formato = self.get_formato()
        if not formato.esta_firmado:
            messages.error(
                request,
                "No se puede liquidar: el formato obligatorio está pendiente de firma.",
            )
            return redirect("liquidaciones:formato_detalle", pk=formato.pk)
        liquidacion, creada = Liquidacion.objects.get_or_create(formato=formato)
        try:
            liquidacion.recalcular()
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
            return redirect("liquidaciones:formato_detalle", pk=formato.pk)
        messages.success(
            request,
            "Borrador creado." if creada else "Borrador reprocesado sin duplicar importes.",
        )
        auditar(
            usuario=request.user,
            accion=TipoAccion.LIQUIDACION,
            entidad="liquidacion",
            entidad_id=liquidacion.pk,
            resumen=f"Borrador {'creado' if creada else 'reprocesado'} de {formato} (S/ {liquidacion.total}).",
        )
        return redirect("liquidaciones:liquidacion_detalle", pk=liquidacion.pk)


class CerrarLiquidacionView(LiquidacionMixin, PermisoRequeridoMixin, View):
    permiso_requerido = "liquidaciones.cerrar_liquidacion"
    template_name = "liquidaciones/confirmar.html"

    def get(self, request, *args, **kwargs):
        liquidacion = self.get_liquidacion()
        return render(
            request,
            self.template_name,
            {
                "liquidacion": liquidacion,
                "titulo": f"Cerrar {liquidacion.formato}",
                "parametros": ParametrosLiquidacion.obtener(),
            },
        )

    def post(self, request, *args, **kwargs):
        liquidacion = self.get_liquidacion()
        try:
            liquidacion.cerrar()
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
            return redirect("liquidaciones:liquidacion_detalle", pk=liquidacion.pk)
        messages.success(request, "Liquidación cerrada. Ya no admite cambios.")
        auditar(
            usuario=request.user,
            accion=TipoAccion.LIQUIDACION,
            entidad="liquidacion",
            entidad_id=liquidacion.pk,
            resumen=f"Cerrada {liquidacion.formato} por S/ {liquidacion.total}.",
        )
        return redirect("liquidaciones:liquidacion_detalle", pk=liquidacion.pk)


class ConfigurarParametrosView(PermisoRequeridoMixin, UpdateView):
    permiso_requerido = "liquidaciones.configurar_liquidacion"
    model = ParametrosLiquidacion
    form_class = ParametrosForm
    template_name = "liquidaciones/parametros.html"

    def get_object(self, queryset=None):
        return ParametrosLiquidacion.obtener()

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Parámetros financieros"
        return contexto

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        auditar(
            usuario=self.request.user,
            accion=TipoAccion.ACTUALIZAR,
            entidad="parametros_liquidacion",
            entidad_id=self.object.pk,
            resumen="Parámetros financieros actualizados.",
        )
        messages.success(self.request, "Parámetros financieros actualizados.")
        return respuesta

    def get_success_url(self):
        return reverse("liquidaciones:liquidaciones_lista")

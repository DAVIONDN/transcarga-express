"""Vistas de asignaciones.

Flujo de alta en dos pasos: se eligen oferta y transportista, se muestra un resumen
con la empresa cliente, el transportista y el vehículo, y recién al confirmar se crea
la asignación (con las reglas revalidadas en el servidor dentro de una transacción).
"""

from datetime import date

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import DetailView, FormView, ListView, View

from auditoria.models import TipoAccion, auditar
from comun.choices import EstadoAsignacion, EstadoOferta
from comun.permisos import PermisoRequeridoMixin
from ofertas.models import OfertaCarga
from transportistas.models import Transportista

from . import reglas
from .forms import (
    AsignacionForm,
    CancelarAsignacionForm,
    FinalizarAsignacionForm,
)
from .models import Asignacion

CLAVE_SESION = "asignacion_pendiente"


class ListaAsignacionesView(PermisoRequeridoMixin, ListView):
    permiso_requerido = "asignaciones.view_asignacion"
    model = Asignacion
    template_name = "asignaciones/lista.html"
    context_object_name = "asignaciones"
    paginate_by = 10

    def get_queryset(self):
        consulta = super().get_queryset().select_related(
            "oferta", "oferta__empresa_cliente", "transportista"
        )
        estado = self.request.GET.get("estado")
        if estado:
            consulta = consulta.filter(estado=estado)
        return consulta

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Asignaciones"
        contexto["estados"] = EstadoAsignacion.choices
        contexto["estado_filtro"] = self.request.GET.get("estado", "")
        contexto["total_asignaciones"] = Asignacion.objects.count()
        contexto["conteos"] = [
            {
                "valor": valor,
                "etiqueta": etiqueta,
                "total": Asignacion.objects.filter(estado=valor).count(),
            }
            for valor, etiqueta in EstadoAsignacion.choices
        ]
        return contexto


class DetalleAsignacionView(PermisoRequeridoMixin, DetailView):
    permiso_requerido = "asignaciones.view_asignacion"
    model = Asignacion
    template_name = "asignaciones/detalle.html"
    context_object_name = "asignacion"

    def get_queryset(self):
        return super().get_queryset().select_related(
            "oferta", "oferta__empresa_cliente", "transportista"
        )

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        asignacion = self.object
        contexto["titulo"] = f"Asignación de la oferta {asignacion.oferta.codigo}"
        contexto["advertencias"] = asignacion.advertencias.select_related("transportista")
        contexto["formatos"] = asignacion.formatos.order_by("periodo_inicio", "id")
        return contexto


class AsignacionCrearView(PermisoRequeridoMixin, FormView):
    """Paso 1: elegir una oferta Disponible y un transportista compatible."""

    permiso_requerido = "asignaciones.add_asignacion"
    form_class = AsignacionForm
    template_name = "asignaciones/formulario.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Nueva asignación"
        contexto["texto_boton"] = "Revisar y confirmar"
        contexto["ofertas_disponibles"] = (
            OfertaCarga.objects.filter(estado=EstadoOferta.DISPONIBLE)
            .select_related("empresa_cliente")
            .order_by("-creado", "-id")
        )
        return contexto

    def form_valid(self, form):
        oferta = form.oferta_seleccionada
        self.request.session[CLAVE_SESION] = {
            "oferta_id": oferta.pk,
            "transportista_id": form.cleaned_data["transportista"].pk,
            "fecha_inicio": form.cleaned_data["fecha_inicio"].isoformat(),
            "fecha_fin": (
                form.cleaned_data["fecha_fin"].isoformat()
                if form.cleaned_data["fecha_fin"]
                else None
            ),
        }
        return redirect("asignaciones:confirmar")


class ConfirmarAsignacionView(PermisoRequeridoMixin, View):
    """Paso 2: resumen de la operación y creación efectiva de la asignación."""

    permiso_requerido = "asignaciones.add_asignacion"
    template_name = "asignaciones/confirmar.html"

    def seleccion(self):
        """Recupera la selección guardada en la sesión, o None si ya no es válida."""
        pendiente = self.request.session.get(CLAVE_SESION)
        if not pendiente:
            return None
        oferta = (
            OfertaCarga.objects.filter(pk=pendiente["oferta_id"])
            .select_related("empresa_cliente")
            .first()
        )
        transportista = Transportista.objects.filter(pk=pendiente["transportista_id"]).first()
        if oferta is None or transportista is None:
            return None
        return {
            "oferta": oferta,
            "transportista": transportista,
            "fecha_inicio": date.fromisoformat(pendiente["fecha_inicio"]),
            "fecha_fin": (
                date.fromisoformat(pendiente["fecha_fin"]) if pendiente["fecha_fin"] else None
            ),
        }

    def get(self, request, *args, **kwargs):
        seleccion = self.seleccion()
        if seleccion is None:
            messages.warning(
                request,
                "No hay una asignación pendiente de confirmar. Elija una oferta disponible y un "
                "transportista compatible.",
            )
            return redirect("asignaciones:nueva")
        return render(
            request,
            self.template_name,
            {
                "titulo": "Confirmar asignación",
                **seleccion,
                "motivos": reglas.motivos_no_elegibilidad(
                    seleccion["transportista"],
                    seleccion["oferta"],
                    fecha_referencia=seleccion["fecha_inicio"],
                ),
            },
        )

    def post(self, request, *args, **kwargs):
        seleccion = self.seleccion()
        if seleccion is None:
            request.session.pop(CLAVE_SESION, None)
            messages.warning(
                request,
                "La selección ya no está disponible. Vuelva a elegir la oferta y el "
                "transportista.",
            )
            return redirect("asignaciones:nueva")

        try:
            # Vuelve a validar las reglas y crea la asignación en una sola transacción.
            asignacion = reglas.crear_asignacion(**seleccion)
        except ValidationError as error:
            request.session.pop(CLAVE_SESION, None)
            messages.error(request, " ".join(error.messages))
            return redirect("asignaciones:nueva")

        request.session.pop(CLAVE_SESION, None)
        auditar(
            usuario=request.user,
            accion=TipoAccion.ASIGNAR,
            entidad="asignacion",
            entidad_id=asignacion.pk,
            resumen=f"{asignacion.oferta.codigo} → {asignacion.transportista.nombre}.",
        )
        messages.success(
            request,
            f"Asignación registrada: la oferta {asignacion.oferta.codigo} quedó Cubierta y "
            f"{asignacion.transportista.nombre} tiene ahora una asignación activa.",
        )
        return redirect("asignaciones:detalle", pk=asignacion.pk)


class AsignacionMixin:
    """Obtiene la asignación indicada en la URL."""

    def get_asignacion(self):
        if not hasattr(self, "_asignacion"):
            self._asignacion = get_object_or_404(
                Asignacion.objects.select_related("oferta", "transportista"), pk=self.kwargs["pk"]
            )
        return self._asignacion


class FinalizarAsignacionView(AsignacionMixin, PermisoRequeridoMixin, FormView):
    """Confirmación y aplicación de la finalización (la oferta sigue Cubierta)."""

    permiso_requerido = "asignaciones.finalizar_asignacion"
    form_class = FinalizarAsignacionForm
    template_name = "asignaciones/finalizar.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["asignacion"] = self.get_asignacion()
        return kwargs

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["asignacion"] = self.get_asignacion()
        contexto["titulo"] = f"Finalizar la asignación {self.get_asignacion().oferta.codigo}"
        return contexto

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not self.get_asignacion().esta_activa:
            messages.info(request, "La asignación no está activa: ya fue finalizada o cancelada.")
            return redirect("asignaciones:detalle", pk=self.get_asignacion().pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        asignacion = self.get_asignacion()
        asignacion.finalizar(form.cleaned_data["fecha_fin"])
        auditar(
            usuario=self.request.user,
            accion=TipoAccion.FINALIZAR,
            entidad="asignacion",
            entidad_id=asignacion.pk,
            resumen=f"Finalizada {asignacion.oferta.codigo}; oferta Cubierta.",
        )
        messages.success(
            self.request,
            "Asignación finalizada. El transportista queda libre para otra asignación y la oferta "
            f"{asignacion.oferta.codigo} permanece Cubierta, porque ya representa una carga "
            "asignada.",
        )
        return redirect("asignaciones:detalle", pk=asignacion.pk)


class CancelarAsignacionView(AsignacionMixin, PermisoRequeridoMixin, FormView):
    """Confirmación y aplicación de la cancelación, sin borrar el historial."""

    permiso_requerido = "asignaciones.cancelar_asignacion"
    form_class = CancelarAsignacionForm
    template_name = "asignaciones/cancelar.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["asignacion"] = self.get_asignacion()
        return kwargs

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["asignacion"] = self.get_asignacion()
        contexto["titulo"] = f"Cancelar la asignación {self.get_asignacion().oferta.codigo}"
        return contexto

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not self.get_asignacion().esta_activa:
            messages.info(request, "La asignación no está activa: ya fue finalizada o cancelada.")
            return redirect("asignaciones:detalle", pk=self.get_asignacion().pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        asignacion = self.get_asignacion()
        asignacion.cancelar(form.cleaned_data["fecha"], motivo=form.cleaned_data["motivo"])
        auditar(
            usuario=self.request.user,
            accion=TipoAccion.CANCELAR,
            entidad="asignacion",
            entidad_id=asignacion.pk,
            resumen=f"Cancelada {asignacion.oferta.codigo}: {asignacion.motivo_cancelacion[:120]}",
        )
        messages.warning(
            self.request,
            "Asignación cancelada: queda registrada en el historial como «Cancelada». La oferta "
            f"{asignacion.oferta.codigo} permanece Cubierta y el transportista queda libre para "
            "otra asignación.",
        )
        return redirect("asignaciones:detalle", pk=asignacion.pk)

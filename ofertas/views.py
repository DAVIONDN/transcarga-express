"""Vistas de ofertas de carga, incluida la asignación de un transportista."""

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import CreateView, DetailView, FormView, ListView, UpdateView

from asignaciones import reglas
from asignaciones.forms import AsignacionForm
from auditoria.models import TipoAccion, auditar
from clientes.models import EmpresaCliente
from comun.choices import EstadoOferta, NivelCarga, TipoVehiculo
from comun.permisos import PermisoRequeridoMixin

from .forms import CambiarEstadoOfertaForm, OfertaCargaForm
from .models import OfertaCarga


class ListaOfertasView(PermisoRequeridoMixin, ListView):
    permiso_requerido = "ofertas.view_ofertacarga"
    model = OfertaCarga
    template_name = "ofertas/lista.html"
    context_object_name = "ofertas"
    paginate_by = 10

    def get_queryset(self):
        consulta = super().get_queryset().select_related("empresa_cliente")
        texto = (self.request.GET.get("q") or "").strip()
        if texto:
            consulta = consulta.filter(
                Q(codigo__icontains=texto)
                | Q(origen__icontains=texto)
                | Q(destino__icontains=texto)
                | Q(empresa_cliente__razon_social__icontains=texto)
            )
        estado = self.request.GET.get("estado")
        if estado:
            consulta = consulta.filter(estado=estado)
        nivel = self.request.GET.get("nivel")
        if nivel and nivel.isdigit():
            consulta = consulta.filter(nivel_requerido=int(nivel))
        tipo = self.request.GET.get("tipo")
        if tipo:
            consulta = consulta.filter(tipo_vehiculo_requerido=tipo)
        empresa = self.request.GET.get("empresa")
        if empresa and empresa.isdigit():
            consulta = consulta.filter(empresa_cliente_id=int(empresa))
        return consulta

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Ofertas de carga"
        contexto["estados"] = EstadoOferta.choices
        contexto["niveles"] = NivelCarga.choices
        contexto["tipos_vehiculo"] = TipoVehiculo.choices
        contexto["empresas"] = EmpresaCliente.objects.order_by("razon_social")
        contexto["filtros"] = {
            "q": self.request.GET.get("q", ""),
            "estado": self.request.GET.get("estado", ""),
            "nivel": self.request.GET.get("nivel", ""),
            "tipo": self.request.GET.get("tipo", ""),
            "empresa": self.request.GET.get("empresa", ""),
        }
        contexto["hay_filtros"] = any(contexto["filtros"].values())
        return contexto


class DetalleOfertaView(PermisoRequeridoMixin, DetailView):
    permiso_requerido = "ofertas.view_ofertacarga"
    model = OfertaCarga
    template_name = "ofertas/detalle.html"
    context_object_name = "oferta"

    def get_queryset(self):
        return super().get_queryset().select_related("empresa_cliente")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        oferta = self.object
        contexto["titulo"] = f"Oferta {oferta.codigo}"
        contexto["asignacion"] = getattr(oferta, "asignacion", None)
        if oferta.esta_disponible:
            contexto["candidatos"] = reglas.candidatos(oferta)
            contexto["elegibles"] = [c for c in contexto["candidatos"] if c["elegible"]]
        return contexto


class CrearOfertaView(PermisoRequeridoMixin, CreateView):
    permiso_requerido = "ofertas.add_ofertacarga"
    model = OfertaCarga
    form_class = OfertaCargaForm
    template_name = "ofertas/formulario.html"

    def get_initial(self):
        inicial = super().get_initial()
        empresa = self.request.GET.get("empresa")
        if empresa and empresa.isdigit():
            inicial["empresa_cliente"] = EmpresaCliente.objects.filter(pk=int(empresa)).first()
        return inicial

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Nueva oferta de carga"
        contexto["texto_boton"] = "Registrar oferta"
        return contexto

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        auditar(
            usuario=self.request.user,
            accion=TipoAccion.CREAR,
            entidad="oferta",
            entidad_id=self.object.pk,
            resumen=f"Oferta {self.object.codigo} de {self.object.empresa_cliente.razon_social}.",
        )
        messages.success(
            self.request, f"Oferta registrada correctamente con el código {self.object.codigo}."
        )
        return respuesta

    def get_success_url(self):
        return reverse("ofertas:detalle", args=[self.object.pk])


class EditarOfertaView(PermisoRequeridoMixin, UpdateView):
    permiso_requerido = "ofertas.change_ofertacarga"
    model = OfertaCarga
    form_class = OfertaCargaForm
    template_name = "ofertas/formulario.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = f"Editar oferta {self.object.codigo}"
        contexto["texto_boton"] = "Guardar cambios"
        return contexto

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        auditar(
            usuario=self.request.user,
            accion=TipoAccion.ACTUALIZAR,
            entidad="oferta",
            entidad_id=self.object.pk,
            resumen=f"Edición de la oferta {self.object.codigo}.",
        )
        messages.success(self.request, "Cambios guardados correctamente.")
        return respuesta

    def get_success_url(self):
        return reverse("ofertas:detalle", args=[self.object.pk])


class CambiarEstadoOfertaView(PermisoRequeridoMixin, FormView):
    """Confirmación y aplicación del cambio de estado de una oferta.

    El estado no se edita desde el formulario de datos: se cambia aquí, con una
    pantalla de confirmación que explica las consecuencias.
    """

    permiso_requerido = "ofertas.cambiar_estado_oferta"
    form_class = CambiarEstadoOfertaForm
    template_name = "ofertas/cambiar_estado.html"

    def get_oferta(self):
        if not hasattr(self, "_oferta"):
            self._oferta = get_object_or_404(
                OfertaCarga.objects.select_related("empresa_cliente"), pk=self.kwargs["pk"]
            )
        return self._oferta

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["oferta"] = self.get_oferta()
        return kwargs

    def get_initial(self):
        return {"estado": self.get_oferta().estado}

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        oferta = self.get_oferta()
        contexto["oferta"] = oferta
        contexto["titulo"] = f"Cambiar estado de la oferta {oferta.codigo}"
        contexto["asignacion"] = getattr(oferta, "asignacion", None)
        return contexto

    def form_valid(self, form):
        oferta = self.get_oferta()
        oferta.estado = form.cleaned_data["estado"]
        oferta.save(update_fields=["estado", "actualizado"])
        auditar(
            usuario=self.request.user,
            accion=TipoAccion.CAMBIAR_ESTADO,
            entidad="oferta",
            entidad_id=oferta.pk,
            resumen=f"Cambio de estado a «{oferta.get_estado_display()}».",
        )
        messages.success(
            self.request,
            f"La oferta {oferta.codigo} pasó a estado «{oferta.get_estado_display()}».",
        )
        if oferta.estado == EstadoOferta.CUBIERTA:
            messages.info(
                self.request, "Mientras esté Cubierta no admitirá nuevas asignaciones."
            )
        else:
            messages.info(
                self.request, "La oferta vuelve a admitir asignaciones de transportistas."
            )
        return redirect("ofertas:detalle", pk=oferta.pk)


class AsignarOfertaView(PermisoRequeridoMixin, FormView):
    """Asigna un transportista a la oferta indicada (reglas R5, R6 y R11)."""

    permiso_requerido = "asignaciones.add_asignacion"
    form_class = AsignacionForm
    template_name = "ofertas/asignar.html"

    def get_oferta(self):
        if not hasattr(self, "_oferta"):
            self._oferta = get_object_or_404(
                OfertaCarga.objects.select_related("empresa_cliente"), pk=self.kwargs["pk"]
            )
        return self._oferta

    def get(self, request, *args, **kwargs):
        oferta = self.get_oferta()
        if oferta.esta_cubierta:
            messages.error(
                request,
                f"La oferta {oferta.codigo} ya está cubierta: una oferta cubierta no puede "
                "recibir otra asignación.",
            )
            return redirect("ofertas:detalle", pk=oferta.pk)
        return super().get(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["oferta"] = self.get_oferta()
        return kwargs

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        oferta = self.get_oferta()
        contexto["oferta"] = oferta
        contexto["titulo"] = f"Asignar transportista a la oferta {oferta.codigo}"
        candidatos = reglas.candidatos(oferta)
        contexto["candidatos"] = candidatos
        contexto["elegibles"] = [c for c in candidatos if c["elegible"]]
        return contexto

    def form_valid(self, form):
        """Guarda la selección y pasa a la pantalla de confirmación de la asignación."""
        oferta = self.get_oferta()
        self.request.session["asignacion_pendiente"] = {
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

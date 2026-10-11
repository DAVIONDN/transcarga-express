"""Vistas de empresas clientes. Todas exigen sesión iniciada (R14)."""

from django.contrib import messages
from django.db.models import Count, Q
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from auditoria.models import TipoAccion, auditar
from comun.permisos import PermisoRequeridoMixin

from .forms import EmpresaClienteForm
from .models import EmpresaCliente


class ListaClientesView(PermisoRequeridoMixin, ListView):
    permiso_requerido = "clientes.view_empresacliente"
    model = EmpresaCliente
    template_name = "clientes/lista.html"
    context_object_name = "empresas"
    paginate_by = 10

    def get_queryset(self):
        consulta = super().get_queryset()
        texto = (self.request.GET.get("q") or "").strip()
        if texto:
            consulta = consulta.filter(
                Q(razon_social__icontains=texto)
                | Q(ruc__icontains=texto)
                | Q(actividad_economica__icontains=texto)
            )
        consulta = consulta.annotate(total_ofertas=Count("ofertas", distinct=True)).order_by(
            "razon_social"
        )
        # Filtro útil: empresas que ya tienen ofertas registradas y las que aún no.
        filtro_ofertas = self.request.GET.get("ofertas")
        if filtro_ofertas == "con":
            consulta = consulta.filter(total_ofertas__gt=0)
        elif filtro_ofertas == "sin":
            consulta = consulta.filter(total_ofertas=0)
        return consulta

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Empresas clientes"
        contexto["texto_busqueda"] = self.request.GET.get("q", "")
        contexto["filtro_ofertas"] = self.request.GET.get("ofertas", "")
        contexto["hay_filtros"] = bool(contexto["texto_busqueda"] or contexto["filtro_ofertas"])
        return contexto


class DetalleClienteView(PermisoRequeridoMixin, DetailView):
    permiso_requerido = "clientes.view_empresacliente"
    model = EmpresaCliente
    template_name = "clientes/detalle.html"
    context_object_name = "empresa"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = self.object.razon_social
        contexto["ofertas"] = self.object.ofertas.select_related("asignacion").order_by("-creado")
        return contexto


class CrearClienteView(PermisoRequeridoMixin, CreateView):
    permiso_requerido = "clientes.add_empresacliente"
    model = EmpresaCliente
    form_class = EmpresaClienteForm
    template_name = "clientes/formulario.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Nueva empresa cliente"
        contexto["texto_boton"] = "Registrar empresa"
        return contexto

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        auditar(
            usuario=self.request.user,
            accion=TipoAccion.CREAR,
            entidad="empresa_cliente",
            entidad_id=self.object.pk,
            resumen=f"Alta de {self.object.razon_social} (RUC {self.object.ruc}).",
        )
        messages.success(self.request, "Empresa cliente registrada correctamente.")
        return respuesta

    def get_success_url(self):
        return reverse("clientes:detalle", args=[self.object.pk])


class EditarClienteView(PermisoRequeridoMixin, UpdateView):
    permiso_requerido = "clientes.change_empresacliente"
    model = EmpresaCliente
    form_class = EmpresaClienteForm
    template_name = "clientes/formulario.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = f"Editar empresa cliente: {self.object.razon_social}"
        contexto["texto_boton"] = "Guardar cambios"
        return contexto

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        auditar(
            usuario=self.request.user,
            accion=TipoAccion.ACTUALIZAR,
            entidad="empresa_cliente",
            entidad_id=self.object.pk,
            resumen=f"Edición de {self.object.razon_social}.",
        )
        messages.success(self.request, "Cambios guardados correctamente.")
        return respuesta

    def get_success_url(self):
        return reverse("clientes:detalle", args=[self.object.pk])

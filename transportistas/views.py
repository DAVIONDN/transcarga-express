"""Vistas de transportistas. Todas exigen sesión iniciada (R14)."""

import secrets
from datetime import timedelta

from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import CreateView, DetailView, FormView, ListView, UpdateView, View

from auditoria.models import TipoAccion, auditar
from comun import fechas
from comun.choices import EstadoTransportista, NivelCarga
from comun.permisos import PermisoRequeridoMixin

from .forms import (
    AdvertenciaForm,
    CambiarEstadoTransportistaForm,
    TransportistaForm,
)
from .models import MAXIMO_ADVERTENCIAS, Advertencia, Transportista


class TransportistaMixin:
    """Obtiene el transportista indicado en la URL."""

    def get_transportista(self):
        if not hasattr(self, "_transportista"):
            self._transportista = get_object_or_404(Transportista, pk=self.kwargs["pk"])
        return self._transportista


class ListaTransportistasView(PermisoRequeridoMixin, ListView):
    """Listado con búsqueda y filtros por estado, nivel y situación documental."""

    permiso_requerido = "transportistas.view_transportista"
    model = Transportista
    template_name = "transportistas/lista.html"
    context_object_name = "transportistas"
    paginate_by = 10

    FILTROS_DOCUMENTO = (
        ("", "Todos"),
        ("vencido", "Con documentos vencidos"),
        ("proximo", "Próximos a vencer (30 días)"),
        ("pendiente", "Con documentos pendientes"),
    )

    def get_queryset(self):
        consulta = super().get_queryset()
        texto = (self.request.GET.get("q") or "").strip()
        if texto:
            consulta = consulta.filter(
                Q(nombre__icontains=texto)
                | Q(numero_documento__icontains=texto)
                | Q(placa__icontains=texto)
            )
        estado = self.request.GET.get("estado")
        if estado:
            consulta = consulta.filter(estado=estado)
        nivel = self.request.GET.get("nivel")
        if nivel and nivel.isdigit():
            consulta = consulta.filter(nivel=int(nivel))
        consulta = self._filtrar_por_documento(consulta)
        return consulta

    def _filtrar_por_documento(self, consulta):
        """Filtra por situación documental calculada contra la fecha actual."""
        filtro = self.request.GET.get("doc", "")
        hoy = fechas.hoy()
        campos = (
            "fecha_vencimiento_licencia",
            "fecha_vencimiento_revision_tecnica",
            "fecha_vencimiento_soat",
        )
        if filtro == "vencido":
            vencido = Q()
            for campo in campos:
                vencido |= Q(**{f"{campo}__lt": hoy})
            return consulta.filter(vencido)
        if filtro == "proximo":
            limite = hoy + timedelta(days=fechas.DIAS_AVISO_VENCIMIENTO)
            proximos = Q()
            for campo in campos:
                proximos |= Q(**{f"{campo}__gte": hoy, f"{campo}__lte": limite})
            vencido = Q()
            for campo in campos:
                vencido |= Q(**{f"{campo}__lt": hoy})
            return consulta.filter(proximos).exclude(vencido)
        if filtro == "pendiente":
            return consulta.filter(fotografia_vehiculo="")
        return consulta

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Transportistas"
        contexto["estados"] = EstadoTransportista.choices
        contexto["niveles"] = NivelCarga.choices
        contexto["filtros_doc"] = self.FILTROS_DOCUMENTO
        contexto["filtros"] = {
            "q": self.request.GET.get("q", ""),
            "estado": self.request.GET.get("estado", ""),
            "nivel": self.request.GET.get("nivel", ""),
            "doc": self.request.GET.get("doc", ""),
        }
        contexto["hay_filtros"] = any(contexto["filtros"].values())
        return contexto


class ListaAdvertenciasView(PermisoRequeridoMixin, ListView):
    """Listado general de advertencias (sección del menú de navegación).

    Permite buscar por descripción o transportista y filtrar por transportista y
    por rango de fechas.
    """

    permiso_requerido = "transportistas.view_advertencia"
    model = Advertencia
    template_name = "transportistas/advertencias_lista.html"
    context_object_name = "advertencias"
    paginate_by = 15

    def get_queryset(self):
        consulta = super().get_queryset().select_related(
            "transportista", "asignacion", "asignacion__oferta", "registrado_por"
        )
        texto = (self.request.GET.get("q") or "").strip()
        if texto:
            consulta = consulta.filter(
                Q(descripcion__icontains=texto)
                | Q(transportista__nombre__icontains=texto)
                | Q(transportista__numero_documento__icontains=texto)
            )
        transportista = self.request.GET.get("transportista")
        if transportista and transportista.isdigit():
            consulta = consulta.filter(transportista_id=int(transportista))
        desde = fechas.interpretar_fecha(self.request.GET.get("desde"))
        if desde:
            consulta = consulta.filter(fecha__gte=desde)
        hasta = fechas.interpretar_fecha(self.request.GET.get("hasta"))
        if hasta:
            consulta = consulta.filter(fecha__lte=hasta)
        return consulta

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Advertencias"
        contexto["transportistas"] = Transportista.objects.order_by("nombre")
        contexto["filtros"] = {
            "q": self.request.GET.get("q", ""),
            "transportista": self.request.GET.get("transportista", ""),
            "desde": self.request.GET.get("desde", ""),
            "hasta": self.request.GET.get("hasta", ""),
        }
        contexto["hay_filtros"] = any(contexto["filtros"].values())
        contexto["total_advertencias"] = self.get_queryset().count()
        contexto["maximo_advertencias"] = MAXIMO_ADVERTENCIAS
        contexto["transportistas_con_advertencias"] = (
            Transportista.objects.annotate(total=Count("advertencias"))
            .filter(total__gt=0)
            .order_by("-total", "nombre")
        )
        return contexto


class DetalleTransportistaView(PermisoRequeridoMixin, DetailView):
    permiso_requerido = "transportistas.view_transportista"
    model = Transportista
    template_name = "transportistas/detalle.html"
    context_object_name = "transportista"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        transportista = self.object
        contexto["titulo"] = transportista.nombre
        contexto["advertencias"] = transportista.advertencias.select_related(
            "asignacion", "registrado_por"
        )
        contexto["incidencias"] = transportista.incidencias.select_related(
            "empresa_cliente", "asignacion", "advertencia_generada", "registrado_por"
        )
        contexto["participaciones"] = transportista.participaciones.select_related("curso")
        contexto["asignaciones"] = transportista.asignaciones.select_related(
            "oferta", "oferta__empresa_cliente"
        )
        contexto["documentos"] = [
            (
                "Licencia de conducir",
                transportista.fecha_vencimiento_licencia,
                transportista.licencia_vigente,
            ),
            (
                "Revisión técnica",
                transportista.fecha_vencimiento_revision_tecnica,
                transportista.revision_tecnica_vigente,
            ),
            ("SOAT", transportista.fecha_vencimiento_soat, transportista.soat_vigente),
        ]
        contexto["documentos_detalle"] = transportista.documentos_detalle()
        contexto["alerta_documental"] = transportista.alerta_documental
        excepcion = transportista.ultima_excepcion_baja()
        contexto["excepcion_baja"] = excepcion
        contexto["puede_aplicar_baja"] = bool(
            transportista.esta_baja_pendiente
            and excepcion is not None
            and (excepcion.asignacion is None or not excepcion.asignacion.esta_activa)
        )
        contexto["maximo_advertencias"] = MAXIMO_ADVERTENCIAS
        contexto["puede_activarse"] = transportista.documentacion_completa
        return contexto


class CrearTransportistaView(PermisoRequeridoMixin, CreateView):
    permiso_requerido = "transportistas.add_transportista"
    model = Transportista
    form_class = TransportistaForm
    template_name = "transportistas/formulario.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Nuevo transportista"
        contexto["texto_boton"] = "Registrar transportista"
        return contexto

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        auditar(
            usuario=self.request.user,
            accion=TipoAccion.CREAR,
            entidad="transportista",
            entidad_id=self.object.pk,
            resumen=f"Alta de {self.object.nombre} ({self.object.placa}).",
        )
        messages.success(
            self.request,
            f"Transportista registrado correctamente. Nivel asignado: "
            f"{self.object.get_nivel_display()}.",
        )
        return respuesta

    def get_success_url(self):
        return reverse("transportistas:detalle", args=[self.object.pk])


class EditarTransportistaView(PermisoRequeridoMixin, UpdateView):
    permiso_requerido = "transportistas.change_transportista"
    model = Transportista
    form_class = TransportistaForm
    template_name = "transportistas/formulario.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = f"Editar transportista: {self.object.nombre}"
        contexto["texto_boton"] = "Guardar cambios"
        return contexto

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        auditar(
            usuario=self.request.user,
            accion=TipoAccion.ACTUALIZAR,
            entidad="transportista",
            entidad_id=self.object.pk,
            resumen=f"Edición de {self.object.nombre} ({self.object.placa}).",
        )
        messages.success(
            self.request,
            f"Cambios guardados. Nivel recalculado: {self.object.get_nivel_display()}.",
        )
        return respuesta

    def get_success_url(self):
        return reverse("transportistas:detalle", args=[self.object.pk])


class CambiarEstadoView(TransportistaMixin, PermisoRequeridoMixin, FormView):
    permiso_requerido = "transportistas.cambiar_estado_transportista"
    form_class = CambiarEstadoTransportistaForm
    template_name = "transportistas/cambiar_estado.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["transportista"] = self.get_transportista()
        return kwargs

    def get_initial(self):
        return {"estado": self.get_transportista().estado}

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        transportista = self.get_transportista()
        contexto["transportista"] = transportista
        contexto["titulo"] = f"Cambiar estado de {transportista.nombre}"
        contexto["puede_activarse"] = transportista.documentacion_completa
        return contexto

    def form_valid(self, form):
        transportista = self.get_transportista()
        transportista.estado = form.cleaned_data["estado"]
        transportista.save(update_fields=["estado", "actualizado"])
        auditar(
            usuario=self.request.user,
            accion=TipoAccion.CAMBIAR_ESTADO,
            entidad="transportista",
            entidad_id=transportista.pk,
            resumen=f"Cambio de estado a «{transportista.get_estado_display()}».",
        )
        messages.success(
            self.request,
            f"El transportista pasó a estado «{transportista.get_estado_display()}».",
        )
        if transportista.estado == EstadoTransportista.EN_RESERVA:
            messages.info(
                self.request, "Mientras esté En Reserva no podrá recibir nuevas asignaciones."
            )
        return redirect("transportistas:detalle", pk=transportista.pk)


class AplicarBajaDiferidaView(TransportistaMixin, PermisoRequeridoMixin, View):
    """Aplica la baja formal diferida por la excepción del cliente, con confirmación.

    Solo procede en estado «Baja pendiente» y con el contrato afectado ya
    terminado; si el servicio sigue en curso, se informa y no se aplica.
    """

    permiso_requerido = "transportistas.cambiar_estado_transportista"
    template_name = "transportistas/aplicar_baja.html"

    def get(self, request, *args, **kwargs):
        transportista = self.get_transportista()
        excepcion = transportista.ultima_excepcion_baja()
        return render(
            request,
            self.template_name,
            {
                "transportista": transportista,
                "excepcion": excepcion,
                "contrato_en_curso": bool(
                    excepcion and excepcion.asignacion and excepcion.asignacion.esta_activa
                ),
                "titulo": f"Aplicar baja formal a {transportista.nombre}",
            },
        )

    def post(self, request, *args, **kwargs):
        transportista = self.get_transportista()
        aplicada, mensaje = transportista.aplicar_baja_diferida()
        auditar(
            usuario=request.user,
            accion=TipoAccion.CAMBIAR_ESTADO,
            entidad="transportista",
            entidad_id=transportista.pk,
            resumen=f"Baja formal {'aplicada' if aplicada else 'rechazada'}: {mensaje}",
        )
        if aplicada:
            messages.warning(request, mensaje)
        else:
            messages.info(request, mensaje)
        return redirect("transportistas:detalle", pk=transportista.pk)


class RegistrarAdvertenciaView(TransportistaMixin, PermisoRequeridoMixin, CreateView):
    """Registra una advertencia con protección contra el doble envío.
    El formulario lleva un token de un solo uso guardado en la sesión: al guardar se
    consume, de modo que un segundo envío del mismo formulario no crea otra advertencia.
    """

    permiso_requerido = "transportistas.add_advertencia"
    model = Advertencia
    form_class = AdvertenciaForm
    template_name = "transportistas/advertencia_form.html"

    def clave_token(self):
        return f"advertencia_token_{self.get_transportista().pk}"

    def token(self):
        """Token de un solo uso que identifica este envío del formulario."""
        if not self.request.session.get(self.clave_token()):
            self.request.session[self.clave_token()] = secrets.token_urlsafe(16)
        return self.request.session[self.clave_token()]

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["transportista"] = self.get_transportista()
        return kwargs

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        transportista = self.get_transportista()
        contexto["transportista"] = transportista
        contexto["titulo"] = f"Registrar advertencia a {transportista.nombre}"
        contexto["maximo_advertencias"] = MAXIMO_ADVERTENCIAS
        contexto["advertencias_actuales"] = transportista.advertencias_total
        contexto["token"] = self.token()
        return contexto

    def form_valid(self, form):
        # El token identifica este envío: si ya se usó, no se registra de nuevo.
        if self.request.POST.get("token") != self.request.session.get(self.clave_token()):
            messages.warning(
                self.request,
                "Esta advertencia ya fue registrada y no se volvió a guardar. Si necesita "
                "registrar otra, abra de nuevo el formulario.",
            )
            return redirect("transportistas:detalle", pk=self.get_transportista().pk)

        advertencia = form.save(commit=False)
        advertencia.transportista = self.get_transportista()
        if self.request.user.is_authenticated:
            advertencia.registrado_por = self.request.user
        advertencia.save()
        self.request.session.pop(self.clave_token(), None)
        self.object = advertencia

        mensaje = form.aviso_acumulado()
        transportista = Transportista.objects.get(pk=advertencia.transportista_id)
        auditar(
            usuario=self.request.user,
            accion=TipoAccion.ADVERTENCIA,
            entidad="advertencia",
            entidad_id=advertencia.pk,
            resumen=f"Advertencia a {transportista.nombre} ({transportista.advertencias_total} de 3).",
        )
        if transportista.esta_de_baja or transportista.esta_baja_pendiente:
            messages.warning(self.request, mensaje)
        else:
            messages.success(self.request, mensaje)
        return redirect("transportistas:detalle", pk=advertencia.transportista_id)

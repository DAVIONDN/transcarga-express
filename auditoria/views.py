"""Historial de auditoría (solo Administrador)."""

from django.db.models import Q
from django.views.generic import ListView

from comun import fechas
from comun.permisos import PermisoRequeridoMixin

from .models import RegistroAuditoria, TipoAccion


class ListaAuditoriaView(PermisoRequeridoMixin, ListView):
    permiso_requerido = "auditoria.ver_auditoria"
    model = RegistroAuditoria
    template_name = "auditoria/lista.html"
    context_object_name = "registros"
    paginate_by = 20

    def get_queryset(self):
        consulta = super().get_queryset().select_related("usuario")
        texto = (self.request.GET.get("q") or "").strip()
        if texto:
            consulta = consulta.filter(
                Q(resumen__icontains=texto)
                | Q(entidad__icontains=texto)
                | Q(usuario__username__icontains=texto)
            )
        accion = self.request.GET.get("accion", "")
        if accion:
            consulta = consulta.filter(accion=accion)
        desde = fechas.interpretar_fecha(self.request.GET.get("desde"))
        if desde:
            consulta = consulta.filter(fecha_hora__date__gte=desde)
        hasta = fechas.interpretar_fecha(self.request.GET.get("hasta"))
        if hasta:
            consulta = consulta.filter(fecha_hora__date__lte=hasta)
        return consulta

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Auditoría de operaciones"
        contexto["acciones"] = TipoAccion.choices
        contexto["filtros"] = {
            "q": self.request.GET.get("q", ""),
            "accion": self.request.GET.get("accion", ""),
            "desde": self.request.GET.get("desde", ""),
            "hasta": self.request.GET.get("hasta", ""),
        }
        contexto["hay_filtros"] = any(contexto["filtros"].values())
        return contexto

"""Vistas del panel de inicio."""

from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.views.generic import TemplateView

from asignaciones.models import Asignacion
from clientes.models import EmpresaCliente
from comun import fechas
from comun.choices import (
    EstadoAsignacion,
    EstadoOferta,
    EstadoTransportista,
    NivelCarga,
)
from liquidaciones.models import EstadoFormato, EstadoLiquidacion, FormatoSemanal, Liquidacion
from ofertas.models import OfertaCarga
from transportistas.models import Advertencia, Transportista


class InicioView(LoginRequiredMixin, TemplateView):
    """Página de inicio: resumen del estado del sistema.

    Todos los indicadores salen de agregaciones del ORM (sin cargar filas de
    más) y cada sección respeta los permisos del usuario.
    """

    template_name = "panel/inicio.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        usuario = self.request.user
        puede = usuario.has_perm
        contexto["permiso_transportistas"] = puede("transportistas.view_transportista")
        contexto["permiso_clientes"] = puede("clientes.view_empresacliente")
        contexto["permiso_ofertas"] = puede("ofertas.view_ofertacarga")
        contexto["permiso_asignaciones"] = puede("asignaciones.view_asignacion")
        contexto["permiso_advertencias"] = puede("transportistas.view_advertencia")
        contexto["permiso_formatos"] = puede("liquidaciones.view_formatosemanal")
        contexto["permiso_liquidaciones"] = puede("liquidaciones.view_liquidacion")
        contexto["titulo"] = "Inicio"
        contexto["hoy"] = fechas.hoy()

        contexto["total_transportistas"] = Transportista.objects.count()
        contexto["transportistas_activos"] = Transportista.objects.filter(
            estado=EstadoTransportista.ACTIVO
        ).count()
        contexto["transportistas_reserva"] = Transportista.objects.filter(
            estado=EstadoTransportista.EN_RESERVA
        ).count()
        contexto["transportistas_baja"] = Transportista.objects.filter(
            estado=EstadoTransportista.BAJA
        ).count()
        contexto["transportistas_baja_pendiente"] = list(
            Transportista.objects.filter(estado=EstadoTransportista.BAJA_PENDIENTE)
            .order_by("nombre")
            .prefetch_related("incidencias", "incidencias__asignacion")
        )
        contexto["total_clientes"] = EmpresaCliente.objects.count()
        contexto["ofertas_disponibles"] = OfertaCarga.objects.filter(
            estado=EstadoOferta.DISPONIBLE
        ).count()
        contexto["ofertas_cubiertas"] = OfertaCarga.objects.filter(
            estado=EstadoOferta.CUBIERTA
        ).count()
        contexto["asignaciones_activas"] = Asignacion.objects.filter(
            estado=EstadoAsignacion.ACTIVA
        ).count()
        contexto["asignaciones_finalizadas"] = Asignacion.objects.filter(
            estado=EstadoAsignacion.FINALIZADA
        ).count()
        contexto["asignaciones_canceladas"] = Asignacion.objects.filter(
            estado=EstadoAsignacion.CANCELADA
        ).count()
        contexto["formatos_pendientes"] = FormatoSemanal.objects.filter(
            estado=EstadoFormato.PENDIENTE
        ).count()
        contexto["formatos_atrasados"] = FormatoSemanal.objects.filter(
            estado=EstadoFormato.PENDIENTE, fecha_prevista__lt=fechas.hoy()
        ).count()
        contexto["liquidaciones_borrador"] = Liquidacion.objects.filter(
            estado=EstadoLiquidacion.BORRADOR
        ).count()
        contexto["advertencias_recientes"] = Advertencia.objects.select_related(
            "transportista"
        )[:5]
        contexto["transportistas_de_baja"] = Transportista.objects.filter(
            estado=EstadoTransportista.BAJA
        ).order_by("nombre")

        totales_nivel = dict(
            Transportista.objects.values("nivel").annotate(total=Count("id")).values_list(
                "nivel", "total"
            )
        )
        contexto["conteo_por_nivel"] = [
            {
                "nivel": nivel,
                "etiqueta": NivelCarga(nivel).label,
                "total": totales_nivel.get(nivel, 0),
            }
            for nivel in (NivelCarga.NIVEL_1, NivelCarga.NIVEL_2, NivelCarga.NIVEL_3)
        ]

        contexto["vencimientos"] = self._vencimientos_proximos()

        # Alertas de SOAT: la vigencia se comprueba al asignar; aquí se avisa al operador.
        operativos = Transportista.objects.exclude(estado=EstadoTransportista.BAJA)
        hoy = fechas.hoy()
        contexto["soat_vencidos"] = [
            {"transportista": transportista, "dias": fechas.dias_para_vencer(transportista.fecha_vencimiento_soat)}
            for transportista in operativos.filter(fecha_vencimiento_soat__lt=hoy).order_by(
                "fecha_vencimiento_soat"
            )
        ]
        contexto["soat_por_vencer"] = [
            {"transportista": transportista, "dias": fechas.dias_para_vencer(transportista.fecha_vencimiento_soat)}
            for transportista in operativos.filter(
                fecha_vencimiento_soat__gte=hoy,
                fecha_vencimiento_soat__lte=hoy + timedelta(days=fechas.DIAS_AVISO_VENCIMIENTO),
            ).order_by("fecha_vencimiento_soat")
        ]

        # Alerta documental en servicio: asignaciones activas cuyo transportista
        # tiene documentos vencidos o pendientes. Es un aviso: no cambia estados
        # ni crea advertencias automáticas.
        contexto["asignaciones_con_alerta"] = [
            {"asignacion": asignacion, "documentos": asignacion.alerta_documental}
            for asignacion in Asignacion.objects.filter(
                estado=EstadoAsignacion.ACTIVA
            )
            .select_related("transportista", "oferta", "oferta__empresa_cliente")
            .order_by("fecha_inicio", "id")
            if asignacion.alerta_documental
        ][:10]

        # Estado vacío: cuando no hay nada registrado, el panel lo explica.
        contexto["tiene_datos"] = bool(
            contexto["total_transportistas"]
            or contexto["total_clientes"]
            or contexto["ofertas_disponibles"]
            or contexto["ofertas_cubiertas"]
        )
        return contexto

    def _vencimientos_proximos(self):
        """Documentos que vencen dentro del plazo de aviso, incluidos los ya vencidos.

        Primero filtra en la base de datos (solo candidatos) y luego calcula el
        detalle en Python: no se cargan todos los transportistas en memoria.
        """
        hoy = fechas.hoy()
        limite = hoy + timedelta(days=fechas.DIAS_AVISO_VENCIMIENTO)
        proximos = []
        candidatos = (
            Transportista.objects.exclude(estado=EstadoTransportista.BAJA)
            .filter(
                Q(fecha_vencimiento_licencia__lte=limite)
                | Q(fecha_vencimiento_revision_tecnica__lte=limite)
                | Q(fecha_vencimiento_soat__lte=limite)
            )
            .order_by("nombre")
        )
        for transportista in candidatos:
            for etiqueta, fecha in transportista.documentos_por_vencer():
                proximos.append(
                    {
                        "transportista": transportista,
                        "documento": etiqueta,
                        "fecha": fecha,
                        "dias": fechas.dias_para_vencer(fecha),
                    }
                )
        proximos.sort(key=lambda fila: fila["fecha"])
        return proximos[:10]

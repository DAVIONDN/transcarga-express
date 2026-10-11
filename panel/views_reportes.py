"""Reportes operativos con filtros y exportación a CSV.

Cada reporte exige el permiso de lectura de su módulo (los combinados exigen
varios) y la exportación usa exactamente las mismas filas filtradas. Solo
agregaciones del ORM para las métricas; sin gráficos.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Max, Q
from django.views.generic import TemplateView

from auditoria.models import auditar
from capacitacion.models import Curso, Participacion
from comun import fechas
from comun.choices import (
    EstadoAsignacion,
    EstadoOferta,
    EstadoParticipacion,
    EstadoTransportista,
    NivelCarga,
)
from comun.permisos import PermisoRequeridoMixin
from liquidaciones.models import EstadoFormato, FormatoSemanal
from ofertas.models import OfertaCarga
from transportistas.models import Advertencia, Transportista
from asignaciones.models import Asignacion

from .csv import respuesta_csv


class ReporteBase(PermisoRequeridoMixin, TemplateView):
    """Plantilla + `?formato=csv` sobre las mismas filas ya filtradas."""

    csv_nombre = "reporte.csv"
    csv_cabeceras = ()

    def get_filas(self):
        """Filas del reporte como tuplas (para HTML y CSV)."""
        return []

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["filas"] = self.get_filas()
        return contexto

    def get(self, request, *args, **kwargs):
        if request.GET.get("formato") == "csv":
            filas = self.get_filas()
            auditar(
                usuario=request.user,
                accion="EXPORTAR",
                entidad="reporte",
                resumen=f"Exportación CSV de {self.csv_nombre} ({len(filas)} filas).",
            )
            return respuesta_csv(self.csv_nombre, self.csv_cabeceras, filas)
        return super().get(request, *args, **kwargs)


class IndiceReportesView(LoginRequiredMixin, TemplateView):
    """Índice: solo muestra los reportes autorizados para el usuario."""

    template_name = "panel/reportes/indice.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Reportes"
        puede = self.request.user.has_perm
        contexto["reportes"] = [
            reporte
            for reporte in (
                {
                    "nombre": "Transportistas por estado y nivel",
                    "descripcion": "Conteo agregado con filtros por estado y nivel.",
                    "url": "panel:reporte_transportistas",
                    "visible": puede("transportistas.view_transportista"),
                },
                {
                    "nombre": "Documentación vencida y próxima a vencer",
                    "descripcion": "Documento, vencimiento y días restantes por transportista.",
                    "url": "panel:reporte_documentos",
                    "visible": puede("transportistas.view_transportista"),
                },
                {
                    "nombre": "Ofertas y asignaciones por periodo",
                    "descripcion": "Creadas e iniciadas en el rango de fechas, por estado.",
                    "url": "panel:reporte_periodo",
                    "visible": puede("ofertas.view_ofertacarga")
                    and puede("asignaciones.view_asignacion"),
                },
                {
                    "nombre": "Advertencias por transportista",
                    "descripcion": "Totales acumulados con filtros por fecha.",
                    "url": "panel:reporte_advertencias",
                    "visible": puede("transportistas.view_advertencia"),
                },
                {
                    "nombre": "Cursos completados",
                    "descripcion": "Participaciones completadas por curso y convocatoria.",
                    "url": "panel:reporte_cursos",
                    "visible": puede("capacitacion.view_participacion"),
                },
                {
                    "nombre": "Formatos y liquidaciones",
                    "descripcion": "Formatos por estado y periodo, con su liquidación.",
                    "url": "panel:reporte_formatos",
                    "visible": puede("liquidaciones.view_formatosemanal"),
                },
            )
            if reporte["visible"]
        ]
        return contexto


class ReporteTransportistasView(ReporteBase):
    permiso_requerido = "transportistas.view_transportista"
    template_name = "panel/reportes/transportistas.html"
    csv_nombre = "transportistas_por_estado_y_nivel.csv"
    csv_cabeceras = ("Estado", "Nivel", "Total")

    def _consulta(self):
        consulta = Transportista.objects.all()
        estado = self.request.GET.get("estado", "")
        if estado:
            consulta = consulta.filter(estado=estado)
        nivel = self.request.GET.get("nivel", "")
        if nivel and nivel.isdigit():
            consulta = consulta.filter(nivel=int(nivel))
        return consulta

    def get_filas(self):
        agregados = (
            self._consulta()
            .values("estado", "nivel")
            .annotate(total=Count("id"))
            .order_by("estado", "nivel")
        )
        estados = dict(EstadoTransportista.choices)
        return [
            (estados.get(fila["estado"], fila["estado"]), f"Nivel {fila['nivel']}", fila["total"])
            for fila in agregados
        ]

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Transportistas por estado y nivel"
        contexto["estados"] = EstadoTransportista.choices
        contexto["niveles"] = NivelCarga.choices
        contexto["filtros"] = {
            "q": "",
            "estado": self.request.GET.get("estado", ""),
            "nivel": self.request.GET.get("nivel", ""),
        }
        contexto["total"] = sum(fila[2] for fila in contexto["filas"])
        return contexto


class ReporteDocumentosView(ReporteBase):
    permiso_requerido = "transportistas.view_transportista"
    template_name = "panel/reportes/documentos.html"
    csv_nombre = "documentacion_vencida.csv"
    csv_cabeceras = ("Transportista", "Placa", "Documento", "Vencimiento", "Días", "Situación")

    DOCUMENTOS = (
        ("licencia", "Licencia de conducir", "fecha_vencimiento_licencia"),
        ("revision", "Revisión técnica", "fecha_vencimiento_revision_tecnica"),
        ("soat", "SOAT", "fecha_vencimiento_soat"),
    )

    def get_filas(self):
        from datetime import timedelta

        hoy = fechas.hoy()
        limite = hoy + timedelta(days=fechas.DIAS_AVISO_VENCIMIENTO)
        documento = self.request.GET.get("documento", "")
        situacion = self.request.GET.get("situacion", "")
        campos = {
            codigo: campo for codigo, _, campo in self.DOCUMENTOS if not documento or codigo == documento
        }
        vencido = Q()
        for campo in campos.values():
            vencido |= Q(**{f"{campo}__lt": hoy})
        candidatos = Transportista.objects.exclude(estado=EstadoTransportista.BAJA)
        if situacion == "vencido":
            candidatos = candidatos.filter(vencido)
        else:
            proximos = Q()
            for campo in campos.values():
                proximos |= Q(**{f"{campo}__lte": limite})
            candidatos = candidatos.filter(proximos)
        filas = []
        for transportista in candidatos.order_by("nombre"):
            for codigo, nombre, campo in self.DOCUMENTOS:
                if codigo not in campos:
                    continue
                fecha = getattr(transportista, campo)
                estado, dias = fechas.estado_documento(fecha)
                if situacion and estado != situacion:
                    continue
                filas.append(
                    (
                        transportista.nombre,
                        transportista.placa,
                        nombre,
                        fechas.formatear_fecha(fecha),
                        "" if dias is None else dias,
                        fechas.ETIQUETAS_ESTADO_DOCUMENTO[estado],
                    )
                )
        return filas

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Documentación vencida y próxima a vencer"
        contexto["filtros"] = {
            "documento": self.request.GET.get("documento", ""),
            "situacion": self.request.GET.get("situacion", ""),
        }
        return contexto


class ReportePeriodoView(ReporteBase):
    permisos_requeridos = ["ofertas.view_ofertacarga", "asignaciones.view_asignacion"]
    template_name = "panel/reportes/periodo.html"
    csv_nombre = "ofertas_y_asignaciones_por_periodo.csv"
    csv_cabeceras = ("Tipo", "Código", "Fecha", "Estado", "Detalle")

    def _rango(self):
        return (
            fechas.interpretar_fecha(self.request.GET.get("desde")),
            fechas.interpretar_fecha(self.request.GET.get("hasta")),
        )

    def get_filas(self):
        desde, hasta = self._rango()
        ofertas = OfertaCarga.objects.select_related("empresa_cliente").order_by("-creado")
        asignaciones = Asignacion.objects.select_related(
            "oferta", "transportista"
        ).order_by("-fecha_inicio")
        if desde:
            ofertas = ofertas.filter(creado__date__gte=desde)
            asignaciones = asignaciones.filter(fecha_inicio__gte=desde)
        if hasta:
            ofertas = ofertas.filter(creado__date__lte=hasta)
            asignaciones = asignaciones.filter(fecha_inicio__lte=hasta)
        filas = [
            (
                "Oferta",
                oferta.codigo,
                oferta.creado.strftime("%d/%m/%Y"),
                oferta.get_estado_display(),
                f"{oferta.origen} → {oferta.destino}",
            )
            for oferta in ofertas
        ]
        filas += [
            (
                "Asignación",
                asignacion.oferta.codigo,
                fechas.formatear_fecha(asignacion.fecha_inicio),
                asignacion.get_estado_display(),
                asignacion.transportista.nombre,
            )
            for asignacion in asignaciones
        ]
        return filas

    def get_context_data(self, **kwargs):
        desde, hasta = self._rango()
        ofertas = OfertaCarga.objects.all()
        asignaciones = Asignacion.objects.all()
        if desde:
            ofertas = ofertas.filter(creado__date__gte=desde)
            asignaciones = asignaciones.filter(fecha_inicio__gte=desde)
        if hasta:
            ofertas = ofertas.filter(creado__date__lte=hasta)
            asignaciones = asignaciones.filter(fecha_inicio__lte=hasta)
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Ofertas y asignaciones por periodo"
        contexto["resumen_ofertas"] = list(
            ofertas.values("estado").annotate(total=Count("id")).order_by("estado")
        )
        contexto["resumen_asignaciones"] = list(
            asignaciones.values("estado").annotate(total=Count("id")).order_by("estado")
        )
        contexto["filtros"] = {
            "desde": self.request.GET.get("desde", ""),
            "hasta": self.request.GET.get("hasta", ""),
        }
        return contexto


class ReporteAdvertenciasView(ReporteBase):
    permiso_requerido = "transportistas.view_advertencia"
    template_name = "panel/reportes/advertencias.html"
    csv_nombre = "advertencias_por_transportista.csv"
    csv_cabeceras = ("Transportista", "Placa", "Total", "Última")

    def _consulta(self):
        consulta = Advertencia.objects.all()
        desde = fechas.interpretar_fecha(self.request.GET.get("desde"))
        if desde:
            consulta = consulta.filter(fecha__gte=desde)
        hasta = fechas.interpretar_fecha(self.request.GET.get("hasta"))
        if hasta:
            consulta = consulta.filter(fecha__lte=hasta)
        return consulta

    def get_filas(self):
        agregados = (
            self._consulta()
            .values("transportista__nombre", "transportista__placa")
            .annotate(total=Count("id"), ultima=Max("fecha"))
            .order_by("-total", "transportista__nombre")
        )
        return [
            (
                fila["transportista__nombre"],
                fila["transportista__placa"],
                fila["total"],
                fechas.formatear_fecha(fila["ultima"]),
            )
            for fila in agregados
        ]

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Advertencias por transportista"
        contexto["filtros"] = {
            "desde": self.request.GET.get("desde", ""),
            "hasta": self.request.GET.get("hasta", ""),
        }
        contexto["total"] = sum(fila[2] for fila in contexto["filas"])
        return contexto


class ReporteCursosView(ReporteBase):
    permiso_requerido = "capacitacion.view_participacion"
    template_name = "panel/reportes/cursos.html"
    csv_nombre = "cursos_completados.csv"
    csv_cabeceras = ("Transportista", "Curso", "Convocatoria", "Finalización", "Resultado")

    def _consulta(self):
        consulta = Participacion.objects.filter(
            estado=EstadoParticipacion.COMPLETADO
        ).select_related("transportista", "curso")
        curso = self.request.GET.get("curso", "")
        if curso.isdigit():
            consulta = consulta.filter(curso_id=int(curso))
        convocatoria = (self.request.GET.get("convocatoria") or "").strip()
        if convocatoria:
            consulta = consulta.filter(convocatoria__icontains=convocatoria)
        desde = fechas.interpretar_fecha(self.request.GET.get("desde"))
        if desde:
            consulta = consulta.filter(fecha_finalizacion__gte=desde)
        hasta = fechas.interpretar_fecha(self.request.GET.get("hasta"))
        if hasta:
            consulta = consulta.filter(fecha_finalizacion__lte=hasta)
        return consulta.order_by("-fecha_finalizacion", "transportista__nombre")

    def get_filas(self):
        return [
            (
                p.transportista.nombre,
                f"{p.curso.codigo} — {p.curso.titulo}",
                p.convocatoria,
                fechas.formatear_fecha(p.fecha_finalizacion),
                p.get_resultado_display() or "—",
            )
            for p in self._consulta()
        ]

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Cursos completados"
        contexto["cursos"] = Curso.objects.order_by("codigo")
        contexto["filtros"] = {
            "curso": self.request.GET.get("curso", ""),
            "convocatoria": self.request.GET.get("convocatoria", ""),
            "desde": self.request.GET.get("desde", ""),
            "hasta": self.request.GET.get("hasta", ""),
        }
        return contexto


class ReporteFormatosView(ReporteBase):
    permisos_requeridos = [
        "liquidaciones.view_formatosemanal",
        "liquidaciones.view_liquidacion",
    ]
    template_name = "panel/reportes/formatos.html"
    csv_nombre = "formatos_y_liquidaciones.csv"
    csv_cabeceras = (
        "Oferta",
        "Transportista",
        "Periodo",
        "Firma prevista",
        "Firma real",
        "Formato",
        "Liquidación",
        "Neto",
    )

    def _consulta(self):
        consulta = FormatoSemanal.objects.select_related(
            "asignacion", "asignacion__oferta", "asignacion__transportista", "liquidacion"
        ).order_by("periodo_inicio", "id")
        estado = self.request.GET.get("estado", "")
        if estado:
            consulta = consulta.filter(estado=estado)
        desde = fechas.interpretar_fecha(self.request.GET.get("desde"))
        if desde:
            consulta = consulta.filter(periodo_inicio__gte=desde)
        hasta = fechas.interpretar_fecha(self.request.GET.get("hasta"))
        if hasta:
            consulta = consulta.filter(periodo_inicio__lte=hasta)
        return consulta

    def get_filas(self):
        filas = []
        for formato in self._consulta():
            liquidacion = getattr(formato, "liquidacion", None)
            filas.append(
                (
                    formato.asignacion.oferta.codigo,
                    formato.asignacion.transportista.nombre,
                    f"{fechas.formatear_fecha(formato.periodo_inicio)} – "
                    f"{fechas.formatear_fecha(formato.periodo_fin)}",
                    fechas.formatear_fecha(formato.fecha_prevista),
                    fechas.formatear_fecha(formato.fecha_firma),
                    formato.etiqueta_estado,
                    liquidacion.get_estado_display() if liquidacion else "Sin liquidar",
                    str(liquidacion.total) if liquidacion else "—",
                )
            )
        return filas

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = "Formatos y liquidaciones"
        contexto["estados"] = EstadoFormato.choices
        contexto["filtros"] = {
            "estado": self.request.GET.get("estado", ""),
            "desde": self.request.GET.get("desde", ""),
            "hasta": self.request.GET.get("hasta", ""),
        }
        return contexto

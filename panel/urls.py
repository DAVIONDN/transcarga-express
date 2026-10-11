from django.urls import path

from . import views, views_reportes, views_usuarios

app_name = "panel"

urlpatterns = [
    path("", views.InicioView.as_view(), name="inicio"),
    path("reportes/", views_reportes.IndiceReportesView.as_view(), name="reportes"),
    path(
        "reportes/transportistas/",
        views_reportes.ReporteTransportistasView.as_view(),
        name="reporte_transportistas",
    ),
    path(
        "reportes/documentos/",
        views_reportes.ReporteDocumentosView.as_view(),
        name="reporte_documentos",
    ),
    path(
        "reportes/periodo/",
        views_reportes.ReportePeriodoView.as_view(),
        name="reporte_periodo",
    ),
    path(
        "reportes/advertencias/",
        views_reportes.ReporteAdvertenciasView.as_view(),
        name="reporte_advertencias",
    ),
    path(
        "reportes/cursos/",
        views_reportes.ReporteCursosView.as_view(),
        name="reporte_cursos",
    ),
    path(
        "reportes/formatos/",
        views_reportes.ReporteFormatosView.as_view(),
        name="reporte_formatos",
    ),
    # Gestión de usuarios (solo Administrador)
    path("usuarios/", views_usuarios.ListaUsuariosView.as_view(), name="usuarios_lista"),
    path("usuarios/nuevo/", views_usuarios.CrearUsuarioView.as_view(), name="usuarios_crear"),
    path(
        "usuarios/<int:pk>/editar/",
        views_usuarios.EditarUsuarioView.as_view(),
        name="usuarios_editar",
    ),
    path(
        "usuarios/<int:pk>/estado/",
        views_usuarios.CambiarEstadoUsuarioView.as_view(),
        name="usuarios_estado",
    ),
    path(
        "usuarios/<int:pk>/clave/",
        views_usuarios.RestablecerClaveUsuarioView.as_view(),
        name="usuarios_clave",
    ),
]

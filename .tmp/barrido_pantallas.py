"""Recurso temporal: barrido de render de todas las rutas con superusuario."""

from django.contrib.auth import get_user_model
from django.test import Client
from django.test.utils import setup_test_environment
from django.urls import reverse

setup_test_environment()

from django.conf import settings

if "testserver" not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]

Usuario = get_user_model()
admin, _ = Usuario.objects.get_or_create(username="auditor_temp", is_superuser=True, is_staff=True)
admin.set_password("x")
admin.save()

cliente = Client()
cliente.force_login(admin)

rutas = [
    ("panel:inicio", ()),
    ("panel:reportes", ()),
    ("panel:reporte_transportistas", ()),
    ("panel:reporte_documentos", ()),
    ("panel:reporte_periodo", ()),
    ("panel:reporte_advertencias", ()),
    ("panel:reporte_cursos", ()),
    ("panel:reporte_formatos", ()),
    ("panel:usuarios_lista", ()),
    ("panel:usuarios_crear", ()),
    ("auditoria:lista", ()),
    ("transportistas:lista", ()),
    ("transportistas:crear", ()),
    ("transportistas:advertencias", ()),
    ("transportistas:incidencias", ()),
    ("transportistas:incidencias_crear", ()),
    ("clientes:lista", ()),
    ("clientes:crear", ()),
    ("ofertas:lista", ()),
    ("ofertas:crear", ()),
    ("asignaciones:lista", ()),
    ("asignaciones:nueva", ()),
    ("liquidaciones:formatos_lista", ()),
    ("liquidaciones:liquidaciones_lista", ()),
    ("liquidaciones:parametros", ()),
    ("capacitacion:cursos_lista", ()),
    ("capacitacion:cursos_crear", ()),
    ("capacitacion:participaciones_lista", ()),
    ("capacitacion:participaciones_inscribir", ()),
    ("login", ()),
]

fallos = []
for nombre, args in rutas:
    try:
        respuesta = cliente.get(reverse(nombre, args=args))
        estado = respuesta.status_code
    except Exception as error:  # noqa: BLE001
        fallos.append((nombre, f"EXC {error}"))
        continue
    html = respuesta.content.decode("utf-8", "replace") if estado == 200 else ""
    problemas = []
    if estado != 200:
        problemas.append(f"HTTP {estado}")
    else:
        for marca in ("tc-topbar", 'id="barraLateral"', "transcarga.js", 'name="viewport"'):
            if marca not in html and nombre != "login":
                problemas.append(f"sin {marca}")
        if nombre != "login" and '<h1 class="tc-titulo"></h1>' in html:
            problemas.append("titulo vacio")
    if problemas:
        fallos.append((nombre, "; ".join(problemas)))

print("rutas revisadas:", len(rutas))
print("fallos:", fallos if fallos else "ninguno")
admin.delete()

"""Verificación (solo lectura) de la estructura visual con los datos demo.

Crea un usuario temporal, recorre todas las pantallas y comprueba los elementos
clave de la interfaz. El usuario se elimina al terminar.
"""

import os
import re
import sys
from pathlib import Path

import django

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.test import Client  # noqa: E402

from asignaciones.models import Asignacion  # noqa: E402
from clientes.models import EmpresaCliente  # noqa: E402
from ofertas.models import OfertaCarga  # noqa: E402
from transportistas.models import Transportista  # noqa: E402

Usuario = get_user_model()
usuario, _ = Usuario.objects.get_or_create(username="visual_temporal")
usuario.set_password("clave-temporal-123")
usuario.is_staff = True
usuario.save()

cliente = Client(SERVER_NAME="127.0.0.1")
cliente.force_login(usuario)

transportista = Transportista.objects.first()
empresa = EmpresaCliente.objects.first()
oferta = OfertaCarga.objects.first()
of = OfertaCarga.objects.filter(estado="DISPONIBLE").first() or oferta
asignacion = Asignacion.objects.first()

rutas = [
    ("/", "Panel"),
    ("/transportistas/", "Listado de transportistas"),
    (f"/transportistas/{transportista.pk}/", "Ficha del transportista"),
    ("/transportistas/nuevo/", "Alta de transportista"),
    (f"/transportistas/{transportista.pk}/editar/", "Edición"),
    (f"/transportistas/{transportista.pk}/estado/", "Cambio de estado"),
    (f"/transportistas/{transportista.pk}/advertencia/", "Registrar advertencia"),
    ("/transportistas/advertencias/", "Advertencias (navegación)"),
    ("/clientes/", "Empresas clientes"),
    (f"/clientes/{empresa.pk}/", "Ficha de empresa"),
    ("/clientes/nuevo/", "Alta de empresa"),
    ("/ofertas/", "Ofertas de carga"),
    (f"/ofertas/{oferta.pk}/", "Ficha de oferta"),
    ("/ofertas/nueva/", "Alta de oferta"),
    (f"/ofertas/{of.pk}/asignar/", "Asignar transportista"),
    ("/asignaciones/", "Asignaciones"),
    (f"/asignaciones/{asignacion.pk}/", "Ficha de asignación"),
    ("/admin/", "Panel de Django"),
]

fallos = 0
print("RUTAS")
for ruta, descripcion in rutas:
    respuesta = cliente.get(ruta)
    ok = respuesta.status_code == 200
    fallos += 0 if ok else 1
    print(f"  {'OK' if ok else 'FALLA':6} {respuesta.status_code}  {ruta:45} {descripcion}")

print("\nESTRUCTURA VISUAL (pantalla /)")
html = cliente.get("/").content.decode("utf-8")
secciones = ["Panel", "Transportistas", "Empresas clientes", "Ofertas de carga", "Asignaciones",
             "Advertencias", "Panel de Django", "Cerrar sesión", "TransCarga Express"]
for seccion in secciones:
    presente = seccion in html
    fallos += 0 if presente else 1
    print(f"  {'OK' if presente else 'FALLA':6} {seccion}")

barra_lateral = 'class="offcanvas-lg offcanvas-start barra-lateral' in html
print(f"  {'OK' if barra_lateral else 'FALLA':6} barra lateral responsiva presente")
fallos += 0 if barra_lateral else 1

print("\nALERTAS Y CONTEO EN EL PANEL")
from panel.views import InicioView  # noqa: E402

contexto = InicioView().get_context_data()
for clave in ("total_transportistas", "transportistas_activos", "transportistas_reserva",
              "transportistas_baja", "ofertas_disponibles", "ofertas_cubiertas",
              "asignaciones_activas", "total_clientes"):
    print(f"  {clave:24} = {contexto[clave]}")
print(f"  {'SOAT vencidos':24} = {[f['transportista'].nombre for f in contexto['soat_vencidos']]}")
print(f"  {'SOAT por vencer':24} = {[f['transportista'].nombre for f in contexto['soat_por_vencer']]}")
print(f"  {'advertencias recientes':24} = {len(contexto['advertencias_recientes'])}")
print(f"  {'documentos por vencer':24} = {len(contexto['vencimientos'])}")
print(f"  {'tiene_datos':24} = {contexto['tiene_datos']}")

for texto in ("SOAT vencido", "SOAT próximo a vencer"):
    presente = texto in html
    fallos += 0 if presente else 1
    print(f"  {'OK' if presente else 'FALLA':6} alerta «{texto}» visible")

print("\nACCESO (anónimo)")
cliente.logout()
acceso = cliente.get("/accounts/login/").content.decode("utf-8")
sin_navegacion = "Cerrar sesión" not in acceso and "Empresas clientes" not in acceso
print(f"  {'OK' if sin_navegacion else 'FALLA':6} la pantalla de acceso no muestra la navegación")
fallos += 0 if sin_navegacion else 1
print(f"  {'OK' if 'Ingresar' in acceso else 'FALLA':6} formulario de acceso en español")

print(f"\nFALLOS: {fallos}")
usuario.delete()

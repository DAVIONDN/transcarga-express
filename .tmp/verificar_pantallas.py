"""Verificación de plantillas con los datos demo reales (recurso del entorno).

Recorre todas las pantallas con un usuario temporal y reporta el código de
respuesta. El usuario se elimina al terminar.
"""

import os
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
usuario, _ = Usuario.objects.get_or_create(username="smoke_temporal")
usuario.set_password("clave-temporal-123")
usuario.save()

cliente = Client(SERVER_NAME="127.0.0.1")
cliente.force_login(usuario)

transportista = Transportista.objects.first()
cliente_empresa = EmpresaCliente.objects.first()
oferta = OfertaCarga.objects.first()
oferta_cubierta = OfertaCarga.objects.filter(estado="CUBIERTA").first()
asignacion = Asignacion.objects.first()

rutas = [
    "/",
    "/transportistas/",
    f"/transportistas/{transportista.pk}/",
    "/transportistas/nuevo/",
    f"/transportistas/{transportista.pk}/editar/",
    f"/transportistas/{transportista.pk}/estado/",
    f"/transportistas/{transportista.pk}/advertencia/",
    "/clientes/",
    f"/clientes/{cliente_empresa.pk}/",
    "/clientes/nuevo/",
    "/ofertas/",
    f"/ofertas/{oferta.pk}/",
    "/ofertas/nueva/",
    f"/ofertas/{oferta.pk}/editar/",
    f"/ofertas/{oferta.pk}/asignar/",
    "/asignaciones/",
    f"/asignaciones/{asignacion.pk}/",
    "/admin/",
]

fallas = 0
for ruta in rutas:
    respuesta = cliente.get(ruta)
    esperado = 302 if ruta == "/admin/" else 200
    if ruta.endswith("/asignar/") and oferta.estado == "CUBIERTA":
        esperado = 302
    if ruta == f"/ofertas/{oferta_cubierta.pk}/asignar/":
        esperado = 302
    estado = "OK" if respuesta.status_code == esperado else "FALLA"
    fallas += 0 if respuesta.status_code == esperado else 1
    print(f"{estado:6} {respuesta.status_code} {ruta}")

if oferta_cubierta:
    respuesta = cliente.get(f"/ofertas/{oferta_cubierta.pk}/asignar/")
    print(f"{'OK' if respuesta.status_code == 302 else 'FALLA':6} {respuesta.status_code} /ofertas/{oferta_cubierta.pk}/asignar/ (oferta cubierta)")
    fallas += 0 if respuesta.status_code == 302 else 1

if transportista.fotografia_vehiculo:
    respuesta = cliente.get(transportista.fotografia_vehiculo.url)
    print(f"{'OK' if respuesta.status_code == 200 else 'FALLA':6} {respuesta.status_code} {transportista.fotografia_vehiculo.url}")
    fallas += 0 if respuesta.status_code == 200 else 1

usuario.delete()
print("Fallos:", fallas)

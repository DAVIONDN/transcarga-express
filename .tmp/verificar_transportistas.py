"""Verificación de extremo a extremo del módulo de transportistas.

Ejercita el ciclo completo contra la base de datos demo con el cliente de pruebas
de Django y limpia todo lo que crea. Recurso del entorno, no forma parte del
proyecto.
"""

import os
import sys
from decimal import Decimal
from pathlib import Path

import django

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.test import Client  # noqa: E402
from django.test.utils import setup_test_environment, teardown_test_environment  # noqa: E402

from comun.choices import EstadoTransportista, NivelCarga  # noqa: E402
from comun.pruebas import datos_post_transportista  # noqa: E402
from transportistas.models import Transportista  # noqa: E402

setup_test_environment()  # necesario para que response.context esté disponible

Usuario = get_user_model()
NUMERO = "47890123"
PLACA = "Z9X-123"

fallos = 0


def comprobar(descripcion, condicion, detalle=""):
    global fallos
    fallos += 0 if condicion else 1
    print(f"  {'OK' if condicion else 'FALLA':6} {descripcion}{detalle}")


# Limpieza preventiva por si quedó algo de una ejecución anterior
Transportista.objects.filter(numero_documento=NUMERO).delete()

usuario, _ = Usuario.objects.get_or_create(username="e2e_temporal")
usuario.set_password("clave-temporal-123")
usuario.save()
cliente = Client(SERVER_NAME="127.0.0.1")
cliente.force_login(usuario)

total_inicial = Transportista.objects.count()
print("1) LISTADO, BÚSQUEDA Y FILTROS")
listado = cliente.get("/transportistas/")
comprobar("el listado responde 200", listado.status_code == 200)
comprobar("muestra todos los transportistas", len(listado.context["transportistas"]) == total_inicial,
          f" ({total_inicial} registros)")
por_placa = cliente.get("/transportistas/", {"q": "V1A-201"})
comprobar("búsqueda por placa devuelve 1", len(por_placa.context["transportistas"]) == 1)
documento = Transportista.objects.first().numero_documento
por_documento = cliente.get("/transportistas/", {"q": documento})
comprobar("búsqueda por documento devuelve 1", len(por_documento.context["transportistas"]) == 1)
por_nombre = cliente.get("/transportistas/", {"q": "María"})
comprobar("búsqueda por nombre devuelve al menos 1", len(por_nombre.context["transportistas"]) >= 1)
por_estado = cliente.get("/transportistas/", {"estado": EstadoTransportista.BAJA})
comprobar("filtro por estado «Baja»", all(t.estado == EstadoTransportista.BAJA for t in por_estado.context["transportistas"]),
          f" ({len(por_estado.context['transportistas'])} registros)")
por_nivel = cliente.get("/transportistas/", {"nivel": NivelCarga.NIVEL_1})
comprobar("filtro por nivel 1", all(t.nivel == NivelCarga.NIVEL_1 for t in por_nivel.context["transportistas"]))

print("2) FICHA COMPLETA")
transportista = Transportista.objects.filter(fotografia_vehiculo__isnull=False).first()
ficha = cliente.get(f"/transportistas/{transportista.pk}/")
html = ficha.content.decode("utf-8")
comprobar("la ficha responde 200", ficha.status_code == 200)
comprobar("muestra la fotografía del vehículo", transportista.fotografia_vehiculo.url in html)
comprobar("el archivo de la fotografía existe", Path(transportista.fotografia_vehiculo.path).exists())
comprobar("muestra la fecha de la licencia", transportista.fecha_vencimiento_licencia.strftime("%d/%m/%Y") in html)
comprobar("muestra la fecha de la revisión técnica", transportista.fecha_vencimiento_revision_tecnica.strftime("%d/%m/%Y") in html)
comprobar("muestra la fecha del SOAT", transportista.fecha_vencimiento_soat.strftime("%d/%m/%Y") in html)
comprobar("muestra el número de advertencias", f"{transportista.advertencias_total} de 3" in html)
comprobar("muestra el nivel calculado", f"Nivel {transportista.nivel}" in html)
comprobar("muestra el historial de asignaciones", "Asignaciones" in html and "Advertencias" in html)

print("3) REGISTRO VÁLIDO")
alta = cliente.post("/transportistas/nuevo/", datos_post_transportista(
    numero_documento=NUMERO, placa=PLACA, nombre="E2E Prueba Manual",
    capacidad_toneladas="12.00",
))
comprobar("el alta redirige (302)", alta.status_code == 302, f" -> {alta.headers.get('Location', '')}")
creado = Transportista.objects.filter(numero_documento=NUMERO).first()
comprobar("el transportista quedó registrado", creado is not None)
if creado:
    comprobar("placa normalizada", creado.placa == PLACA)
    comprobar("nivel derivado (12 t -> 2)", creado.nivel == NivelCarga.NIVEL_2, f" (nivel {creado.nivel})")
    comprobar("fotografía guardada en disco", Path(creado.fotografia_vehiculo.path).exists())

print("4) DOCUMENTO Y PLACA DUPLICADOS")
duplicado = cliente.post("/transportistas/nuevo/", datos_post_transportista(
    numero_documento=NUMERO, placa="Q1Q-111",
))
comprobar("documento duplicado rechazado", duplicado.status_code == 200)
comprobar("mensaje concreto de documento duplicado",
          "Ya existe un transportista registrado con este número de documento" in duplicado.content.decode("utf-8"))
duplicado_placa = cliente.post("/transportistas/nuevo/", datos_post_transportista(
    numero_documento="47890124", placa=PLACA,
))
comprobar("placa duplicada rechazada",
          "Ya existe un transportista registrado con esta placa" in duplicado_placa.content.decode("utf-8"))

print("5) REQUISITOS DOCUMENTALES Y CLASIFICACIÓN")
from datetime import timedelta  # noqa: E402

from django.utils import timezone  # noqa: E402

hoy = timezone.localdate()
licencia_vencida = cliente.post("/transportistas/nuevo/", datos_post_transportista(
    numero_documento="47890125", placa="Q2Q-222",
    fecha_vencimiento_licencia=(hoy - timedelta(days=1)).isoformat(),
))
comprobar("licencia vencida rechazada",
          "licencia de conducir debe estar vigente" in licencia_vencida.content.decode("utf-8"))
revision_vencida = cliente.post("/transportistas/nuevo/", datos_post_transportista(
    numero_documento="47890126", placa="Q3Q-333",
    fecha_vencimiento_revision_tecnica=(hoy - timedelta(days=1)).isoformat(),
))
comprobar("revisión técnica vencida rechazada",
          "revisión técnica debe estar vigente" in revision_vencida.content.decode("utf-8"))
sin_certificacion = cliente.post("/transportistas/nuevo/", datos_post_transportista(
    numero_documento="47890127", placa="Q4Q-444", capacidad_toneladas="25.00",
))
comprobar("capacidad > 20 t sin certificación rechazada",
          "certificación de carga peligrosa es obligatoria" in sin_certificacion.content.decode("utf-8"))
sin_foto = datos_post_transportista(numero_documento="47890128", placa="Q5Q-555")
sin_foto.pop("fotografia_vehiculo")
sin_fotografia = cliente.post("/transportistas/nuevo/", sin_foto)
comprobar("fotografía ausente rechazada", "fotografia_vehiculo" in sin_fotografia.context["form"].errors)

print("6) EDICIÓN Y CAMBIO DE ESTADO")
edicion = cliente.post(f"/transportistas/{creado.pk}/editar/", datos_post_transportista(
    numero_documento=NUMERO, placa=PLACA, nombre="E2E Prueba Manual",
    capacidad_toneladas="25.00", certificacion_carga_peligrosa="on",
))
creado.refresh_from_db()
comprobar("edición aceptada", edicion.status_code == 302)
comprobar("nivel recalculado tras la edición (25 t -> 1)", creado.nivel == NivelCarga.NIVEL_1,
          f" (nivel {creado.nivel})")
en_reserva = cliente.post(f"/transportistas/{creado.pk}/estado/", {"estado": EstadoTransportista.EN_RESERVA})
creado.refresh_from_db()
comprobar("cambio a En Reserva aceptado", en_reserva.status_code == 302)
comprobar("estado actualizado", creado.estado == EstadoTransportista.EN_RESERVA)
comprobar("la fotografía se conserva sin volver a subirla", Path(creado.fotografia_vehiculo.path).exists())

print("7) LIMPIEZA")
ruta_foto = creado.fotografia_vehiculo.path
creado.delete()
if Path(ruta_foto).exists():
    os.remove(ruta_foto)
comprobar("el transportista de prueba fue eliminado", not Transportista.objects.filter(numero_documento=NUMERO).exists())
comprobar("la base demo queda igual", Transportista.objects.count() == total_inicial,
          f" ({Transportista.objects.count()}/{total_inicial})")
usuario.delete()
teardown_test_environment()

print(f"\nFALLOS: {fallos}")

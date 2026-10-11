"""Verificación de extremo a extremo del flujo de asignación.

Recorre el flujo completo (elegir → confirmar → crear → finalizar → cancelar) sobre
la base demo y limpia todo lo que crea. Recurso del entorno, no del proyecto.
"""

import os
import sys
from datetime import timedelta
from pathlib import Path

import django

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.test import Client  # noqa: E402
from django.test.utils import setup_test_environment, teardown_test_environment  # noqa: E402
from django.utils import timezone  # noqa: E402

from asignaciones.models import Asignacion  # noqa: E402
from asignaciones.reglas import motivos_no_elegibilidad  # noqa: E402
from clientes.models import EmpresaCliente  # noqa: E402
from comun.choices import EstadoAsignacion, EstadoOferta, NivelCarga, TipoVehiculo  # noqa: E402
from ofertas.models import OfertaCarga  # noqa: E402
from transportistas.models import Transportista  # noqa: E402

setup_test_environment()
HOY = timezone.localdate()

fallos = 0


def comprobar(descripcion, condicion, detalle=""):
    global fallos
    fallos += 0 if condicion else 1
    print(f"  {'OK' if condicion else 'FALLA':6} {descripcion}{detalle}")


usuario, _ = get_user_model().objects.get_or_create(username="e2e_temporal")
usuario.set_password("clave-temporal-123")
usuario.save()
cliente = Client(SERVER_NAME="127.0.0.1")
cliente.force_login(usuario)

total_asignaciones = Asignacion.objects.count()
total_ofertas = OfertaCarga.objects.count()
empresa = EmpresaCliente.objects.first()
transportista = Transportista.objects.filter(
    estado="ACTIVO", asignaciones__isnull=True
).first()


def crear_oferta_demo(destino):
    return OfertaCarga.objects.create(
        empresa_cliente=empresa,
        origen="Lima",
        destino=destino,
        tipo_vehiculo_requerido=transportista.tipo_vehiculo,
        nivel_requerido=transportista.nivel,
        remuneracion="1234.56",
    )


print("1) OFERTAS DISPONIBLES Y TRANSPORTISTA COMPATIBLE")
disponibles = OfertaCarga.objects.filter(estado=EstadoOferta.DISPONIBLE)
comprobar("hay ofertas disponibles en la demo", disponibles.count() >= 1, f" ({disponibles.count()})")
listado = cliente.get("/asignaciones/nueva/")
comprobar("la pantalla de nueva asignación responde 200", listado.status_code == 200)
ofertas_formulario = list(listado.context["form"].fields["oferta"].queryset)
comprobar("solo ofrece ofertas disponibles", all(o.estado == EstadoOferta.DISPONIBLE for o in ofertas_formulario))
comprobar("el transportista elegido está Activo", transportista.estado == "ACTIVO",
          f" ({transportista.nombre}, Nivel {transportista.nivel})")

print("2) VALIDACIONES OBLIGATORIAS CON DATOS REALES (mensajes al operador)")
oferta_prueba = crear_oferta_demo("Tacna")
for candidato in Transportista.objects.all().order_by("nombre"):
    motivos = motivos_no_elegibilidad(candidato, oferta_prueba)
    estado = "elegible" if not motivos else f"{len(motivos)} motivo(s)"
    print(f"    {candidato.nombre[:32]:34} [{candidato.get_estado_display():10}] {estado}")
    for motivo in motivos:
        print(f"        - {motivo}")
comprobar("los mensajes indican cómo resolverlo",
          any("Cámbiele" in m or "Actualice" in m or "Finalice" in m
              for candidato in Transportista.objects.all()
              for m in motivos_no_elegibilidad(candidato, oferta_prueba)))

print("3) SELECCIÓN Y CONFIRMACIÓN (paso 1 y paso 2)")
primer_paso = cliente.post("/asignaciones/nueva/", {
    "oferta": oferta_prueba.pk, "transportista": transportista.pk,
    "fecha_inicio": str(HOY),
})
comprobar("el paso 1 redirige a la confirmación", primer_paso.status_code == 302
          and primer_paso.url == "/asignaciones/confirmar/")
comprobar("todavía NO se creó la asignación", not Asignacion.objects.filter(oferta=oferta_prueba).exists())
oferta_prueba.refresh_from_db()
comprobar("la oferta sigue Disponible", oferta_prueba.estado == EstadoOferta.DISPONIBLE)

resumen = cliente.get("/asignaciones/confirmar/")
comprobar("el resumen responde 200", resumen.status_code == 200)
html = resumen.content.decode("utf-8")
for dato, etiqueta in [
    (oferta_prueba.codigo, "código de la oferta"),
    (empresa.razon_social, "empresa cliente"),
    (transportista.nombre, "transportista"),
    (transportista.placa, "placa del vehículo"),
    (transportista.get_tipo_vehiculo_display(), "tipo de vehículo"),
]:
    comprobar(f"el resumen muestra {etiqueta}", dato in html)

print("4) CREACIÓN Y DETALLE")
creacion = cliente.post("/asignaciones/confirmar/")
asignacion = Asignacion.objects.filter(oferta=oferta_prueba).first()
comprobar("se creó la asignación", asignacion is not None)
comprobar("redirige al detalle", creacion.status_code == 302
          and creacion.url == f"/asignaciones/{asignacion.pk}/")
oferta_prueba.refresh_from_db()
comprobar("la oferta pasó a Cubierta", oferta_prueba.estado == EstadoOferta.CUBIERTA)
comprobar("el transportista tiene asignación activa", transportista.tiene_asignacion_activa)
detalle = cliente.get(f"/asignaciones/{asignacion.pk}/")
comprobar("el detalle responde 200 y muestra la oferta",
          detalle.status_code == 200 and oferta_prueba.codigo in detalle.content.decode("utf-8"))

print("5) VALIDACIONES QUE BLOQUEAN (servidor)")
oferta_bloqueada = crear_oferta_demo("Puno")
otro = Transportista.objects.filter(estado="ACTIVO", asignaciones__isnull=True).exclude(pk=transportista.pk).first()
bloqueo_activo = cliente.post("/asignaciones/nueva/", {
    "oferta": oferta_bloqueada.pk, "transportista": transportista.pk,
    "fecha_inicio": str(HOY),
})
comprobar("un transportista con asignación activa no puede recibir otra",
          bloqueo_activo.status_code == 200
          and "ya tiene una asignación activa" in bloqueo_activo.content.decode("utf-8"))
comprobar("no se creó una segunda asignación", not Asignacion.objects.filter(oferta=oferta_bloqueada).exists())

if otro:
    cubierta = cliente.post("/asignaciones/nueva/", {
        "oferta": oferta_prueba.pk, "transportista": otro.pk,
        "fecha_inicio": str(HOY),
    })
    comprobar("no se ofrece una oferta ya cubierta",
              cubierta.status_code == 200
              and "no está entre las disponibles" in cubierta.content.decode("utf-8"))

print("6) FINALIZAR (con confirmación)")
confirmar_fin = cliente.get(f"/asignaciones/{asignacion.pk}/finalizar/")
comprobar("pantalla de confirmación de finalización",
          confirmar_fin.status_code == 200 and "Confirmar finalización" in confirmar_fin.content.decode("utf-8"))
fin = cliente.post(f"/asignaciones/{asignacion.pk}/finalizar/", {"fecha_fin": str(HOY)})
asignacion.refresh_from_db()
oferta_prueba.refresh_from_db()
comprobar("la asignación queda Finalizada", fin.status_code == 302 and asignacion.esta_finalizada)
comprobar("la oferta permanece Cubierta", oferta_prueba.estado == EstadoOferta.CUBIERTA)
comprobar("el transportista queda libre", not transportista.tiene_asignacion_activa)
comprobar("el historial se conserva", Asignacion.objects.filter(oferta=oferta_prueba).count() == 1)

print("7) CANCELAR (con confirmación)")
oferta_cancelar = crear_oferta_demo("Iquitos")
cliente.post("/asignaciones/nueva/", {
    "oferta": oferta_cancelar.pk, "transportista": transportista.pk,
    "fecha_inicio": str(HOY),
})
cliente.post("/asignaciones/confirmar/")
cancelable = Asignacion.objects.filter(oferta=oferta_cancelar).first()
confirmar_cancelar = cliente.get(f"/asignaciones/{cancelable.pk}/cancelar/")
comprobar("pantalla de confirmación de cancelación",
          confirmar_cancelar.status_code == 200
          and "Confirmar cancelación" in confirmar_cancelar.content.decode("utf-8"))
cancelacion = cliente.post(f"/asignaciones/{cancelable.pk}/cancelar/",
                           {"fecha": str(HOY)})
cancelable.refresh_from_db()
oferta_cancelar.refresh_from_db()
comprobar("la asignación queda Cancelada", cancelacion.status_code == 302 and cancelable.esta_cancelada)
comprobar("la oferta permanece Cubierta", oferta_cancelar.estado == EstadoOferta.CUBIERTA)
comprobar("el transportista queda libre", not transportista.tiene_asignacion_activa)
comprobar("el historial del transportista conserva las dos asignaciones",
          transportista.asignaciones.count() == 2)

print("8) LISTADO CON LOS TRES ESTADOS")
listado_final = cliente.get("/asignaciones/")
conteos = {fila["valor"]: fila["total"] for fila in listado_final.context["conteos"]}
print(f"    conteos: {conteos}")
comprobar("el listado muestra activas, finalizadas y canceladas",
          all(valor in conteos for valor in ("ACTIVA", "FINALIZADA", "CANCELADA")))

print("9) LIMPIEZA")
for oferta in (oferta_prueba, oferta_cancelar, oferta_bloqueada):
    Asignacion.objects.filter(oferta=oferta).delete()
    OfertaCarga.objects.filter(pk=oferta.pk).delete()
comprobar("base demo restaurada",
          Asignacion.objects.count() == total_asignaciones and OfertaCarga.objects.count() == total_ofertas,
          f" ({Asignacion.objects.count()}/{total_asignaciones} asignaciones, "
          f"{OfertaCarga.objects.count()}/{total_ofertas} ofertas)")
usuario.delete()
teardown_test_environment()
print(f"\nFALLOS: {fallos}")


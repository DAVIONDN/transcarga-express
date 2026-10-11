"""Verificación de extremo a extremo del módulo de Advertencias.

Recorre el registro de advertencias, la baja automática a la tercera, el bloqueo de
asignaciones, los filtros y los indicadores del panel; al terminar restaura el estado
original de los datos demo. Recurso del entorno, no del proyecto.
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
from django.test.utils import setup_test_environment, teardown_test_environment  # noqa: E402
from django.utils import timezone  # noqa: E402

from asignaciones.forms import AsignacionForm  # noqa: E402
from asignaciones.models import Asignacion  # noqa: E402
from asignaciones.reglas import motivos_no_elegibilidad  # noqa: E402
from comun.choices import EstadoTransportista, NivelCarga, TipoVehiculo  # noqa: E402
from ofertas.models import OfertaCarga  # noqa: E402
from transportistas.models import Advertencia, Transportista  # noqa: E402

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

# Transportista demo con asignación activa y sin advertencias (se restaura al final)
transportista = (
    Transportista.objects.filter(advertencias__isnull=True, asignaciones__estado="ACTIVA")
    .distinct()
    .first()
) or Transportista.objects.filter(advertencias__isnull=True).first()
estado_original = transportista.estado
asignacion_previa = transportista.asignaciones.filter(estado="ACTIVA").first()
total_advertencias_inicial = Advertencia.objects.count()
bajas_iniciales = Transportista.objects.filter(estado=EstadoTransportista.BAJA).count()

print(f"TRANSPORTISTA DE PRUEBA: {transportista.nombre} (estado {estado_original}, "
      f"{transportista.advertencias.count()} advertencias, asignación activa: "
      f"{'sí' if asignacion_previa else 'no'})")

url_registro = f"/transportistas/{transportista.pk}/advertencia/"


def registrar(descripcion, token=None, follow=False):
    cliente.get(url_registro)
    clave = f"advertencia_token_{transportista.pk}"
    return cliente.post(
        url_registro,
        {"fecha": str(HOY), "descripcion": descripcion, "token": token or cliente.session[clave]},
        follow=follow,
    )


print("\n1) PRIMERA Y SEGUNDA ADVERTENCIA (no dan de baja)")
registrar("Demora leve en la entrega")
transportista.refresh_from_db()
comprobar("tras la 1ª queda Activo", transportista.estado == estado_original,
          f" (estado {transportista.get_estado_display()}, {transportista.advertencias.count()} advertencia)")
registrar("Documentación incompleta en el recojo")
transportista.refresh_from_db()
comprobar("tras la 2ª sigue habilitado", transportista.estado != EstadoTransportista.BAJA,
          f" ({transportista.advertencias.count()} advertencias)")
oferta_disponible = OfertaCarga.objects.filter(
    estado="DISPONIBLE",
    nivel_requerido=transportista.nivel,
    tipo_vehiculo_requerido=transportista.tipo_vehiculo,
).first() or OfertaCarga.objects.first()
motivos_tras_dos = motivos_no_elegibilidad(transportista, oferta_disponible)
comprobar("las dos advertencias no lo bloquean (no aparece «dado de baja»)",
          not any("dado de baja" in motivo for motivo in motivos_tras_dos),
          f" ({len(motivos_tras_dos)} motivo(s) ajenos a las advertencias)")

print("\n2) TERCERA ADVERTENCIA (baja automática)")
respuesta = registrar("Reiteradas quejas del cliente", follow=True)
transportista.refresh_from_db()
comprobar("el estado cambió a Baja", transportista.estado == EstadoTransportista.BAJA,
          f" ({transportista.advertencias.count()} advertencias)")
html = respuesta.content.decode("utf-8")
comprobar("el sistema informa de la baja", "pasó automáticamente a estado «Baja»" in html)
comprobar("e informa de que no recibirá asignaciones", "no podrá recibir nuevas asignaciones" in html)

print("\n3) CUARTA ADVERTENCIA Y DOBLE ENVÍO")
url_actual = f"/transportistas/{transportista.pk}/advertencia/"
cliente.get(url_actual)
clave = f"advertencia_token_{transportista.pk}"
datos = {"fecha": str(HOY), "descripcion": "Advertencia posterior a la baja", "token": cliente.session[clave]}
cliente.post(url_actual, datos)
cliente.post(url_actual, datos)  # el mismo envío, dos veces
transportista.refresh_from_db()
comprobar("el doble envío no duplica la advertencia", transportista.advertencias.count() == 4,
          f" ({transportista.advertencias.count()} advertencias)")
comprobar("la cuarta advertencia no reactiva al transportista",
          transportista.estado == EstadoTransportista.BAJA)

print("\n4) HISTORIAL Y BLOQUEO DE ASIGNACIONES")
comprobar("las advertencias se conservan", transportista.advertencias.count() == 4)
if asignacion_previa:
    asignacion_previa.refresh_from_db()
    comprobar("la asignación previa se conserva",
              transportista.asignaciones.filter(pk=asignacion_previa.pk).exists())
    comprobar("la asignación previa sigue activa", asignacion_previa.esta_activa)
    comprobar("la oferta de esa asignación sigue Cubierta",
              asignacion_previa.oferta.estado == "CUBIERTA")
comprobar("no aparece entre los transportistas asignables",
          transportista not in AsignacionForm().fields["transportista"].queryset)
motivos = motivos_no_elegibilidad(transportista, OfertaCarga.objects.first())
comprobar("las reglas explican el motivo",
          any("dado de baja" in motivo for motivo in motivos),
          f" ({len(motivos)} motivo(s))")
nueva = cliente.post("/asignaciones/nueva/", {
    "oferta": OfertaCarga.objects.filter(estado="DISPONIBLE").first().pk,
    "transportista": transportista.pk,
    "fecha_inicio": str(HOY),
})
antes = Asignacion.objects.count()
comprobar("un POST directo no crea la asignación",
          "transportista" in nueva.context["form"].errors and Asignacion.objects.count() == antes)

print("\n5) LISTADO GENERAL CON FILTROS")
listado = cliente.get("/transportistas/advertencias/")
comprobar("el listado responde 200", listado.status_code == 200)
por_transportista = cliente.get("/transportistas/advertencias/", {"transportista": transportista.pk})
comprobar("filtro por transportista",
          all(a.transportista_id == transportista.pk for a in por_transportista.context["advertencias"])
          and por_transportista.context["advertencias"].count() == 4,
          f" ({por_transportista.context['advertencias'].count()} registros)")
desde_hoy = cliente.get("/transportistas/advertencias/", {"desde": str(HOY)})
comprobar("filtro por fecha (desde hoy)",
          all(a.fecha >= HOY for a in desde_hoy.context["advertencias"]))
hasta_antiguo = cliente.get("/transportistas/advertencias/",
                            {"hasta": str(HOY - timezone.timedelta(days=365))})
comprobar("filtro por fecha (hasta hace un año) no devuelve nada",
          hasta_antiguo.context["advertencias"].count() == 0)
resumen = {fila.pk: fila.total for fila in listado.context["transportistas_con_advertencias"]}
comprobar("el listado muestra el total por transportista", resumen.get(transportista.pk) == 4,
          f" (total {resumen.get(transportista.pk)})")

print("\n6) INDICADORES DEL PANEL")
panel = cliente.get("/")
comprobar("el panel muestra las advertencias recientes",
          "Advertencias recientes" in panel.content.decode("utf-8"))
comprobar("el panel lista los transportistas dados de baja",
          "Transportistas dados de baja" in panel.content.decode("utf-8")
          and transportista.nombre in panel.content.decode("utf-8"))
comprobar("el contador de bajas aumenta",
          len(panel.context["transportistas_de_baja"]) == bajas_iniciales + 1,
          f" ({len(panel.context['transportistas_de_baja'])} bajas)")

print("\n7) RESTAURACIÓN DE LOS DATOS DEMO")
transportista.advertencias.all().delete()
transportista.estado = estado_original
transportista.save(update_fields=["estado", "actualizado"])
transportista.refresh_from_db()
comprobar("advertencias restauradas", Advertencia.objects.count() == total_advertencias_inicial,
          f" ({Advertencia.objects.count()}/{total_advertencias_inicial})")
comprobar("estado restaurado", transportista.estado == estado_original)
comprobar("bajas restauradas",
          Transportista.objects.filter(estado=EstadoTransportista.BAJA).count() == bajas_iniciales)
usuario.delete()
teardown_test_environment()
print(f"\nFALLOS: {fallos}")

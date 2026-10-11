"""Verificación de extremo a extremo de Empresas Clientes y Ofertas de Carga.

Ejercita el ciclo completo contra la base demo y limpia todo lo que crea.
Recurso del entorno, no forma parte del proyecto.
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

from clientes.models import EmpresaCliente  # noqa: E402
from comun.choices import EstadoOferta, NivelCarga, TipoVehiculo  # noqa: E402
from ofertas.models import OfertaCarga  # noqa: E402

setup_test_environment()

RUC = "20911122233"
fallos = 0


def comprobar(descripcion, condicion, detalle=""):
    global fallos
    fallos += 0 if condicion else 1
    print(f"  {'OK' if condicion else 'FALLA':6} {descripcion}{detalle}")


EmpresaCliente.objects.filter(ruc=RUC).delete()
usuario, _ = get_user_model().objects.get_or_create(username="e2e_temporal")
usuario.set_password("clave-temporal-123")
usuario.save()
cliente = Client(SERVER_NAME="127.0.0.1")
cliente.force_login(usuario)

total_empresas = EmpresaCliente.objects.count()
total_ofertas = OfertaCarga.objects.count()

print("EMPRESAS CLIENTES")
listado = cliente.get("/clientes/")
comprobar("listado 200", listado.status_code == 200)
comprobar("muestra todas las empresas", len(listado.context["empresas"]) == total_empresas, f" ({total_empresas})")

empresa = EmpresaCliente.objects.first()
por_ruc = cliente.get("/clientes/", {"q": empresa.ruc})
comprobar("búsqueda por RUC", list(por_ruc.context["empresas"]) == [empresa])
por_nombre = cliente.get("/clientes/", {"q": empresa.razon_social[:8]})
comprobar("búsqueda por razón social", len(por_nombre.context["empresas"]) >= 1)
con_ofertas = cliente.get("/clientes/", {"ofertas": "con"})
comprobar("filtro «con ofertas»", all(e.total_ofertas > 0 for e in con_ofertas.context["empresas"]),
          f" ({len(con_ofertas.context['empresas'])} empresas)")
sin_ofertas = cliente.get("/clientes/", {"ofertas": "sin"})
comprobar("filtro «sin ofertas»", all(e.total_ofertas == 0 for e in sin_ofertas.context["empresas"]))
comprobar("la ficha muestra las ofertas", cliente.get(f"/clientes/{empresa.pk}/").status_code == 200)

alta = cliente.post("/clientes/nuevo/", {
    "ruc": RUC, "razon_social": "E2E Cliente S.A.C.",
    "direccion": "Av. Prueba 123", "actividad_economica": "Comercio",
})
creada = EmpresaCliente.objects.filter(ruc=RUC).first()
comprobar("alta válida (302)", alta.status_code == 302 and creada is not None)
duplicado = cliente.post("/clientes/nuevo/", {
    "ruc": RUC, "razon_social": "Otro nombre", "direccion": "x", "actividad_economica": "x",
})
comprobar("RUC duplicado rechazado",
          duplicado.status_code == 200 and "Ya existe una empresa cliente" in duplicado.content.decode("utf-8"))
edicion = cliente.post(f"/clientes/{creada.pk}/editar/", {
    "ruc": RUC, "razon_social": "E2E Cliente Editado S.A.C.",
    "direccion": "Av. Prueba 456", "actividad_economica": "Servicios",
})
creada.refresh_from_db()
comprobar("edición aceptada", edicion.status_code == 302 and creada.razon_social == "E2E Cliente Editado S.A.C.")

print("OFERTAS DE CARGA")
listado_ofertas = cliente.get("/ofertas/")
comprobar("listado 200", listado_ofertas.status_code == 200)
comprobar("muestra el estado de cada oferta",
          "Disponible" in listado_ofertas.content.decode("utf-8")
          and "Cubierta" in listado_ofertas.content.decode("utf-8"))
por_empresa = cliente.get("/ofertas/", {"empresa": empresa.pk})
comprobar("filtro por empresa cliente", all(o.empresa_cliente_id == empresa.pk for o in por_empresa.context["ofertas"]))
por_estado = cliente.get("/ofertas/", {"estado": EstadoOferta.DISPONIBLE})
comprobar("filtro por estado", all(o.estado == EstadoOferta.DISPONIBLE for o in por_estado.context["ofertas"]))
por_nivel = cliente.get("/ofertas/", {"nivel": NivelCarga.NIVEL_1})
comprobar("filtro por nivel", all(o.nivel_requerido == NivelCarga.NIVEL_1 for o in por_nivel.context["ofertas"]))
una = OfertaCarga.objects.first()
comprobar("búsqueda por código", list(cliente.get("/ofertas/", {"q": una.codigo}).context["ofertas"]) == [una])
comprobar("búsqueda por origen", len(cliente.get("/ofertas/", {"q": una.origen}).context["ofertas"]) >= 1)
comprobar("búsqueda por destino", len(cliente.get("/ofertas/", {"q": una.destino}).context["ofertas"]) >= 1)

alta_oferta = cliente.post("/ofertas/nueva/", {
    "empresa_cliente": creada.pk, "origen": "Lima", "destino": "Tacna",
    "tipo_vehiculo_requerido": TipoVehiculo.CAMION, "nivel_requerido": NivelCarga.NIVEL_2,
    "remuneracion": "1850.75",
})
nueva = OfertaCarga.objects.filter(destino="Tacna").first()
comprobar("alta válida con código autogenerado (302)",
          alta_oferta.status_code == 302 and nueva is not None and nueva.codigo.startswith("OF-"))
comprobar("importe decimal guardado", nueva.remuneracion == Decimal("1850.75"))
comprobar("estado inicial Disponible", nueva.estado == EstadoOferta.DISPONIBLE)

sin_empresa = cliente.post("/ofertas/nueva/", {
    "empresa_cliente": "", "origen": "Lima", "destino": "Piura",
    "tipo_vehiculo_requerido": TipoVehiculo.CAMION, "nivel_requerido": NivelCarga.NIVEL_2,
    "remuneracion": "1000.00",
})
comprobar("empresa obligatoria", "empresa_cliente" in sin_empresa.context["form"].errors)
negativo = cliente.post("/ofertas/nueva/", {
    "empresa_cliente": creada.pk, "origen": "Lima", "destino": "Piura",
    "tipo_vehiculo_requerido": TipoVehiculo.CAMION, "nivel_requerido": NivelCarga.NIVEL_2,
    "remuneracion": "-50.00",
})
comprobar("importe negativo rechazado", "remuneracion" in negativo.context["form"].errors)

edicion_oferta = cliente.post(f"/ofertas/{nueva.pk}/editar/", {
    "empresa_cliente": creada.pk, "origen": "Lima", "destino": "Tacna",
    "tipo_vehiculo_requerido": TipoVehiculo.CAMION, "nivel_requerido": NivelCarga.NIVEL_3,
    "remuneracion": "1900.00",
})
nueva.refresh_from_db()
comprobar("edición de una oferta disponible", edicion_oferta.status_code == 302 and nueva.nivel_requerido == NivelCarga.NIVEL_3)

confirmacion = cliente.get(f"/ofertas/{nueva.pk}/estado/")
comprobar("pantalla de confirmación de estado", confirmacion.status_code == 200
          and "Confirmar cambio de estado" in confirmacion.content.decode("utf-8"))
cambio = cliente.post(f"/ofertas/{nueva.pk}/estado/", {"estado": EstadoOferta.CUBIERTA})
nueva.refresh_from_db()
comprobar("cambio de estado aplicado", cambio.status_code == 302 and nueva.estado == EstadoOferta.CUBIERTA)
vuelta = cliente.post(f"/ofertas/{nueva.pk}/estado/", {"estado": EstadoOferta.DISPONIBLE})
nueva.refresh_from_db()
comprobar("una oferta cubierta a mano puede volver a Disponible",
          vuelta.status_code == 302 and nueva.estado == EstadoOferta.DISPONIBLE)

print("REGLA DE OFERTA YA ASIGNADA")
asignada = OfertaCarga.objects.filter(estado=EstadoOferta.CUBIERTA).first()
comprobar("existe una oferta cubierta con asignación en los datos demo", asignada is not None)
bloqueo = cliente.post(f"/ofertas/{asignada.pk}/editar/", {
    "empresa_cliente": asignada.empresa_cliente_id, "origen": asignada.origen, "destino": asignada.destino,
    "tipo_vehiculo_requerido": asignada.tipo_vehiculo_requerido, "nivel_requerido": NivelCarga.NIVEL_3,
    "remuneracion": str(asignada.remuneracion),
})
comprobar("se bloquea cambiar el nivel requerido", bloqueo.status_code == 200
          and "invalidaría la asignación existente" in bloqueo.content.decode("utf-8"))
sin_disponible = cliente.post(f"/ofertas/{asignada.pk}/estado/", {"estado": EstadoOferta.DISPONIBLE})
comprobar("no puede volver a Disponible estando asignada",
          sin_disponible.status_code == 200 and "no puede volver a «Disponible»" in sin_disponible.content.decode("utf-8"))

print("LIMPIEZA")
OfertaCarga.objects.filter(pk=nueva.pk).delete()
EmpresaCliente.objects.filter(ruc=RUC).delete()
comprobar("base demo igual", EmpresaCliente.objects.count() == total_empresas and OfertaCarga.objects.count() == total_ofertas,
          f" ({EmpresaCliente.objects.count()}/{total_empresas} empresas, {OfertaCarga.objects.count()}/{total_ofertas} ofertas)")
usuario.delete()
teardown_test_environment()
print(f"\nFALLOS: {fallos}")

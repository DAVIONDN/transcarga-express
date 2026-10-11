"""Verificación de las pantallas con los datos reales (solo lectura).

Crea un usuario temporal con contraseña inutilizable, recorre las pantallas y lo
elimina al terminar. No modifica ningún registro de negocio.
"""

from django.test.utils import setup_test_environment

setup_test_environment()

from django.contrib.auth import get_user_model  # noqa: E402
from django.test import Client  # noqa: E402

from asignaciones.models import Asignacion  # noqa: E402
from clientes.models import EmpresaCliente  # noqa: E402
from ofertas.models import OfertaCarga  # noqa: E402
from transportistas.models import Advertencia, Transportista  # noqa: E402

USUARIO_TEMPORAL = "verificacion_temporal_auditoria"

Usuario = get_user_model()
usuario = Usuario.objects.create_user(username=USUARIO_TEMPORAL, password=None)  # sin contraseña usable

fallos = 0
try:
    cliente = Client()
    cliente.force_login(usuario)

    activo = Transportista.objects.filter(estado="ACTIVO").order_by("pk").first()
    print(f"=== identificadores reales: transportistas pk {Transportista.objects.order_by('pk').first().pk}"
          f"–{Transportista.objects.order_by('pk').last().pk}; se usará pk {activo.pk} en las pruebas ===")
    rutas = [
        "/",
        "/transportistas/",
        "/transportistas/?estado=BAJA",
        "/transportistas/?estado=EN_RESERVA",
        "/transportistas/?nivel=1",
        f"/transportistas/{activo.pk}/",
        "/transportistas/advertencias/",
        "/transportistas/advertencias/?transportista=6",
        "/clientes/",
        "/clientes/1/",
        "/ofertas/",
        "/ofertas/?estado=DISPONIBLE&nivel=1",
        "/ofertas/5/",
        "/ofertas/5/asignar/",
        "/asignaciones/",
        "/asignaciones/?estado=CANCELADA",
        "/asignaciones/?estado=FINALIZADA",
        "/asignaciones/1/",
    ]
    print("=== pantallas con los datos reales ===")
    for ruta in rutas:
        respuesta = cliente.get(ruta)
        estado = respuesta.status_code
        if estado != 200:
            fallos += 1
        print(f"  {estado}  {ruta}  ({len(respuesta.content)} bytes)")

    print("=== panel contra la base de datos ===")
    respuesta = cliente.get("/")
    contexto = respuesta.context
    comprobaciones = [
        ("total_transportistas", contexto["total_transportistas"], Transportista.objects.count()),
        ("transportistas_activos", contexto["transportistas_activos"], Transportista.objects.filter(estado="ACTIVO").count()),
        ("transportistas_reserva", contexto["transportistas_reserva"], Transportista.objects.filter(estado="EN_RESERVA").count()),
        ("transportistas_baja", contexto["transportistas_baja"], Transportista.objects.filter(estado="BAJA").count()),
        ("total_clientes", contexto["total_clientes"], EmpresaCliente.objects.count()),
        ("ofertas_disponibles", contexto["ofertas_disponibles"], OfertaCarga.objects.filter(estado="DISPONIBLE").count()),
        ("ofertas_cubiertas", contexto["ofertas_cubiertas"], OfertaCarga.objects.filter(estado="CUBIERTA").count()),
        ("asignaciones_activas", contexto["asignaciones_activas"], Asignacion.objects.filter(estado="ACTIVA").count()),
        ("advertencias_recientes", len(contexto["advertencias_recientes"]), min(Advertencia.objects.count(), 5)),
        ("transportistas_de_baja", len(contexto["transportistas_de_baja"]), Transportista.objects.filter(estado="BAJA").count()),
        ("vencimientos (máx. 10)", len(contexto["vencimientos"]), min(10, sum(len(t.documentos_por_vencer()) for t in Transportista.objects.all()))),
    ]
    for nombre, obtenido, esperado in comprobaciones:
        marca = "OK " if obtenido == esperado else "FALLO"
        if obtenido != esperado:
            fallos += 1
        print(f"  {marca} {nombre}: panel={obtenido} base={esperado}")

    for fila in contexto["conteo_por_nivel"]:
        esperado = Transportista.objects.filter(nivel=fila["nivel"]).count()
        marca = "OK " if fila["total"] == esperado else "FALLO"
        if fila["total"] != esperado:
            fallos += 1
        print(f"  {marca} nivel {fila['nivel']}: panel={fila['total']} base={esperado}")

    print("=== paginación con 17 transportistas ===")
    pagina_1 = cliente.get("/transportistas/")
    pagina_2 = cliente.get("/transportistas/", {"page": 2})
    print(f"  página 1: {len(pagina_1.context['transportistas'])} filas")
    print(f"  página 2: {len(pagina_2.context['transportistas'])} filas (status {pagina_2.status_code})")
    if pagina_1.context["paginator"].num_pages != 2:
        fallos += 1
        print("  FALLO: se esperaban 2 páginas")

    print("=== estados en la interfaz ===")
    print(f"  Asignaciones activas/finalizadas/canceladas en pantalla: "
          f"{'activa' in cliente.get('/asignaciones/').content.decode()} ...")
    detalle = cliente.get("/asignaciones/")
    for etiqueta in ("Activa", "Finalizada", "Cancelada"):
        presente = etiqueta in detalle.content.decode()
        print(f"  {'OK ' if presente else 'FALLO'} aparece «{etiqueta}» en el listado")
        if not presente:
            fallos += 1
finally:
    usuario.delete()
    sigue = Usuario.objects.filter(username=USUARIO_TEMPORAL).exists()
    print(f"usuario temporal eliminado: {not sigue}")

print(f"\nRESULTADO: {'sin fallos' if fallos == 0 else str(fallos) + ' fallo(s)'}")

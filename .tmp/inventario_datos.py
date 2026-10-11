"""Inventario legible de los datos cargados (solo lectura)."""

from django.contrib.auth import get_user_model

from asignaciones.models import Asignacion
from clientes.models import EmpresaCliente
from ofertas.models import OfertaCarga
from transportistas.models import Advertencia, Transportista

print("=== EMPRESAS CLIENTES ===")
for empresa in EmpresaCliente.objects.order_by("pk"):
    print(f"  [{empresa.pk}] RUC {empresa.ruc} · {empresa.razon_social} · {empresa.actividad_economica}")

print("=== TRANSPORTISTAS ===")
for t in Transportista.objects.order_by("pk"):
    asignacion = t.asignacion_activa
    print(
        f"  [{t.pk}] {t.nombre} | {t.get_tipo_documento_display()} {t.numero_documento} | "
        f"{t.placa} | {t.get_tipo_vehiculo_display()} {t.capacidad_toneladas} t | "
        f"Nivel {t.nivel} | {t.get_estado_display()} | advertencias {t.advertencias_total} | "
        f"asignacion activa: {asignacion.oferta.codigo if asignacion else '—'} | "
        f"cert. peligrosa: {'si' if t.certificacion_carga_peligrosa else 'no'}"
    )
    print(
        f"        licencia {t.fecha_vencimiento_licencia:%d/%m/%Y} "
        f"({'vigente' if t.licencia_vigente else 'VENCIDA'}) · "
        f"RT {t.fecha_vencimiento_revision_tecnica:%d/%m/%Y} "
        f"({'vigente' if t.revision_tecnica_vigente else 'VENCIDA'}) · "
        f"SOAT {t.fecha_vencimiento_soat:%d/%m/%Y} "
        f"({'vigente' if t.soat_vigente else 'VENCIDO'})"
    )

print("=== OFERTAS DE CARGA ===")
for o in OfertaCarga.objects.order_by("codigo"):
    asignacion = getattr(o, "asignacion", None)
    print(
        f"  [{o.pk}] {o.codigo} | {o.empresa_cliente.razon_social} | {o.origen} -> {o.destino} | "
        f"{o.get_tipo_vehiculo_requerido_display()} | Nivel {o.nivel_requerido} | "
        f"S/ {o.remuneracion} | {o.get_estado_display()} | "
        f"transportista: {asignacion.transportista.nombre if asignacion else '—'}"
    )

print("=== ASIGNACIONES ===")
for a in Asignacion.objects.order_by("pk"):
    print(
        f"  [{a.pk}] {a.oferta.codigo} -> {a.transportista.nombre} | {a.get_estado_display()} | "
        f"inicio {a.fecha_inicio:%d/%m/%Y} | fin {a.fecha_fin:%d/%m/%Y}" if a.fecha_fin
        else f"  [{a.pk}] {a.oferta.codigo} -> {a.transportista.nombre} | {a.get_estado_display()} | "
             f"inicio {a.fecha_inicio:%d/%m/%Y} | en curso"
    )

print("=== ADVERTENCIAS ===")
for ad in Advertencia.objects.order_by("-fecha", "-id"):
    print(f"  [{ad.pk}] {ad.fecha:%d/%m/%Y} | {ad.transportista.nombre} | {ad.descripcion[:70]}")

print("=== USUARIOS ===")
print(f"  {get_user_model().objects.count()} usuario(s)")

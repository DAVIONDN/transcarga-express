"""Recurso temporal: verifica usuarios, grupos y datos demo (sin credenciales)."""

from django.contrib.auth import get_user_model
from asignaciones.models import Asignacion
from auditoria.models import RegistroAuditoria
from capacitacion.models import Curso, Participacion
from clientes.models import EmpresaCliente
from liquidaciones.models import FormatoSemanal, Liquidacion
from ofertas.models import OfertaCarga
from transportistas.models import Advertencia, Incidencia, Transportista

Usuario = get_user_model()
print("== usuarios ==")
for u in Usuario.objects.order_by("username"):
    grupos = sorted(u.groups.values_list("name", flat=True))
    print(f"{u.username} | super={u.is_superuser} | activo={u.is_active} "
          f"| grupos={grupos} | clave_utilizable={u.has_usable_password()}")

print("== datos ==")
print("clientes:", EmpresaCliente.objects.count(),
      "| transportistas:", Transportista.objects.count(),
      "| ofertas:", OfertaCarga.objects.count(),
      "| asignaciones:", Asignacion.objects.count(),
      "| advertencias:", Advertencia.objects.count(),
      "| incidencias:", Incidencia.objects.count(),
      "| formatos:", FormatoSemanal.objects.count(),
      "| liquidaciones:", Liquidacion.objects.count(),
      "| cursos:", Curso.objects.count(),
      "| participaciones:", Participacion.objects.count(),
      "| auditoria:", RegistroAuditoria.objects.count())

print("== permisos por rol ==")
for username, permiso in (("administrador", "auth.view_user"),
                          ("operador", "transportistas.add_transportista"),
                          ("consulta", "ofertas.view_ofertacarga")):
    u = Usuario.objects.get(username=username)
    print(f"{username}: {permiso}={u.has_perm(permiso)}")
op = Usuario.objects.get(username="operador")
print("operador ve auditoria (debe ser False):", op.has_perm("auditoria.ver_auditoria"))
admin = Usuario.objects.get(username="administrador")
print("administrador ve auditoria:", admin.has_perm("auditoria.ver_auditoria"))

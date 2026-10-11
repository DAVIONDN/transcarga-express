"""Roles y permisos de TransCarga Express (fuente única de verdad).

Los roles se materializan como **grupos de Django** (exclusivos: cada usuario
pertenece a un solo grupo de rol). Los permisos son los nativos de Django: los
`view_*`/`add_*`/`change_*` de cada modelo más permisos personalizados declarados
en `Meta.permissions` (cambiar estado, finalizar y cancelar).

Política de seguridad:

* Los **superusuarios eluden los permisos** (comportamiento nativo de Django), por
  lo que es obligatorio conservar al menos un superusuario.
* Un usuario **inactivo** no puede autenticarse (lo garantiza `AuthenticationForm`)
  y, además, `has_perm` devuelve `False` para usuarios inactivos.
* El rol se asigna con `asignar_rol()` (un único grupo); nunca se confía en
  identificadores enviados por el navegador para decidir quién realiza la acción.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.shortcuts import render

GRUPO_ADMINISTRADOR = "Administrador"
GRUPO_OPERADOR = "Operador"
GRUPO_CONSULTA = "Consulta"

GRUPOS_DE_ROL = (GRUPO_ADMINISTRADOR, GRUPO_OPERADOR, GRUPO_CONSULTA)

# Permisos personalizados: (app_label, modelo, codename, nombre legible).
# También se declaran en Meta.permissions de cada modelo (migración); aquí se
# repiten para que el comando pueda crearlos de forma defensiva e idempotente.
PERMISOS_PERSONALIZADOS = (
    (
        "transportistas",
        "Transportista",
        "cambiar_estado_transportista",
        "Puede cambiar el estado de un transportista.",
    ),
    (
        "ofertas",
        "OfertaCarga",
        "cambiar_estado_oferta",
        "Puede cambiar el estado de una oferta de carga.",
    ),
    (
        "asignaciones",
        "Asignacion",
        "finalizar_asignacion",
        "Puede finalizar una asignación.",
    ),
    (
        "asignaciones",
        "Asignacion",
        "cancelar_asignacion",
        "Puede cancelar una asignación.",
    ),
    (
        "liquidaciones",
        "FormatoSemanal",
        "generar_formatos",
        "Puede generar los formatos semanales.",
    ),
    (
        "liquidaciones",
        "FormatoSemanal",
        "firmar_formato",
        "Puede registrar la firma de un formato.",
    ),
    (
        "liquidaciones",
        "Liquidacion",
        "generar_liquidacion",
        "Puede generar liquidaciones en borrador.",
    ),
    (
        "liquidaciones",
        "Liquidacion",
        "cerrar_liquidacion",
        "Puede cerrar una liquidación.",
    ),
    (
        "liquidaciones",
        "ParametrosLiquidacion",
        "configurar_liquidacion",
        "Puede configurar los parámetros financieros.",
    ),
    (
        "capacitacion",
        "Participacion",
        "finalizar_participacion",
        "Puede confirmar la finalización de una participación.",
    ),
    (
        "auditoria",
        "RegistroAuditoria",
        "ver_auditoria",
        "Puede consultar la auditoría de operaciones.",
    ),
)


def _permisos_crud():
    """Permisos view/add/change de los modelos de negocio."""
    codigos = []
    for app_label, modelo in (
        ("transportistas", "transportista"),
        ("transportistas", "advertencia"),
        ("clientes", "empresacliente"),
        ("ofertas", "ofertacarga"),
    ):
        for accion in ("view", "add", "change"):
            codigos.append(f"{app_label}.{accion}_{modelo}")
    # La asignación no se edita: solo se ve y se crea (finalizar/cancelar son permisos propios).
    for accion in ("view", "add"):
        codigos.append(f"asignaciones.{accion}_asignacion")
    return codigos


def _permisos_personalizados():
    # `ver_auditoria` se crea por migración y red de seguridad, pero solo se
    # otorga al Administrador (lista explícita): no entra aquí para que el
    # Operador no la reciba.
    return [
        f"{app}.{codename}"
        for app, _, codename, _ in PERMISOS_PERSONALIZADOS
        if codename != "ver_auditoria"
    ]


# Permisos financieros (liquidaciones): ver, operar y configurar.
PERMISOS_LIQUIDACIONES_VISTA = [
    "liquidaciones.view_formatosemanal",
    "liquidaciones.view_liquidacion",
]
PERMISOS_LIQUIDACIONES_OPERATIVOS = [
    "liquidaciones.generar_formatos",
    "liquidaciones.firmar_formato",
    "liquidaciones.generar_liquidacion",
    "liquidaciones.cerrar_liquidacion",
]
PERMISO_LIQUIDACIONES_CONFIGURAR = "liquidaciones.configurar_liquidacion"


# Permisos de capacitación: ver, operar y confirmar finalizaciones.
PERMISOS_CAPACITACION_VISTA = [
    "capacitacion.view_curso",
    "capacitacion.view_participacion",
]
PERMISOS_CAPACITACION_OPERATIVOS = [
    "capacitacion.add_curso",
    "capacitacion.change_curso",
    "capacitacion.add_participacion",
    "capacitacion.finalizar_participacion",
]

# Auditoría: solo el Administrador la consulta.
PERMISO_VER_AUDITORIA = "auditoria.ver_auditoria"


PERMISOS_ADMINISTRADOR = sorted(
    set(
        _permisos_crud()
        + _permisos_personalizados()
        + ["auth.view_user", "auth.add_user", "auth.change_user"]
        + PERMISOS_LIQUIDACIONES_VISTA
        + PERMISOS_LIQUIDACIONES_OPERATIVOS
        + [PERMISO_LIQUIDACIONES_CONFIGURAR]
        + PERMISOS_CAPACITACION_VISTA
        + PERMISOS_CAPACITACION_OPERATIVOS
        + [PERMISO_VER_AUDITORIA]
    )
)
PERMISOS_OPERADOR = sorted(
    set(
        _permisos_crud()
        + _permisos_personalizados()
        + PERMISOS_LIQUIDACIONES_VISTA
        + PERMISOS_LIQUIDACIONES_OPERATIVOS
        + PERMISOS_CAPACITACION_VISTA
        + PERMISOS_CAPACITACION_OPERATIVOS
    )
)
PERMISOS_CONSULTA = [
    "transportistas.view_transportista",
    "transportistas.view_advertencia",
    "clientes.view_empresacliente",
    "ofertas.view_ofertacarga",
    "asignaciones.view_asignacion",
] + PERMISOS_LIQUIDACIONES_VISTA + PERMISOS_CAPACITACION_VISTA

# Matriz de permisos por rol (ver docs/DECISIONES.md).
PERMISOS_POR_ROL = {
    GRUPO_ADMINISTRADOR: PERMISOS_ADMINISTRADOR,
    GRUPO_OPERADOR: PERMISOS_OPERADOR,
    GRUPO_CONSULTA: PERMISOS_CONSULTA,
}


def _asegurar_permisos_personalizados():
    """Crea los permisos personalizados si no existen (idempotente).

    En condiciones normales los crea la migración de `Meta.permissions`; esto es
    una red de seguridad para que el comando funcione aunque falten.
    """
    from django.apps import apps

    for app_label, modelo, codename, nombre in PERMISOS_PERSONALIZADOS:
        modelo_clase = apps.get_model(app_label, modelo)
        content_type = ContentType.objects.get_for_model(modelo_clase)
        Permission.objects.get_or_create(
            codename=codename,
            content_type=content_type,
            defaults={"name": nombre},
        )


def _permisos_de_grupo(nombre_rol):
    permisos = []
    for codigo in PERMISOS_POR_ROL[nombre_rol]:
        app_label, codename = codigo.split(".", 1)
        permisos.append(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )
    return permisos


def inicializar_roles_y_permisos():
    """Crea los grupos de rol y les asigna sus permisos (idempotente).

    Solo **añade** permisos; nunca elimina permisos personalizados ya asignados ni
    cambia los grupos de los usuarios existentes.
    """
    _asegurar_permisos_personalizados()
    grupos = {}
    for nombre in GRUPOS_DE_ROL:
        grupo, _ = Group.objects.get_or_create(name=nombre)
        grupo.permissions.add(*_permisos_de_grupo(nombre))
        grupos[nombre] = grupo
    return grupos


def roles_disponibles():
    """Opciones de rol para formularios (nombre legible == nombre del grupo)."""
    return [(nombre, nombre) for nombre in GRUPOS_DE_ROL]


def rol_de(usuario):
    """Rol visible de un usuario (los superusuarios tienen acceso total)."""
    if usuario.is_superuser:
        return "Superusuario"
    grupo = usuario.groups.filter(name__in=GRUPOS_DE_ROL).first()
    return grupo.name if grupo else "Sin rol"


def asignar_rol(usuario, nombre_rol):
    """Asigna un único grupo de rol (política de roles exclusivos)."""
    if nombre_rol not in GRUPOS_DE_ROL:
        raise ValueError(f"Rol desconocido: {nombre_rol}")
    usuario.groups.set([Group.objects.get(name=nombre_rol)])


def es_administrador(usuario):
    return usuario.is_superuser or usuario.groups.filter(name=GRUPO_ADMINISTRADOR).exists()


def es_ultimo_administrador_activo(usuario):
    """True si `usuario` es el único administrador activo (no se puede degradar)."""
    if not usuario.is_active or not es_administrador(usuario):
        return False
    otros_activos = (
        get_user_model()
        .objects.filter(is_active=True)
        .exclude(pk=usuario.pk)
        .filter(Q(is_superuser=True) | Q(groups__name=GRUPO_ADMINISTRADOR))
        .distinct()
    )
    return not otros_activos.exists()


def puede_gestionar_cuenta(actor, objetivo):
    """True si `actor` puede administrar la cuenta `objetivo`.

    Política: solo un **superusuario** puede editar, activar/desactivar o
    restablecer la contraseña de otra cuenta con privilegios de superusuario. Así
    un Administrador (no superusuario) no puede escalar privilegios apoderándose de
    una cuenta de superusuario (por ejemplo, restableciendo su contraseña).
    """
    if actor.is_superuser:
        return True
    return not objetivo.is_superuser


class PermisoRequeridoMixin(LoginRequiredMixin):
    """Exige sesión iniciada y un permiso concreto, tanto en GET como en POST.

    * Anónimo → redirige al inicio de sesión (comportamiento de `LoginRequiredMixin`).
    * Autenticado sin permiso → responde 403 con una plantilla clara.
    * Superusuario → pasa siempre (permiso nativo de Django).
    """

    permiso_requerido = None
    permisos_requeridos = None

    def tiene_permiso(self):
        if self.permisos_requeridos:
            return all(
                self.request.user.has_perm(permiso) for permiso in self.permisos_requeridos
            )
        if self.permiso_requerido is None:
            return True
        return self.request.user.has_perm(self.permiso_requerido)

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not self.tiene_permiso():
            return self._denegar()
        return super().dispatch(request, *args, **kwargs)

    def _denegar(self):
        requerido = self.permiso_requerido
        if self.permisos_requeridos:
            requerido = ", ".join(self.permisos_requeridos)
        return render(
            self.request,
            "403.html",
            {
                "titulo": "Acceso denegado",
                "permiso_requerido": requerido,
            },
            status=403,
        )

"""Ajustes del panel de administración de Django para las cuentas de usuario.

Las cuentas **no se eliminan** nunca: se activan o desactivan desde la aplicación
(`/usuarios/<pk>/estado/`). Se desactiva el borrado también en el panel de
administración para no dejar huérfanas las operaciones históricas (por ejemplo,
`Advertencia.registrado_por`, que además usa `PROTECT`).
"""

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

Usuario = get_user_model()


class UsuarioAdmin(UserAdmin):
    """Administración de usuarios sin permiso de borrado."""

    def has_delete_permission(self, request, obj=None):
        return False


try:
    admin.site.unregister(Usuario)
except admin.sites.NotRegistered:
    pass

admin.site.register(Usuario, UsuarioAdmin)

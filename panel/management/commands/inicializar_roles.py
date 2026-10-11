"""Comando idempotente: crea los grupos de rol y les asigna sus permisos.

No asigna roles a los usuarios existentes y no toca contraseñas. Los superusuarios
eluden los permisos (Django), de modo que el acceso del administrador actual se
conserva. Ejecútelo una vez tras `migrate` (y cada vez que cambie la matriz):

    python manage.py inicializar_roles
"""

from django.core.management.base import BaseCommand

from comun.permisos import inicializar_roles_y_permisos


class Command(BaseCommand):
    help = (
        "Crea los grupos Administrador, Operador y Consulta y les asigna sus permisos. "
        "Es idempotente: no duplica grupos ni elimina permisos personalizados."
    )

    def handle(self, *args, **opciones):
        grupos = inicializar_roles_y_permisos()

        self.stdout.write(self.style.SUCCESS("Roles y permisos inicializados:"))
        for nombre, grupo in grupos.items():
            self.stdout.write(f"  - {nombre}: {grupo.permissions.count()} permiso(s)")

        self.stdout.write("")
        self.stdout.write("Los superusuarios eluden los permisos (comportamiento nativo de Django).")
        self.stdout.write("Asigne roles desde la pantalla de usuarios (solo Administrador) o con:")
        self.stdout.write(
            '  manage.py shell -c "from django.contrib.auth.models import User, Group; '
            "u = User.objects.get(username='MI_USUARIO'); "
            "u.groups.set([Group.objects.get(name='Operador')])\""
        )

"""Recurso temporal: crea usuarios demo por rol con claves aleatorias.

Las claves se generan con `secrets` y solo se muestran por salida estándar una
vez: nunca quedan en comandos, archivos ni datos demo.
"""

import secrets

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

Usuario = get_user_model()

CUENTAS = (
    ("administrador", "Administrador"),
    ("operador", "Operador"),
    ("consulta", "Consulta"),
)

for username, rol in CUENTAS:
    usuario, creado = Usuario.objects.get_or_create(
        username=username,
        defaults={
            "first_name": username.capitalize(),
            "is_active": True,
        },
    )
    usuario.groups.set([Group.objects.get(name=rol)])
    if creado:
        clave = secrets.token_urlsafe(12)
        usuario.set_password(clave)
        usuario.save()
        print(f"NUEVO {username} | rol={rol} | clave={clave}")
    else:
        print(f"EXISTE {username} | rol={rol} (clave sin cambios)")

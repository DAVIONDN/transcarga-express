"""Recurso temporal: lista usuarios sin exponer credenciales."""

from django.contrib.auth import get_user_model

Usuario = get_user_model()
for u in Usuario.objects.order_by("username"):
    grupos = sorted(u.groups.values_list("name", flat=True))
    print(f"{u.username} | super={u.is_superuser} | staff={u.is_staff} "
          f"| activo={u.is_active} | grupos={grupos} | ultimo={u.last_login}")
print("total:", Usuario.objects.count())

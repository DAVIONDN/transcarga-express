from django.contrib.auth import get_user_model

U = get_user_model()
print("usuarios:", U.objects.count())
for u in U.objects.order_by("pk"):
    print(
        f"  {u.username} | superuser={u.is_superuser} | staff={u.is_staff} | "
        f"activo={u.is_active} | grupos={list(u.groups.values_list('name', flat=True))} | "
        f"last_login={u.last_login}"
    )

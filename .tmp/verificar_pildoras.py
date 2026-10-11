"""Recurso temporal: verifica las pildoras del filtro de asignaciones."""

import re

from django.conf import settings
from django.test import Client
from django.test.utils import setup_test_environment

setup_test_environment()
if "testserver" not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]

from django.contrib.auth import get_user_model  # noqa: E402

cliente = Client()
cliente.force_login(get_user_model().objects.get(username="mariano"))
for ruta in ("/asignaciones/", "/asignaciones/?estado=ACTIVA"):
    respuesta = cliente.get(ruta)
    html = respuesta.content.decode()
    pildoras = re.findall(r'class="tc-pildora[^"]*"[^>]*>(.*?)</a>', html, re.S)
    print(ruta, "HTTP:", respuesta.status_code)
    for pildora in pildoras:
        print("-", re.sub(r"<[^>]+>", "", pildora).strip())
    print("activa marcada:", 'aria-current="page"' in html)

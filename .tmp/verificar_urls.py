"""Recurso temporal: verifica que cada {% url %} de las plantillas resuelva."""

import pathlib
import re

from django.urls import NoReverseMatch, reverse

nombres = set()
for archivo in pathlib.Path("templates").rglob("*.html"):
    texto = archivo.read_text(encoding="utf-8")
    nombres.update(re.findall(r"{% url '([^']+)'", texto))

fallos = []
for nombre in sorted(nombres):
    for cantidad in (0, 1, 2):
        try:
            reverse(nombre, args=[1] * cantidad)
            break
        except NoReverseMatch:
            continue
    else:
        fallos.append(nombre)

print("urls usadas:", len(nombres))
print("fallos:", fallos if fallos else "ninguno")

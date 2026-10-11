"""Inspección (solo lectura) del registro de modelos en Django Admin."""

import os
import sys
from pathlib import Path

import django

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib import admin  # noqa: E402

from asignaciones.models import Asignacion  # noqa: E402
from clientes.models import EmpresaCliente  # noqa: E402
from ofertas.models import OfertaCarga  # noqa: E402
from transportistas.models import Advertencia, Transportista  # noqa: E402

for modelo in (Transportista, Advertencia, EmpresaCliente, OfertaCarga, Asignacion):
    clase = admin.site._registry.get(modelo)
    if clase is None:
        print(f"NO REGISTRADO: {modelo.__name__}")
        continue
    meta = modelo._meta
    print(f"{modelo.__name__}")
    print(f"    verbose_name        : {meta.verbose_name!r} / {meta.verbose_name_plural!r}")
    print(f"    columnas (list)     : {list(clase.list_display)}")
    print(f"    filtros (list_filter): {list(clase.list_filter)}")
    print(f"    busqueda            : {list(clase.search_fields)}")
    print(f"    restricciones BD    : {[c.name for c in meta.constraints]}")

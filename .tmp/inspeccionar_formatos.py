"""Inspección (solo lectura) de idioma, zona horaria y formatos efectivos."""

import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import django

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings  # noqa: E402
from django.template import Context, Template  # noqa: E402
from django.utils import formats, translation  # noqa: E402

print("LANGUAGE_CODE   :", settings.LANGUAGE_CODE)
print("TIME_ZONE       :", settings.TIME_ZONE)
print("USE_I18N/USE_TZ :", settings.USE_I18N, "/", settings.USE_TZ)
print("locale es_PE    :", os.path.isdir(os.path.join(django.__path__[0], "conf", "locale", "es_PE")))

with translation.override(settings.LANGUAGE_CODE):
    print("Idioma activo   :", translation.get_language())
    for nombre in (
        "DATE_FORMAT",
        "SHORT_DATE_FORMAT",
        "DATETIME_FORMAT",
        "DATE_INPUT_FORMATS",
        "DECIMAL_SEPARATOR",
        "THOUSAND_SEPARATOR",
        "NUMBER_GROUPING",
    ):
        print(f"{nombre:17}: {formats.get_format(nombre)}")
    print("date_format()   :", formats.date_format(date(2026, 10, 9)))

print("{{ remuneracion }} :", Template("S/ {{ valor }}").render(Context({"valor": Decimal("2500.00")})))
print("{{ remun|floatformat:2 }} :", Template("S/ {{ valor|floatformat:2 }}").render(Context({"valor": Decimal("2500.00")})))
print("{{ fecha|date }} :", Template("{{ valor|date }}").render(Context({"valor": date(2026, 10, 9)})))
print("{{ fecha|date:'d/m/Y' }} :", Template("{{ valor|date:'d/m/Y' }}").render(Context({"valor": date(2026, 10, 9)})))

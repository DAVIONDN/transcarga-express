"""Formatos para el locale `es` (alias de los peruanos).

Django no incluye el locale `es_PE`. Al activarse `LANGUAGE_CODE = "es-pe"`, Django
resuelve el idioma al locale `es` y busca los formatos en `formats/es/formats.py`,
por lo que este módulo reexporta los valores definidos en `formats/es_PE/formats.py`
y así se aplican tanto si el locale activo es `es` como si es `es_PE`.
"""

from formats.es_PE.formats import *  # noqa: F401,F403

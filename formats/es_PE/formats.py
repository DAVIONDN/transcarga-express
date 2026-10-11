"""Formatos regionales para es-PE (Perú).

Django no incluye un módulo de formatos para `es_PE`, por lo que sin este paquete
la interfaz hereda los de `es` (España): fecha larga «9 de octubre de 2026» y
separador decimal coma («2500,00»), que no corresponden al uso peruano.

Django carga este módulo cuando `LANGUAGE_CODE = "es-pe"` y
`FORMAT_MODULE_PATH = ["formats"]` (ver config/settings.py).

Convenciones aplicadas: fecha corta dd/mm/aaaa, separador decimal punto y
separador de miles coma.
"""

DATE_FORMAT = "d/m/Y"
SHORT_DATE_FORMAT = "d/m/Y"
DATETIME_FORMAT = "d/m/Y H:i"
SHORT_DATETIME_FORMAT = "d/m/Y H:i"
TIME_FORMAT = "H:i"

# Se mantienen los formatos de ingreso que ya aceptaba el locale `es`: fecha ISO
# (la que envían los campos HTML5 tipo date) y fecha escrita como dd/mm/aaaa.
DATE_INPUT_FORMATS = ["%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"]
DATETIME_INPUT_FORMATS = [
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
]
TIME_INPUT_FORMATS = ["%H:%M:%S", "%H:%M"]

DECIMAL_SEPARATOR = "."
THOUSAND_SEPARATOR = ","
NUMBER_GROUPING = 3
USE_THOUSAND_SEPARATOR = True

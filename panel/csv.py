"""Ayudas para exportar reportes a CSV.

Los valores que empiezan con `=`, `+`, `-` o `@` se neutralizan con una comilla
inicial para que las hojas de cálculo no los interpreten como fórmulas.
"""

import csv

from django.http import HttpResponse

PREFIJOS_FORMULA = ("=", "+", "-", "@")


def celda_segura(valor):
    """Devuelve el valor como texto neutralizado contra inyección CSV."""
    if valor is None:
        return ""
    texto = str(valor)
    if texto.lstrip(" \t").startswith(PREFIJOS_FORMULA):
        return "'" + texto
    return texto


def respuesta_csv(nombre, cabeceras, filas):
    """CSV con codificación UTF-8 y BOM para Excel, solo datos ya autorizados."""
    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
    respuesta.write("﻿")
    escritor = csv.writer(respuesta, lineterminator="\n")
    escritor.writerow([celda_segura(cabecera) for cabecera in cabeceras])
    for fila in filas:
        escritor.writerow([celda_segura(valor) for valor in fila])
    return respuesta

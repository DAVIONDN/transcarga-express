"""Instalación directa de dependencias sin pip (recurso del entorno, no del proyecto).

El sandbox de Windows deja a `pip` en un bucle de CPU sin progreso, por eso las
dependencias se descargan con `urllib` desde PyPI y se extraen con `zipfile` en
el site-packages del entorno virtual. Verifica el sha256 publicado por PyPI.

Uso:
    python .tmp\\instalar_sin_pip.py
"""

import hashlib
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SITEPACKAGES = RAIZ / ".venv" / "Lib" / "site-packages"
CARPETA_WHEELS = RAIZ / ".tmp" / "wheels"
PY_TAG = f"cp{sys.version_info.major}{sys.version_info.minor}"

# (nombre en PyPI, versión exacta o None para la última estable compatible)
REQUISITOS = [
    ("django", "5.2.18"),
    ("asgiref", None),
    ("sqlparse", None),
    ("tzdata", None),
    ("pillow", None),
]


def consultar_pypi(nombre):
    url = f"https://pypi.org/pypi/{nombre}/json"
    with urllib.request.urlopen(url, timeout=60) as respuesta:
        return json.load(respuesta)


def etiquetas(nombre_archivo):
    return tuple(nombre_archivo[:-4].split("-")[-3:])


def wheel_compatible(nombre_archivo):
    """Indica si el wheel sirve para Windows x64 y este Python."""
    py, abi, plataforma = etiquetas(nombre_archivo)
    if plataforma == "any":
        return py == "py3" or py == "py2.py3"
    if plataforma != "win_amd64":
        return False
    if abi == "abi3" and py.startswith("cp3"):
        return int(py[2:]) <= sys.version_info.minor
    return py == PY_TAG


def clave_version(version):
    return tuple(
        (0, int(parte)) if parte.isdigit() else (1, parte)
        for parte in re.split(r"[.\-]", version)
    )


def requiere_python_ok(texto):
    """Comprobación mínima de `Requires-Python` (>=X.Y y no excluir este Python)."""
    if not texto:
        return True
    actual = f"{sys.version_info.major}.{sys.version_info.minor}"
    for exigencia in re.findall(r">=\s*(\d+\.\d+)", texto):
        if tuple(map(int, exigencia.split("."))) > tuple(map(int, actual.split("."))):
            return False
    for tope in re.findall(r"<\s*(\d+\.\d+)", texto):
        if tuple(map(int, actual.split("."))) >= tuple(map(int, tope.split("."))):
            return False
    return True


def elegir(nombre, fijada):
    datos = consultar_pypi(nombre)
    if fijada:
        versiones = [fijada]
    else:
        versiones = [
            version
            for version in datos["releases"]
            if not re.search(r"[A-Za-z]", version)
            and datos["releases"][version]
            and not all(archivo.get("yanked") for archivo in datos["releases"][version])
        ]
    info_version = {}
    for candidata in sorted(versiones, key=clave_version, reverse=True):
        archivos = [a for a in datos["releases"].get(candidata, []) if not a.get("yanked")]
        if not any(a["filename"].endswith(".whl") and wheel_compatible(a["filename"]) for a in archivos):
            continue
        requiere = next(
            (a.get("requires_python") for a in archivos if a["filename"].endswith(".whl")),
            None,
        )
        if not fijada and not requiere_python_ok(requiere or datos["info"].get("requires_python")):
            continue
        info_version = {"version": candidata, "archivos": archivos}
        break
    if not info_version:
        raise SystemExit(f"No se encontró un wheel compatible para {nombre}")

    archivo = next(
        a for a in info_version["archivos"]
        if a["filename"].endswith(".whl") and wheel_compatible(a["filename"])
    )
    return info_version["version"], archivo


def descargar(url, destino, sha256_esperado):
    with urllib.request.urlopen(url, timeout=300) as respuesta:
        contenido = respuesta.read()
    obtenido = hashlib.sha256(contenido).hexdigest()
    if sha256_esperado and obtenido != sha256_esperado:
        raise SystemExit(
            f"sha256 incorrecto para {destino.name}: {obtenido} != {sha256_esperado}"
        )
    destino.write_bytes(contenido)
    return len(contenido)


def extraer(ruta_wheel, nombre_dist):
    destino_raiz = SITEPACKAGES
    prefijo_datos = None
    instalados = 0
    with zipfile.ZipFile(ruta_wheel) as z:
        for miembro in z.namelist():
            if not prefijo_datos:
                coincidencia = re.match(r"^([^/]+\.data)/", miembro)
                if coincidencia:
                    prefijo_datos = coincidencia.group(1)
            if prefijo_datos and miembro.startswith(prefijo_datos + "/"):
                resto = miembro[len(prefijo_datos) + 1:]
                if resto.startswith("purelib/") or resto.startswith("platlib/"):
                    relativo = resto.split("/", 1)[1]
                    base = SITEPACKAGES
                elif resto.startswith("scripts/"):
                    relativo = resto.split("/", 1)[1]
                    base = RAIZ / ".venv" / "Scripts"
                elif resto.startswith("data/"):
                    relativo = resto.split("/", 1)[1]
                    base = RAIZ / ".venv"
                else:
                    continue
                if not relativo or miembro.endswith("/"):
                    continue
                salida = base / relativo
            else:
                if miembro.endswith("/"):
                    continue
                salida = destino_raiz / miembro
            salida.parent.mkdir(parents=True, exist_ok=True)
            with z.open(miembro) as origen, open(salida, "wb") as f:
                f.write(origen.read())
            instalados += 1
    return instalados


def main():
    CARPETA_WHEELS.mkdir(parents=True, exist_ok=True)
    SITEPACKAGES.mkdir(parents=True, exist_ok=True)
    for nombre, fijada in REQUISITOS:
        version, archivo = elegir(nombre, fijada)
        ruta = CARPETA_WHEELS / archivo["filename"]
        if ruta.exists():
            print(f"= {archivo['filename']} (ya descargado)")
        else:
            descargados = descargar(archivo["url"], ruta, archivo.get("digests", {}).get("sha256"))
            print(f"+ {archivo['filename']} ({descargados / 1048576:.1f} MB)")
        total = extraer(ruta, nombre)
        print(f"  -> {total} archivos extraídos en site-packages (versión {version})")
    print("Dependencias instaladas.")


if __name__ == "__main__":
    main()

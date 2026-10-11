"""Shim temporal para el sandbox de Windows de DSH (fuera del repositorio).

Motivo: en Windows, un directorio creado con mode=0o700 (lo que hacen
tempfile.mkdtemp y tempfile.TemporaryDirectory) recibe una DACL restrictiva que
el token restringido del sandbox no puede usar, de modo que cualquier escritura
dentro de el falla con PermissionError. Esto rompe ensurepip y pip.

Solucion: mientras DSH_TEMP_COMPAT=1 este definida, se crea con 0o777 cualquier
directorio pedido con 0o700. Se carga via PYTHONPATH (por ejemplo
PYTHONPATH=.tmp\\shim), de forma que el venv y el codigo del proyecto quedan
intactos. No forma parte del proyecto entregable.
"""

import os

if os.name == "nt" and os.environ.get("DSH_TEMP_COMPAT") == "1":

    _os_mkdir_original = os.mkdir

    def _mkdir_compatible(path, mode=0o777, *args, **kwargs):
        if mode == 0o700:
            mode = 0o777
        return _os_mkdir_original(path, mode, *args, **kwargs)

    os.mkdir = _mkdir_compatible

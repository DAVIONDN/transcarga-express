# TransCarga Express

Sistema **gestión de transportistas y ofertas de carga**, desarrollado con
**Django 5.2 LTS (5.2.18)** y **SQLite**. La interfaz, las etiquetas y los mensajes están en
español; se usan plantillas Django y Bootstrap 5 por CDN, y el panel de administración de
Django queda disponible como alternativa de administración.

Alcance del MVP: transportistas (con su vehículo principal), empresas clientes, ofertas de
carga, asignaciones y advertencias, con clasificación por nivel derivada de la capacidad y
validación documental (licencia, revisión técnica y SOAT).

---

## 1. Requisitos del entorno

| Componente | Versión usada |
|---|---|
| Python | 3.13.5 |
| Django | 5.2.18 (última versión correctiva de la rama 5.2 LTS) |
| Pillow | 12.3.0 (obligatoria: el modelo `Transportista` usa `ImageField`) |
| Base de datos | SQLite (archivo `db.sqlite3`, no versionado) |
| Sistema probado | Windows 11 con PowerShell 7 (los comandos funcionan igual en cmd) |

> **Nota sobre el stack:** el enunciado pedía Python 3.12. El equipo de desarrollo solo tiene
> Python 3.13.5 instalado, por lo que se documentó la desviación (decisión **D1** en
> [docs/DECISIONES.md](docs/DECISIONES.md)). Django 5.2.18 declara `requires_python >=3.10`, así
> que la aplicación funciona igual, no usa características exclusivas de 3.13 y migrar a 3.12 es
> inmediato: basta crear el entorno virtual con `py -3.12`.

## 2. Instalación y puesta en marcha

Todos los comandos se ejecutan **desde la carpeta del proyecto** (donde está `manage.py`).

### 2.1 Crear el entorno virtual (solo la primera vez)

```powershell
py -3.13 -m venv .venv
```

Si el equipo solo tiene otro Python disponible, use `python -m venv .venv` (debe ser 3.10 o
superior). El proyecto **ya incluye** un `.venv` funcional: si existe, puede saltar este paso.

### 2.2 Activar el entorno virtual

PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Símbolo del sistema (cmd):

```bat
.venv\Scripts\activate.bat
```

Si PowerShell rechaza la activación por política de ejecución («la ejecución de scripts está
deshabilitada en este sistema»), habilítela solo para esa ventana:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

También puede **no activar nada** y llamar al intérprete del entorno directamente; es lo que se
usa en el resto de este documento:

```powershell
.\.venv\Scripts\python.exe manage.py <comando>
```

### 2.3 Instalar las dependencias

```powershell
.\.venv\Scripts\python -m pip install -r requirements.txt
```

`requirements.txt` fija Django 5.2.18 y Pillow 12.3.0. No hay más dependencias: no se usa
Node.js, ni React, ni ninguna API REST.

### 2.4 Crear la base de datos (migraciones)

```powershell
.\.venv\Scripts\python manage.py migrate
```

Crea `db.sqlite3` con todas las tablas. Para comprobar que no queda ninguna migración pendiente:

```powershell
.\.venv\Scripts\python manage.py makemigrations --check --dry-run
.\.venv\Scripts\python manage.py migrate --check
```

### 2.5 Crear el usuario para ingresar

El sistema no tiene registro público de usuarios ni credenciales en el código:

```powershell
.\.venv\Scripts\python manage.py createsuperuser
```

Ese usuario sirve tanto para la aplicación como para el panel de administración de Django
(`/admin/`). Si además necesita acceso al panel de administración, el usuario debe ser *staff*
(`createsuperuser` ya lo crea así).

### 2.5.1 Inicializar roles y asignar accesos

```powershell
.\.venv\Scripts\python manage.py inicializar_roles
```

Crea los grupos **Administrador**, **Operador** y **Consulta** con su matriz de permisos
(idempotente: puede repetirse; no toca usuarios ni contraseñas). El superusuario elude los
permisos por diseño nativo de Django, así que el acceso actual se conserva.

| Rol | Acceso |
|---|---|
| Administrador | Completo: opera todos los módulos, gestiona usuarios, configura parámetros financieros y consulta la auditoría |
| Operador | Opera transportistas, clientes, ofertas, asignaciones, advertencias, incidencias, formatos, liquidaciones y capacitación; no administra usuarios ni ve la auditoría |
| Consulta | Solo lectura de los módulos autorizados |

Asigne roles desde **Usuarios** (solo Administrador) o con `groups.set()` en el shell.
Detalle en [docs/DECISIONES.md](docs/DECISIONES.md) (D16) y [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md).

### 2.6 Inicializar los roles y asignar accesos

```powershell
.\.venv\Scripts\python manage.py inicializar_roles
```

Crea los grupos **Administrador**, **Operador** y **Consulta** con su matriz de permisos
(21/18/5 permisos; detalle en [docs/DECISIONES.md](docs/DECISIONES.md), decisión **D16**).
El comando es **idempotente** (puede repetirse), **no asigna roles a los usuarios
existentes** y **no toca contraseñas**. Los superusuarios eluden los permisos por diseño
nativo de Django, así que el acceso del administrador actual se conserva.

Estrategia de asignación (sin asignar Administrador masivamente):

1. Ingrese con el superusuario y abra **Usuarios** en la barra lateral.
2. **Nuevo usuario** para cada persona (rol + contraseña inicial) o **Editar** para asignar
   rol a una cuenta existente. Los roles son exclusivos (uno por usuario).
3. El último administrador activo no puede degradarse ni desactivarse; las cuentas nunca
   se eliminan, solo se desactivan. Un administrador no superusuario no puede gestionar
   cuentas de superusuario.

### 2.7 Cargar datos ficticios de demostración (opcional)

```powershell
.\.venv\Scripts\python manage.py cargar_datos_demo
```

El comando es **idempotente** (puede ejecutarse las veces que haga falta), **no borra ni modifica**
registros existentes y **no crea usuarios ni contraseñas**. Carga un conjunto pensado para poder
probar todos los casos del MVP:

| Contenido | Cantidad y detalle |
|---|---|
| Empresas clientes | **6** (alimentos, agroexportación, minería, cadena de frío, ferretería y agroindustria) |
| Transportistas | **17**: 12 Activos, 2 En Reserva y 3 de Baja; 6 de Nivel 1, 9 de Nivel 2 y 2 de Nivel 3 |
| Ofertas de carga | **18**: 11 Disponibles y 7 Cubiertas, de los tres niveles y de todos los tipos de vehículo |
| Asignaciones | **7**: 3 Activas, 3 Finalizadas y 1 Cancelada (el historial se conserva en las tres) |
| Advertencias | **10**, repartidas entre transportistas con 1, 2 y 3 advertencias |
| Capacitación | **2** cursos con **3** participaciones: inscrita, en progreso y completada aprobada sin constancia (muestra el aviso) |
| Incidencias | **2**: queja pendiente sin advertencia formal y renuncia con acuerdo de reemplazo |
| Formatos y liquidaciones | Semanas firmadas de las asignaciones finalizadas (una regularizada) con borradores; parámetros sin configurar, cierre bloqueado |
| Documentación | 2 transportistas con documentos vencidos y 11 documentos que vencen en los próximos 30 días |

Incluye casos borde a propósito: un transportista con 1 advertencia y otro con 2 (siguen
habilitados), dos que llegaron a 3 (baja automática), una **baja administrativa sin advertencias**,
documentos vencidos y por vencer, capacidad **exactamente en el límite de 20 t** (Nivel 2), un
transportista con documento **RUC** en lugar de DNI y otro con **0 años de experiencia**.
Nombres, documentos y RUC son inventados y no corresponden a personas ni empresas reales.

### 2.8 Ejecutar la aplicación

**Comando exacto para iniciar la aplicación:**

```powershell
.\.venv\Scripts\python.exe manage.py runserver
```

La aplicación queda disponible en <http://127.0.0.1:8000/>. Todas las pantallas de negocio exigen
sesión iniciada; sin sesión se redirige a `/accounts/login/`. Para detener el servidor, `Ctrl+C`.

## 3. Pruebas y comprobaciones

```powershell
# Suite completa (371 pruebas)
.\.venv\Scripts\python manage.py test

# Solo una aplicación o un módulo
.\.venv\Scripts\python manage.py test transportistas
.\.venv\Scripts\python manage.py test panel.tests_comandos

# Comprobaciones del proyecto
.\.venv\Scripts\python manage.py check

# Comprobaciones de despliegue (informativas; el MVP es local, con DEBUG activo)
.\.venv\Scripts\python manage.py check --deploy
```

Las **371 pruebas** cubren las reglas críticas (clasificación por capacidad, certificación, vigencias
documentales, formato y normalización de la placa, carga de archivos, estados del transportista y
de la asignación, bloqueo de campos críticos de una oferta asignada, elegibilidad para asignar,
baja automática y diferida por advertencias, integridad del historial, paginación con filtros, acceso
protegido por roles, documentación y copia SOAT, motivo de cancelación, quejas y reemplazos,
formatos y liquidaciones, capacitación, reportes con CSV, auditoría, coincidencia del panel con la base de datos, cobertura del conjunto de datos demo y los comandos de gestión). Detalle en [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md), sección **G**.

Las pruebas **no escriben en `media/`**: durante `manage.py test` las fotografías se guardan en
`.tmp/media_pruebas` (ignorado por Git), de modo que la suite no deja archivos en el proyecto.

## 4. Recorrido de demostración en cinco minutos

Requisito previo: `migrate`, `inicializar_roles`, `createsuperuser` y `cargar_datos_demo` ejecutados, y el servidor
levantado con el comando de la sección 2.8. Los identificadores que se citan son los que crea el
comando de demostración.

| Minuto | Qué hacer | Qué se demuestra |
|---|---|---|
| 0:00–0:45 | Entre en <http://127.0.0.1:8000/> y observe el panel | Todos los indicadores salen de la base de datos: conteos por estado (12 activos, 2 en reserva, 3 de baja), ofertas disponibles y cubiertas, asignaciones activas, transportistas por nivel (6/9/2), alertas de SOAT vencido o por vencer, advertencias recientes y la tarjeta **Transportistas dados de baja** |
| 0:45–1:30 | Menú **Transportistas** → filtre Estado `Baja` y luego `En Reserva`; abra la ficha de **Jorge Salazar Pinto** (Baja, «3 de 3» advertencias) | Estados, insignias de nivel, historial de advertencias y de asignaciones conservado, y el aviso de que un transportista en Baja no puede recibir asignaciones. En la lista de bajas también aparece **Nadia Fuentes** (baja administrativa, sin advertencias) |
| 1:30–2:00 | Menú **Advertencias** → filtre por transportista y por rango de fechas; vea el resumen lateral «N de 3» | Listado general con 10 advertencias, filtros por transportista y fecha, total por transportista calculado desde los registros |
| 2:00–3:00 | Abra la ficha de **Ana Lucía Vargas Medina** (Activo, «2 de 3») → **Registrar advertencia** → guarde un motivo | La tercera advertencia pasa al transportista a **Baja** en la misma operación y la pantalla lo informa. Compruebe después que ya no aparece en `/ofertas/1/asignar/` |
| 3:00–4:00 | Menú **Ofertas de carga** → abra **OF-00005** (Arequipa → Puerto de Matarani, Tráiler, Nivel 1) → **Asignar transportista** | Tabla de **candidatos evaluados** con el motivo exacto de cada rechazo (nivel, tipo de vehículo, certificación de carga peligrosa, SOAT, asignación activa, estado). Elija a **Carlos Mendoza Ríos** (Tráiler Nivel 1 con certificación) → pantalla de **resumen y confirmación** → confirme |
| 4:00–5:00 | Menú **Asignaciones** → filtre por estado para ver las 3 activas, 3 finalizadas y 1 cancelada; abra la asignación recién creada → **Finalizar asignación** (con fecha de hoy) y luego intente reasignar la misma oferta | La asignación pasa a **Finalizada** conservando el historial, el transportista queda libre y la oferta **permanece Cubierta**: una oferta cubierta no admite otra asignación (el sistema lo explica con un mensaje) |

Dos cambios quedan en la base de datos tras el recorrido: Ana Lucía pasa a Baja y OF-00005 queda
Cubierta. Son parte de la demostración; si quiere volver al estado inicial, cambie el estado de
Ana a **Activo** desde `/admin/` (la aplicación no permite reactivar a un transportista dado de
baja, por diseño) y tenga en cuenta que una oferta cubierta no vuelve a «Disponible» desde la
aplicación. Si prefiere un recorrido que no toque los datos de demostración, cree una oferta nueva
(`/ofertas/nueva/`) y un transportista nuevo (`/transportistas/nuevo/`) y utilícelos en los pasos
3 a 5.

Si tiene más tiempo, el conjunto ampliado permite además: ver ofertas con **todos los candidatos
rechazados** (por ejemplo la oferta de cisterna de Nivel 1 en `/ofertas/<id>/asignar/`, donde solo
Héctor Ramírez es elegible), revisar una **asignación cancelada** que no libera su oferta, y
comprobar los avisos de **documentos por vencer** (Teresa Núñez con la revisión técnica y el SOAT
a menos de un mes).

## 5. Pantallas principales

La interfaz reutiliza `templates/base.html`: barra lateral de navegación fija en escritorio y
deslizante (offcanvas) en móvil, barra superior solo en pantallas pequeñas, mensajes de éxito,
error y aviso, tablas desplazables horizontalmente en pantallas pequeñas y Bootstrap 5 por CDN
(sin dependencias visuales adicionales).

| Ruta | Descripción |
|---|---|
| `/` | Panel: conteos por estado, transportistas por nivel, asignaciones activas, advertencias recientes, transportistas dados de baja, alertas de SOAT vencido o por vencer y vencimientos a 30 días |
| `/transportistas/` | Listado con búsqueda (nombre, documento, placa) y filtros por estado y nivel; alta, ficha, edición y cambio de estado |
| `/transportistas/<id>/` | Ficha: datos, documentación con su vigencia, fotografía, advertencias e historial de asignaciones |
| `/transportistas/<id>/advertencia/` | Registro de una advertencia (fecha, motivo y asignación opcional) |
| `/transportistas/advertencias/` | Listado general de advertencias con búsqueda y filtros por transportista y rango de fechas, y resumen por transportista |
| `/clientes/` | Empresas clientes con búsqueda por RUC o razón social y filtro con/sin ofertas; alta, ficha y edición |
| `/ofertas/` | Ofertas de carga con búsqueda y filtros por empresa, nivel, estado y tipo de vehículo; alta, ficha y edición |
| `/ofertas/<id>/estado/` | Cambio de estado con pantalla de confirmación (no se edita en el formulario) |
| `/ofertas/<id>/asignar/` | Asignación de un transportista con la tabla de elegibilidad; continúa en el paso de confirmación |
| `/asignaciones/` | Asignaciones con conteos y filtro por estado (activas, finalizadas y canceladas) |
| `/asignaciones/nueva/` → `/asignaciones/confirmar/` | Flujo en dos pasos: se eligen oferta y transportista, se revisa el resumen (oferta, empresa cliente, transportista y vehículo) y se confirma |
| `/asignaciones/<id>/` | Detalle de la asignación, con las acciones *Finalizar* y *Cancelar* |
| `/asignaciones/<id>/finalizar/` · `/asignaciones/<id>/cancelar/` | Confirmaciones explícitas; ninguna borra el historial y la oferta permanece Cubierta |
| `/usuarios/` | Listado con búsqueda, rol, estado y último acceso (solo Administrador) |
| `/liquidaciones/formatos/` · `/liquidaciones/` | Formatos semanales (firma los viernes) y liquidaciones por asignación y periodo |
| `/capacitacion/cursos/` · `/capacitacion/` | Cursos y participaciones con historial por transportista |
| `/reportes/` | Seis reportes con filtros y exportación CSV (según permisos de lectura) |
| `/auditoria/` | Auditoría de operaciones críticas (solo Administrador) |
| `/usuarios/nuevo/` · `/usuarios/<id>/editar/` · `/usuarios/<id>/estado/` · `/usuarios/<id>/clave/` | Alta, edición, activar/desactivar con confirmación y restablecimiento de contraseña (solo Administrador; sin borrado) |
| `/admin/` | Panel de administración de Django (alternativa; requiere usuario *staff*) |

## 6. Reglas de negocio implementadas

1. **Nivel derivado de la capacidad:** menos de 5 t → Nivel 3; de 5 a 20 t inclusive → Nivel 2;
   más de 20 t → Nivel 1 **con certificación de carga peligrosa obligatoria**. El nivel nunca se
   recibe del formulario: se recalcula al guardar. La placa se valida y se normaliza a «ABC-123»;
   el número de documento exige 8 dígitos (DNI) u 11 (RUC), sin consultas externas.
2. **Documentación obligatoria:** no se registra ni se activa un transportista sin fotografía,
   licencia vigente y revisión técnica vigente. El SOAT puede estar vencido al registrarlo, pero
   **bloquea cualquier asignación**.
3. **Estados:** Activo (puede recibir asignaciones), En Reserva (no recibe asignaciones),
   Baja (no recibe asignaciones y no se reactiva desde la interfaz).
4. **Asignaciones:** la oferta debe estar Disponible; se exige coincidencia exacta de **nivel** y
   de **tipo de vehículo**, SOAT vigente, y que el transportista no tenga otra asignación activa.
   Al crear la asignación, la oferta pasa a **Cubierta** en la misma transacción. Una asignación
   puede **finalizarse** o **cancelarse** conservando siempre el historial; cancelar no libera la
   oferta.
5. **Advertencias:** al acumular **tres**, el transportista pasa automáticamente a **Baja** y sus
   nuevas asignaciones se rechazan. El total se cuenta desde los registros (nunca un contador
   manual), la baja se aplica en la misma transacción que registra la advertencia, una cuarta
   advertencia **no reactiva** al transportista y el formulario no permite registrar dos veces el
   mismo envío. La asignación en curso no se cancela y el historial se conserva.
6. **Historial protegido:** las claves foráneas usan `PROTECT` y no existen pantallas de borrado
   para transportistas, clientes ni asignaciones.
7. **Ofertas asignadas:** una oferta con asignación **bloquea** los cambios de empresa cliente,
   tipo de vehículo y nivel requerido (invalidarían la asignación); solo admite ajustar origen,
   destino y remuneración. El estado se cambia con confirmación y nunca vuelve a «Disponible» si
   tiene asignación.
8. **Elegibilidad para asignar:** transportista **Activo**, con fotografía, licencia y revisión
técnica **vigentes**, SOAT vigente, compatibilidad de nivel y tipo de vehículo, certificación
cuando la oferta es de Nivel 1, sin otra asignación activa y con la oferta Disponible. Todo se
valida en el servidor (y se revalida al confirmar, dentro de una transacción) con mensajes que
indican cómo resolver cada impedimento.
9. **Baja diferida:** con tres advertencias y rechazo documentado del reemplazo con contrato en
curso, el estado pasa a **«Baja pendiente»** (termina su servicio sin nuevas asignaciones); la
baja formal la aplica una acción autorizada al terminar el contrato. La cuarta advertencia no
cambia nada.
10. **Cancelación con motivo:** cancelar exige fecha y motivo registrados; la oferta permanece
Cubierta y el historial se conserva.
11. **Documentación:** cada documento informa Vigente / Próximo (aviso a 30 días) / Vencido /
Pendiente; la copia del SOAT es opcional (PDF/JPG/PNG ≤ 5 MB). La vigencia se exige a la fecha
de inicio del servicio; vencer en servicio solo genera alerta.
12. **Formatos y liquidaciones:** semana lunes–domingo con firma el viernes; sin formato firmado
no se paga; neto = base − comisión − penalidad con parámetros configurables (sin ellos no hay
cierre); la cerrada es inmutable.
13. **Capacitación y reportes:** cursos con código único, participaciones únicas por
convocatoria, finalización solo por confirmación autorizada; seis reportes con CSV y auditoría
de operaciones críticas (solo Administrador).

## 7. Estructura del proyecto

```
config/            configuración del proyecto (settings, urls, wsgi/asgi)
comun/             catálogos, utilidades de fechas, mezclas de formularios y ayudas de prueba
formats/           formatos regionales del Perú (`es_PE` y su alias `es`): 09/10/2026 y 2100.00
panel/             inicio, reportes con CSV, usuarios y comandos de gestión
transportistas/    Transportista, Advertencia e Incidencia + pantallas
clientes/          EmpresaCliente + pantallas
ofertas/           OfertaCarga + pantallas (incluye la asignación)
asignaciones/      Asignacion + reglas.py (reglas de elegibilidad) + pantallas
liquidaciones/     FormatoSemanal, Liquidacion y parámetros + pantallas
capacitacion/      Curso y Participacion + pantallas
auditoria/         RegistroAuditoria + pantallas
templates/         plantillas compartidas y por aplicación
static/            hoja de estilos propia (Bootstrap se carga por CDN)
docs/              arquitectura, decisiones y limitaciones
```

Las pruebas de cada módulo viven en su `<aplicación>/tests.py`; las de la auditoría funcional, en
`<aplicación>/tests_auditoria.py` y `panel/tests_comandos.py`.

## 8. Solución de errores comunes

| Síntoma | Causa | Solución |
|---|---|---|
| «No se puede cargar el archivo …\Activate.ps1 porque la ejecución de scripts está deshabilitada en este sistema» | Política de ejecución de PowerShell | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` y volver a activar, o usar `.\.venv\Scripts\python.exe manage.py <comando>` sin activar |
| `ModuleNotFoundError: No module named 'django'` | El entorno virtual no está activado o las dependencias no están instaladas | Activar `.venv` (sección 2.2) y ejecutar `pip install -r requirements.txt` |
| `ModuleNotFoundError: No module named 'PIL'` | Falta Pillow (obligatoria por el `ImageField` de la fotografía) | `.\.venv\Scripts\python -m pip install -r requirements.txt` |
| «No se reconoce 'python' como un comando» | Python no está en el `PATH` | Usar `py -3.13 -m venv .venv` para crear el entorno y `.\.venv\Scripts\python.exe` para ejecutarlo |
| `no such table: transportistas_transportista` (o similar) | La base de datos no existe o no tiene las migraciones aplicadas | `.\.venv\Scripts\python manage.py migrate` |
| `You have N unapplied migration(s)` al arrancar | Hay migraciones pendientes tras actualizar el código | `.\.venv\Scripts\python manage.py migrate` (nunca `migrate zero`) |
| `Error: That port is already in use.` | Otro proceso usa el puerto 8000 | `.\.venv\Scripts\python manage.py runserver 8001` o cierre el proceso anterior |
| `DisallowedHost` / `Invalid HTTP_HOST header` | Se entró por un nombre de host distinto de `127.0.0.1` o `localhost` | Use <http://127.0.0.1:8000/>; `ALLOWED_HOSTS` es deliberadamente local |
| Las imágenes de los vehículos dan 404 en el navegador | `DEBUG` desactivado o servidor de producción | En este MVP las imágenes se sirven solo con `DEBUG=1` y `runserver` (`DJANGO_DEBUG` no debe valer `0`) |
| `makemigrations --check` informa de cambios | Se modificó un modelo sin generar su migración | `.\.venv\Scripts\python manage.py makemigrations` y `migrate`; si el cambio es solo de presentación, revise el modelo |
| No puedo entrar: «usuario o contraseña incorrectos» | No existe un usuario creado | `.\.venv\Scripts\python manage.py createsuperuser` (el comando de datos demo no crea usuarios) |
| Un transportista quedó en Baja y no puedo volver a activarlo | Es una regla del MVP: la pantalla de cambio de estado lo impide a propósito | Solo el panel de administración (`/admin/`) puede corregir ese estado; es la decisión D7 |
| No puedo reasignar una oferta ya cubierta | Es una regla del MVP (`Asignacion.oferta` es `OneToOne`) | Registre una oferta nueva para esa carga; la reasignación está fuera del alcance (decisión D6) |
| La suite deja archivos o `media/` crece mucho | Ejecuciones antiguas anteriores al aislamiento de `MEDIA_ROOT`, o uso normal de la aplicación | Durante las pruebas las fotos van a `.tmp/media_pruebas`; puede borrar `media/vehiculos/` si no necesita las fotografías cargadas |
| Caracteres raros (`Ã³`, `â†’`) al redirigir la salida a un archivo en Windows | Codificación de la consola | Ejecute con `$env:PYTHONIOENCODING="utf-8"` antes del comando |
| `pip` falla o se queda colgado al crear directorios temporales dentro de un sandbox de desarrollo | Restricciones de ACL del entorno aislado | Ejecute la instalación en una terminal normal; en el sandbox las dependencias se provisionan desde `.tmp/` (no versionado) |
| Quiero empezar de cero | — | **Operación destructiva**: detenga el servidor, borre `db.sqlite3` y ejecute `migrate` + `createsuperuser`. El sistema no borra registros por sí solo |

## 9. Documentación

- [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md) — arquitectura, modelos, reglas, pantallas,
  estructura, iteraciones y casos de prueba (T-01 … T-60).
- [docs/DECISIONES.md](docs/DECISIONES.md) — requisitos proporcionados frente a decisiones
  propuestas, incluida la desviación del runtime y las decisiones pendientes P1–P7.
- [docs/LIMITACIONES.md](docs/LIMITACIONES.md) — alcance excluido y limitaciones conocidas.

## 10. Fuera del alcance del MVP

Pagos y registro de pagos, notificaciones, despliegue en Internet,
React/Node.js, APIs REST independientes, Docker, microservicios y bases de datos externas.
Tampoco se definieron valores comerciales de comisión ni penalidad (son parámetros vacíos
hasta que la empresa los configure).

## 11. Respaldo de la base de datos

La base es un único archivo SQLite (`db.sqlite3`, no versionado). Respaldo: detenga el
servidor y copie el archivo a un lugar seguro; para restaurar, devuélvalo a la carpeta del
proyecto. Las fotografías viven en `media/` (ignorada por Git): respáldela junto con la base.
La suite de pruebas usa una base temporal y `.tmp/media_pruebas`, así que probar no altera
los datos reales.

## 12. Checklist de verificación de los casos del negocio

Con datos demo cargados y sesión de Operador (salvo indicación):

| # | Caso | Cómo verificarlo | Resultado esperado |
|---|---|---|---|
| 1 | Nivel por capacidad | Crear transportista de 22 t sin certificación | Error que exige certificación; con ella, Nivel 1 |
| 2 | SOAT bloquea asignar | Oferta disponible + transportista con SOAT vencido → Nueva asignación | Motivo «SOAT» y no se crea nada |
| 3 | Doble asignación | Asignar dos ofertas al mismo transportista | Segunda rechazada («ya tiene una asignación activa») |
| 4 | Oferta cubierta | Reasignar OF cubierta | Rechazo («ya está cubierta»); sigue Cubierta |
| 5 | Tercera advertencia | Registrar 3.ª a transportista activo | Baja inmediata + mensaje; historial intacto |
| 6 | Baja pendiente | 3.ª con excepción y contrato en curso | Estado «Baja pendiente»; sin nuevas asignaciones |
| 7 | Aplicar baja | Finalizar el servicio → Aplicar baja formal | Baja + excepción revisada |
| 8 | Cancelar con motivo | Cancelar sin motivo y con motivo | Sin motivo se rechaza; con motivo queda Cancelada |
| 9 | Formato viernes | Generar formatos → firmar el viernes | Presentado; sin firma no se liquida |
| 10 | Cierre bloqueado | Cerrar sin parámetros configurados | Error que pide configurar comisión y penalidad |
| 11 | Roles | Consulta intenta crear; Operador intenta ver usuarios | 403 en ambos; Admin gestiona |
| 12 | Inactivo | Desactivar cuenta e intentar entrar | Acceso denegado |
| 13 | Reportes y CSV | Abrir reporte y exportar | Mismas filas; sin fórmulas ejecutables |
| 14 | Auditoría | Operar y abrir `/auditoria/` como Admin | Rastro con usuario, acción y resumen |

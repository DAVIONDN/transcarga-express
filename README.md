# TransCarga Express

**Sistema de gestión de transportistas, empresas clientes y ofertas de carga.**

TransCarga Express es una aplicación web desarrollada como producto mínimo viable (MVP) para apoyar la gestión de operaciones de transporte de carga. Permite registrar transportistas y sus vehículos principales, gestionar empresas clientes y ofertas, controlar asignaciones, validar documentación, administrar advertencias y consultar reportes operativos.

> **Estado del proyecto:** MVP para ejecución local. Antes de utilizarlo en producción o exponerlo a Internet, requiere una revisión de seguridad y una configuración adecuada de despliegue.

## Tabla de contenidos

- [Características principales](#características-principales)
- [Tecnologías](#tecnologías)
- [Requisitos previos](#requisitos-previos)
- [Instalación en Windows](#instalación-en-windows)
- [Acceso al sistema](#acceso-al-sistema)
- [Roles y permisos](#roles-y-permisos)
- [Datos de demostración](#datos-de-demostración)
- [Ejecución y pruebas](#ejecución-y-pruebas)
- [Módulos y rutas principales](#módulos-y-rutas-principales)
- [Reglas de negocio relevantes](#reglas-de-negocio-relevantes)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Limitaciones conocidas](#limitaciones-conocidas)
- [Buenas prácticas antes de subir a GitHub](#buenas-prácticas-antes-de-subir-a-github)
- [Documentación adicional](#documentación-adicional)

## Características principales

- **Transportistas:** registro, edición, consulta de ficha, documentación, fotografía, nivel operativo e historial.
- **Vehículo principal:** registro de capacidad, tipo de vehículo y placa.
- **Empresas clientes:** mantenimiento de información empresarial y consulta de ofertas asociadas.
- **Ofertas de carga:** registro, búsqueda y filtrado de ofertas disponibles o cubiertas.
- **Asignaciones:** evaluación de elegibilidad, confirmación, finalización y cancelación con motivo, manteniendo el historial.
- **Documentación:** control de vigencia de licencia de conducir, revisión técnica y SOAT; alertas para documentos próximos a vencer o vencidos.
- **Advertencias e incidencias:** seguimiento de advertencias, quejas, renuncias y reglas de baja.
- **Formatos semanales y liquidaciones:** flujo de firma semanal y cálculos sujetos a parámetros configurables.
- **Capacitación:** administración de cursos, participaciones e historial.
- **Usuarios y roles:** administración de cuentas y permisos.
- **Reportes:** consultas operativas y exportación a CSV según permisos.
- **Auditoría:** registro de operaciones críticas para usuarios autorizados.
- **Panel principal:** indicadores calculados a partir de los datos almacenados.

## Tecnologías

| Componente | Versión documentada |
|---|---|
| Python | 3.13.5 en el entorno de desarrollo documentado |
| Django | 5.2.18 (rama 5.2 LTS) |
| Pillow | 12.3.0 |
| Base de datos | SQLite (`db.sqlite3`) |
| Interfaz | Django Templates y Bootstrap 5 por CDN |
| Sistema probado | Windows 11 y PowerShell 7 |

El entorno de desarrollo documentado utiliza Python 3.13.5. La versión de Python debe ser compatible con las dependencias fijadas en `requirements.txt`.

## Requisitos previos

- Windows 11 o un entorno compatible con Python.
- Python instalado y disponible mediante el comando `py` o `python`.
- Git, si se va a clonar o versionar el proyecto.
- Conexión a Internet durante la instalación de dependencias y para cargar Bootstrap desde su CDN.

Todos los comandos de esta guía se ejecutan desde la **carpeta raíz del proyecto**, donde se encuentra `manage.py`.

## Instalación en Windows

### 1. Abrir la carpeta del proyecto

En PowerShell, entra a la ruta local donde guardaste el código. Sustituye la ruta de ejemplo por la ubicación real:

```powershell
cd C:\Proyectos\TransCargaExpress
```

Comprueba que existe `manage.py`:

```powershell
dir
```

### 2. Crear el entorno virtual

Si aún no existe `.venv`, créalo con la versión de Python disponible. Para reproducir el entorno documentado:

```powershell
py -3.13 -m venv .venv
```

Si tienes otra versión compatible de Python, puedes crear el entorno con `python -m venv .venv`.

### 3. Instalar las dependencias

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 4. Crear las tablas de la base de datos

```powershell
.\.venv\Scripts\python.exe manage.py migrate
```

Esto crea o actualiza el archivo local `db.sqlite3` con las tablas definidas por las migraciones.

### 5. Crear un usuario administrador

El proyecto no incluye un usuario predeterminado creado automáticamente. Para crear un superusuario, ejecuta:

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

Sigue las instrucciones de la terminal. El usuario creado podrá acceder a la aplicación y al panel de administración de Django (`/admin/`).

### 6. Inicializar los roles

```powershell
.\.venv\Scripts\python.exe manage.py inicializar_roles
```

Este comando crea los grupos de permisos **Administrador**, **Operador** y **Consulta**. Es idempotente: puede ejecutarse más de una vez y no asigna roles automáticamente a los usuarios existentes ni modifica sus contraseñas.

### 7. Cargar datos de demostración (opcional)

```powershell
.\.venv\Scripts\python.exe manage.py cargar_datos_demo
```

El comando carga registros ficticios para probar los módulos. No crea usuarios ni contraseñas y está diseñado para no borrar ni modificar registros existentes. Los nombres, documentos y RUC de demostración son ficticios.

### 8. Iniciar el servidor

```powershell
.\.venv\Scripts\python.exe manage.py runserver
```

Abre [http://127.0.0.1:8000/](http://127.0.0.1:8000/) en el navegador. Para detener el servidor, vuelve a la terminal y pulsa `Ctrl+C`.

> Este servidor de desarrollo está pensado para pruebas locales, no para publicar la aplicación en producción.

## Acceso al sistema

### Credenciales para demostración local

Si la cuenta ya fue creada en la base de datos de esta instalación, las credenciales de demostración son:

| Campo | Valor |
|---|---|
| Usuario | `mariano` |
| Contraseña | `admin123` |

**Importante:** estas credenciales se documentan para la demostración local. No se crean automáticamente mediante las migraciones ni mediante `cargar_datos_demo`. Si no funcionan, comprueba que la cuenta exista en tu base de datos y que tenga la contraseña indicada. Puedes crear un usuario con `createsuperuser` o cambiar la contraseña de una cuenta existente con:

```powershell
.\.venv\Scripts\python.exe manage.py changepassword mariano
```

`admin123` es una contraseña débil: úsala únicamente en una base de datos local de demostración. No reutilices esta contraseña en otras cuentas ni publiques una instalación con estas credenciales. Cámbiala antes de cualquier despliegue compartido o accesible desde Internet.

## Roles y permisos

| Rol | Alcance general |
|---|---|
| **Administrador** | Acceso amplio a los módulos, gestión de usuarios, configuración de parámetros financieros y consulta de auditoría. |
| **Operador** | Operación de transportistas, clientes, ofertas, asignaciones, advertencias, incidencias, formatos, liquidaciones y capacitación; no administra usuarios ni consulta auditoría. |
| **Consulta** | Acceso de lectura a los módulos autorizados. |

Los permisos deben asignarse a cada usuario desde el módulo **Usuarios** cuando corresponda. El comando `inicializar_roles` crea los grupos, pero no asigna un rol automáticamente a todas las cuentas. El superusuario de Django conserva el comportamiento privilegiado nativo.

## Datos de demostración

El conjunto de demostración está diseñado para recorrer los casos principales y algunos escenarios límite. Según la documentación del proyecto, incluye:

- 6 empresas clientes.
- 17 transportistas con diferentes estados y niveles.
- 18 ofertas de carga.
- 7 asignaciones: activas, finalizadas y canceladas.
- 10 advertencias.
- 2 cursos y 3 participaciones de capacitación.
- Registros de incidencias, formatos semanales y liquidaciones.
- Casos con documentación vencida o próxima a vencer.

Los datos se cargan con `cargar_datos_demo`. Las cantidades anteriores describen el conjunto inicial de demostración; después de utilizar el sistema pueden cambiar.

## Ejecución y pruebas

### Verificar la configuración de Django

```powershell
.\.venv\Scripts\python.exe manage.py check
```

### Ejecutar la suite de pruebas

```powershell
.\.venv\Scripts\python.exe manage.py test
```

La documentación de desarrollo registra **371 pruebas** para la versión correspondiente del proyecto. El número puede variar a medida que se incorporen nuevas pruebas o se actualice el código; considera como resultado válido el que informe tu ejecución actual.

### Comprobar migraciones

```powershell
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py migrate --check
```

### Revisar un módulo concreto

Por ejemplo:

```powershell
.\.venv\Scripts\python.exe manage.py test transportistas
.\.venv\Scripts\python.exe manage.py test panel.tests_comandos
```

`check --deploy` también puede utilizarse como revisión informativa, pero el MVP está configurado para desarrollo local y puede mostrar advertencias de despliegue que deben resolverse antes de publicarlo.

## Módulos y rutas principales

| Ruta | Descripción |
|---|---|
| `/` | Panel principal con indicadores, advertencias recientes y alertas documentales. |
| `/transportistas/` | Listado, búsqueda y filtros de transportistas. |
| `/transportistas/<id>/` | Ficha, documentación, fotografía, advertencias e historial. |
| `/transportistas/advertencias/` | Listado y filtros de advertencias. |
| `/clientes/` | Gestión de empresas clientes. |
| `/ofertas/` | Gestión de ofertas de carga y búsqueda por criterios. |
| `/asignaciones/` | Listado y seguimiento de asignaciones. |
| `/usuarios/` | Administración de usuarios, según permisos. |
| `/liquidaciones/formatos/` | Gestión de formatos semanales. |
| `/liquidaciones/` | Consulta de liquidaciones. |
| `/capacitacion/cursos/` | Administración de cursos. |
| `/capacitacion/` | Participaciones e historial de capacitación. |
| `/reportes/` | Reportes y exportación CSV, según permisos. |
| `/auditoria/` | Registro de operaciones críticas, solo para usuarios autorizados. |
| `/admin/` | Panel de administración de Django para usuarios con acceso `staff`. |

Las rutas concretas pueden depender de la configuración de URL y de la versión actual del proyecto. Los módulos de negocio requieren autenticación.

## Reglas de negocio relevantes

1. **Nivel del transportista:** se calcula a partir de la capacidad del vehículo principal. Menos de 5 toneladas corresponde al Nivel 3; de 5 a 20 toneladas inclusive, Nivel 2; más de 20 toneladas, Nivel 1, que exige certificación de carga peligrosa.
2. **Documentación:** se exige fotografía, licencia vigente y revisión técnica vigente para registrar o activar al transportista. El SOAT vencido bloquea las nuevas asignaciones.
3. **Estados del transportista:** Activo puede recibir asignaciones; En Reserva y Baja no pueden recibirlas. Baja pendiente bloquea nuevas asignaciones mientras se completa el servicio vigente.
4. **Elegibilidad para una asignación:** la oferta debe estar disponible y deben coincidir el nivel y el tipo de vehículo. También se comprueban el SOAT, la documentación, las certificaciones necesarias y que el transportista no tenga otra asignación activa.
5. **Integridad del historial:** finalizar o cancelar una asignación no elimina el registro histórico. La cancelación requiere un motivo y la oferta permanece cubierta conforme a las reglas del MVP.
6. **Advertencias:** al llegar a tres advertencias, se aplica la baja automática, salvo la excepción documentada de baja diferida cuando el cliente rechaza el reemplazo inmediato y existe un servicio en curso. La cuarta advertencia no reactiva al transportista.
7. **Documentos:** se distinguen los estados Vigente, Próximo a vencer, Vencido y Pendiente. La copia del SOAT es opcional y admite PDF/JPG/PNG de hasta 5 MB, según las validaciones implementadas.
8. **Formatos y liquidaciones:** el periodo semanal es de lunes a domingo, con firma prevista para el viernes. Sin formato firmado no se liquida la semana. La liquidación depende de parámetros configurables de comisión y penalidad; no se debe cerrar mientras falten los valores necesarios.
9. **Capacitación y reportes:** se conserva el historial de participaciones. Los reportes se exportan a CSV conforme a los permisos del usuario.
10. **Protección de registros:** transportistas, clientes y asignaciones conservan su historial; las interfaces de negocio no ofrecen borrado indiscriminado de estos registros.

Consulta `docs/ARQUITECTURA.md` y `docs/DECISIONES.md` para conocer los detalles y las decisiones del proyecto.

## Estructura del proyecto

```text
config/          Configuración de Django, URL, WSGI y ASGI
comun/           Utilidades comunes, catálogos y ayudas
formats/         Formatos regionales y localización
panel/           Inicio, reportes, usuarios y comandos de gestión
transportistas/  Transportistas, advertencias, incidencias y vistas
clientes/        Empresas clientes
ofertas/         Ofertas de carga y flujos de asignación
asignaciones/    Asignaciones y reglas de elegibilidad
liquidaciones/   Formatos semanales, liquidaciones y parámetros
capacitacion/    Cursos y participaciones
auditoria/       Registro y consulta de auditoría
templates/       Plantillas HTML compartidas y de cada aplicación
static/          Hojas de estilo y recursos estáticos propios
docs/            Arquitectura, decisiones y limitaciones
manage.py        Utilidad de administración de Django
requirements.txt Dependencias Python del proyecto
```

La estructura exacta puede variar según la versión de trabajo. Conserva las migraciones de Django y los archivos necesarios para reproducir el esquema de la base de datos.

## Limitaciones conocidas

- El proyecto es un **MVP de ejecución local**, no un despliegue de producción.
- La base de datos utilizada es SQLite.
- Bootstrap 5 se carga por CDN, por lo que algunos recursos visuales requieren conexión a Internet.
- No incluye pagos reales ni integración bancaria.
- No cuenta con un servicio independiente de notificaciones.
- No incluye una API REST separada, React, Docker, microservicios ni una base de datos externa.
- Los valores comerciales de comisión y penalidad no están definidos por defecto; deben configurarse antes de efectuar el cierre correspondiente.
- Antes de desplegarlo en Internet deben revisarse `DEBUG`, `SECRET_KEY`, `ALLOWED_HOSTS`, HTTPS, archivos estáticos y multimedia, gestión de secretos, copias de seguridad, autenticación y controles de acceso.


---

**TransCarga Express**  
Desarrollado con Django y SQLite para apoyar la gestión de transportistas y ofertas de carga.

# Limitaciones y alcance excluido — TransCarga Express

Este documento describe lo que el MVP académico **no** hace, para evitar expectativas equivocadas y para delimitar el trabajo de una eventual segunda etapa. Todas las limitaciones se corresponden con el código implementado (Django 5.2.18 + SQLite, ejecución local).

## Alcance excluido

| Elemento excluido | Situación |
| --- | --- |
| Cursos | Módulo de capacitación interna implementado (decisión D21): cursos con código único, participaciones por convocatoria y constancias digitales. No otorga acreditaciones externas ni modifica niveles. |
| Liquidaciones semanales | No existen liquidaciones ni cierres periódicos de operaciones. |
| Penalidades | No se calculan ni registran penalidades económicas; el control se limita a las advertencias (hasta 3) y al pase a Baja. |
| Notificaciones | No hay envío de notificaciones por correo, SMS ni push; el único aviso es el listado de vencimientos del panel de inicio. |
| Pagos | No hay pasarela de pagos, cobros, facturación ni transferencias. La remuneración de la oferta es la fuente de los importes y las liquidaciones calculan el neto semanal, pero **no se registra el pago** (queda pendiente). |
| Despliegue en Internet | El sistema es local: `DEBUG` activo, `ALLOWED_HOSTS = ["127.0.0.1", "localhost"]`, servidor de desarrollo de Django y SQLite. No incluye configuración de producción. |
| React / Node | No hay SPA ni herramientas de Node; la interfaz son plantillas de Django con Bootstrap 5 por CDN. |
| API REST | No se expone ninguna API; toda la interacción es por formularios HTML y vistas del servidor. |
| Docker | No hay contenedores ni orquestación. |
| Microservicios | Es una aplicación monolítica de Django con aplicaciones internas (`panel`, `transportistas`, `clientes`, `ofertas`, `asignaciones`). |
| Bases de datos externas | Solo SQLite local (`db.sqlite3`); no hay PostgreSQL, MySQL, MariaDB ni servicios equivalentes. |

## Un único vehículo principal por transportista

El transportista y su vehículo comparten la misma tabla: `placa`, `tipo_vehiculo`, `capacidad_toneladas`, `certificacion_carga_peligrosa`, `fotografia_vehiculo` y el `nivel` derivado (`transportistas/models.py`).

- No existe una entidad «Vehículo» separada ni historial de vehículos.
- No se puede registrar un segundo vehículo para el mismo transportista ni conservar el vehículo anterior al reemplazarlo: al editar la placa o la capacidad, se sobrescribe el dato y se recalcula el nivel.
- Las validaciones de unicidad de placa y de número de documento impiden duplicar el mismo vehículo o el mismo transportista.

## La relación asignación–oferta es OneToOne

`Asignacion.oferta` es un `OneToOneField` (`asignaciones/models.py`), lo que produce estas limitaciones:

- Una oferta cubierta **no puede reasignarse** a otro transportista: la creación de una segunda asignación falla y el formulario de oferta impide volver el estado a «Disponible» (`ofertas/forms.py`).
- Una oferta cubierta **no puede volver a Disponible**, ni siquiera después de finalizar la asignación: al finalizar, la oferta permanece Cubierta (`asignaciones/views.py`).
- No hay **borrado de asignaciones**: la asignación solo puede estar **Activa**, **Finalizada** o **Cancelada** (`comun/choices.py`), y el historial se conserva en los tres casos (`Asignacion.finalizar()` y `Asignacion.cancelar()` nunca borran la fila).
- La interfaz **sí permite cancelar** una asignación, con pantalla de confirmación (`/asignaciones/<pk>/cancelar/`) que exige **fecha y motivo** (el motivo queda guardado en la asignación), pero cancelar **no libera la oferta**: la oferta permanece Cubierta y no puede reasignarse (decisión D6). Para esa misma carga debe registrarse una oferta nueva.
- Como consecuencia, corregir una asignación equivocada exige intervención desde el panel de administración de Django o sobre la base de datos, no desde la aplicación.

## Rechazo de un reemplazo inmediato: registro explícito y baja diferida

La excepción por la que un cliente podría **rechazar un reemplazo inmediato** queda **registrada de forma explícita** (decisión D18: `Incidencia` de tipo excepción con decisión del cliente, fecha, responsable y asignación afectada, consultable en su ficha y en el historial del transportista) y tiene **tratamiento implementado** (decisión D19): con la tercera advertencia el transportista pasa a **«Baja pendiente»**, termina únicamente su servicio en curso sin recibir nuevas asignaciones, y la baja formal se aplica con una acción autorizada cuando el contrato termina (con alerta anti-estancamiento en la ficha y el panel). La cuarta advertencia no cambia nada y la «Baja pendiente» no se fija ni se revierte manualmente desde la pantalla de estados.

## Baja por advertencias y vencimientos documentales

- Al llegar a **3 advertencias** el transportista pasa automáticamente a **Baja** (`transportistas/models.py`), lo que le impide recibir nuevas asignaciones.
- **La asignación activa en curso no se cancela**: si el transportista acumula la tercera advertencia mientras tiene una asignación Activa, esa asignación continúa vigente y debe finalizarse manualmente. El sistema no reasigna la carga ni penaliza la operación.
- **El estado no se recalcula por vencimiento documental**: no hay proceso automático que pase a En Reserva o Baja a un transportista cuya licencia, revisión técnica o SOAT venció. La vigencia se evalúa al consultar (`comun/fechas.py`) y solo tiene dos efectos: se bloquean **nuevas asignaciones** cuando el SOAT está vencido (`asignaciones/reglas.py`) y el panel de inicio avisa de los documentos que vencen en los próximos 30 días.
- Un transportista cuyo SOAT vence con una asignación ya activa sigue operando: el bloqueo solo alcanza a asignaciones nuevas.
- **La vigencia documental se evalúa a la fecha de inicio del servicio** (decisión D17): con `fecha_inicio` futura se exige que licencia, revisión técnica y SOAT estén vigentes ese día; con inicio pasado se evalúa contra hoy. Si un documento vence **durante la ejecución**, la ficha de la asignación y el panel muestran una **alerta** («Incidencia documental en servicio») sin cambiar el estado contractual y sin crear advertencias automáticas: registrar la incidencia como advertencia es decisión del operador, porque cada advertencia cuenta hacia la baja.
- **Sin auditoría por usuario de los cambios documentales**: cada ficha guarda `actualizado` (fecha y hora del último cambio, visible en la ficha), pero no quién lo hizo. El único rastro con responsable es `Advertencia.registrado_por`. No se inventó un registro de auditoría nuevo para esta etapa.

## Sin historial de cambios ni auditoría

- Solo se conservan dos rastros históricos: las **advertencias** (con fecha, descripción y quién las registró en `Advertencia.registrado_por`) y las **asignaciones** (con fecha de inicio, fecha de fin y estado).
- La **auditoría de operaciones** (`auditoria/`) registra quién hizo qué y cuándo en las acciones críticas (altas, ediciones, estados, asignaciones, advertencias, usuarios, formatos, liquidaciones, cursos y exportaciones), con resúmenes explícitos sin contraseñas ni secretos. No es inalterable: los superusuarios conservan acceso total. Las ediciones desde el panel de administración de Django no generan estos registros.
- No hay historial de **cambios de estado** del transportista: se guarda el estado actual y una marca `actualizado`, pero no la secuencia ni el motivo de cada transición.
- No hay historial de **ediciones** de transportistas, clientes ni ofertas: al guardar se sobrescriben los valores anteriores.
- **No hay auditoría de quién editó un transportista**: los modelos solo registran `creado` y `actualizado` (marcas de tiempo), sin usuario responsable. Lo mismo ocurre con ofertas y empresas clientes.

## Sin multi-tenant; roles implementados

- La aplicación es de un solo inquilino: una única base de datos y un único conjunto de datos compartido por todos los usuarios.
- **Roles y permisos diferenciados** (decisión D16): Administrador (acceso completo + gestión de usuarios), Operador (opera todos los módulos, no administra cuentas) y Consulta (solo lectura). Los roles son **exclusivos** (un grupo por usuario) y cada vista exige su permiso en el servidor, en GET y POST, con 403 ante la falta de permiso.
- **No hay registro público de usuarios**: las cuentas las crea un Administrador en `/usuarios/` o por línea de comandos (`python manage.py createsuperuser`). Las contraseñas nunca se muestran ni se recuperan en texto legible.
- Las cuentas **nunca se eliminan** (tampoco desde el panel de administración de Django): se desactivan, y el último administrador activo no puede degradarse ni desactivarse.
- El comando `inicializar_roles` es **solo aditivo**: si la matriz se redujera en el futuro, los permisos sobrantes ya asignados no se revocan solos.
- El superusuario elude los permisos por diseño nativo de Django; un administrador no superusuario no puede gestionar cuentas de superusuario.
- Todas las pantallas de negocio exigen sesión iniciada; el cierre de sesión está disponible en la barra de navegación.

## Panel de inicio sin paginación, búsqueda avanzada ni exportación

- El panel de inicio es un resumen: muestra contadores, los transportistas por nivel, las últimas 5 advertencias y hasta 10 documentos por vencer. Esos listados **no tienen paginación por servidor** ni filtros propios.
- Los listados de transportistas, clientes, ofertas y asignaciones sí paginan de a 10 registros, pero su búsqueda es **básica**: coincidencias parciales de texto y filtros simples por estado, nivel, tipo de vehículo o empresa. No hay filtros combinados avanzados, ordenamientos configurables ni búsqueda por rangos (por ejemplo, de fechas o de remuneración).
- **No hay exportación de reportes**: no se generan archivos PDF, Excel ni CSV, ni reportes imprimibles.

## Nota operativa sobre los datos de demostración

El comando de datos demo (`python manage.py cargar_datos_demo`) carga un conjunto ficticio
pensado para cubrir todos los casos del MVP: 6 empresas clientes, 17 transportistas (12 Activos, 2 En Reserva y 3 de Baja;
niveles 1, 2 y 3), 18 ofertas de carga (11 Disponibles y 7 Cubiertas), 7 asignaciones (3 Activas, 3 Finalizadas y
1 Cancelada), 10 advertencias, 2 cursos con 3 participaciones (inscrita, en progreso y completada aprobada
sin constancia), 2 incidencias (queja pendiente sin advertencia formal y renuncia con acuerdo) y los formatos
semanales firmados de las asignaciones finalizadas con sus liquidaciones en borrador. Es **idempotente** (puede ejecutarse varias veces) y **nunca borra ni modifica** registros existentes: solo crea lo que falta (se identifica por RUC, número de documento, placa, ruta de la oferta, oferta de la asignación y descripción de la advertencia).

Los **nombres, documentos y RUC son inventados** para la demostración y no corresponden a personas ni empresas reales; los documentos cumplen solo el formato (8 dígitos de DNI, 11 de RUC) porque el sistema no consulta SUNAT ni RENIEC.

**No crea usuarios ni contraseñas.** Para poder ingresar al sistema es obligatorio crear un usuario antes (por ejemplo, `python manage.py createsuperuser`); hasta entonces, todas las pantallas de negocio redirigen al inicio de sesión.

## Archivos subidos y carpeta `media/`

- Las fotografías de los vehículos se guardan en `media/vehiculos/<año>/<mes>/` (ignorada por Git). La aplicación no las borra nunca: al reemplazar la fotografía de un transportista, la anterior queda en disco sin referencia.
- Durante las pruebas (`python manage.py test`) la configuración usa `.tmp/media_pruebas` como `MEDIA_ROOT`, de modo que la suite no acumula archivos en `media/`. Las fotografías cargadas por el uso normal de la aplicación sí van a `media/`.

## Avisos esperados de `check --deploy` y páginas de error

- `python manage.py check --deploy` informa de **6 avisos** (`security.W004`, `W008`, `W009`, `W012`, `W016`, `W018`): HSTS, redirección a HTTPS, `SECRET_KEY` de desarrollo, cookies seguras y `DEBUG` activo. Son **esperados**: el MVP es local y no se despliega en Internet. En un despliegue real habría que definir `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0` y activar HTTPS con sus opciones de seguridad.
- Con `DEBUG` activo, una URL inexistente muestra la **página técnica de error de Django** (con trazas) en lugar de una página 404 propia, y una URL sin barra final responde 301 hacia la versión con barra. En producción correspondería desactivar `DEBUG` y definir plantillas `404.html` y `500.html`.

## Concurrencia en la generación del código de oferta

`OfertaCarga.generar_codigo()` calcula el consecutivo a partir del número de ofertas existentes y comprueba que el código no esté en uso, pero no bloquea la tabla. Si **dos operadores registraran una oferta exactamente a la vez**, la restricción de unicidad del código impediría el duplicado y la segunda operación fallaría con un error de integridad, en lugar de reintentar automáticamente. En el uso previsto (una sola persona operando, SQLite local) no se produce; se anota como mejora futura.

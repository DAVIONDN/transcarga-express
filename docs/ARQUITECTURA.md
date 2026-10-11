# TransCarga Express — Arquitectura y diseño (entregable A–H)

Documento de referencia del MVP implementado. Todo lo descrito aquí está en el repositorio:
las rutas de archivo son las reales y las reglas indican su ubicación en el código.

- Requisitos proporcionados frente a decisiones propuestas: [DECISIONES.md](DECISIONES.md)
- Alcance excluido y limitaciones: [LIMITACIONES.md](LIMITACIONES.md)

---

## A. Arquitectura propuesta

**Estilo:** monolito Django clásico **MVT** (Model–Template–View): un proyecto `config` y cinco
aplicaciones pequeñas y cohesionadas. No hay capa de servicios genérica, repositorios, API REST,
Docker ni base de datos externa; tampoco señales de Django.

| Elemento | Implementación |
|---|---|
| Presentación | Plantillas Django con herencia desde `templates/base.html`; Bootstrap 5.3 por CDN; estilos propios en `static/css/transcarga.css`. Barra lateral de navegación (fija en escritorio, deslizante en móvil: `offcanvas-lg`) y barra superior solo en pantallas pequeñas |
| Validación de datos | `Model.clean()` (invariantes: nivel ↔ capacidad, certificación ↔ capacidad, fechas, RUC) y `ModelForm.clean()` (reglas según el estado y mensajes en español) |
| Reglas de asignación | `asignaciones/reglas.py`: funciones puras reutilizadas por el formulario, las vistas, el panel de administración y las pruebas (una sola fuente de verdad) |
| Consistencia transaccional | `transaction.atomic()` + `select_for_update()` en `crear_asignacion` y `UniqueConstraint` parcial como red de seguridad |
| Autenticación | `django.contrib.auth` + `LoginRequiredMixin` en todas las vistas de negocio; contraseñas siempre gestionadas por Django; roles Administrador/Operador/Consulta como grupos con matriz explícita (`comun/permisos.py`) y `PermisoRequeridoMixin` en cada vista (403 sin permiso, en GET y POST) |
| Administración | `admin.py` de cada aplicación con `list_display`, filtros, búsqueda y campos de solo lectura |
| Código compartido | Paquete `comun/` (sin `AppConfig` ni migraciones): `choices.py`, `fechas.py`, `forms.py`, `pruebas.py` |
| Configuración | `SECRET_KEY` por variable de entorno con valor de desarrollo, `DEBUG` en local, `ALLOWED_HOSTS` limitado a `127.0.0.1` y `localhost`, `LANGUAGE_CODE = es-pe`, `TIME_ZONE = America/Lima`, `USE_TZ = True` y formatos regionales en `formats/` (directorios `es_PE` y su alias `es`, vía `FORMAT_MODULE_PATH`: fecha dd/mm/aaaa, separador decimal punto y miles con coma) |
| Dependencias | `Django==5.2.18` y `Pillow` (única dependencia no incluida en Django, necesaria para `ImageField`) |

Flujo de una asignación: vista `AsignarOfertaView` → formulario `AsignacionForm` (valida con
`reglas.es_elegible`) → `reglas.crear_asignacion` (revalida con registros bloqueados, crea la
asignación y marca la oferta como Cubierta) → mensaje y redirección al detalle.

---

## B. Modelos de datos y relaciones

### `transportistas.Transportista` (el vehículo principal vive en la misma tabla)

| Campo | Tipo | Notas |
|---|---|---|
| `tipo_documento` | `CharField(3, choices)` | DNI o RUC |
| `numero_documento` | `CharField(15, unique)` | 8 dígitos (DNI) u 11 (RUC) |
| `nombre` | `CharField(150)` | persona o razón social |
| `direccion` | `CharField(200)` | |
| `anios_experiencia` | `PositiveSmallIntegerField` | ≥ 0 |
| `placa` | `CharField(10, unique)` | validada y normalizada a `ABC-123` / `A1B-234` |
| `tipo_vehiculo` | `CharField(20, choices)` | Camioneta, Furgón, Camión, Tráiler, Cisterna, Volquete |
| `capacidad_toneladas` | `Decimal(6,2)` | > 0 |
| `certificacion_carga_peligrosa` | `BooleanField` | obligatoria si la capacidad supera 20 t |
| `nivel` | `PositiveSmallIntegerField(editable=False)` | **derivado** de la capacidad |
| `fecha_vencimiento_licencia` | `DateField` | |
| `fecha_vencimiento_revision_tecnica` | `DateField` | |
| `fecha_vencimiento_soat` | `DateField` | |
| `fotografia_vehiculo` | `ImageField` | JPG/PNG, máximo 5 MB |
| `estado` | `CharField(12, choices)` | Activo / En Reserva / Baja |
| `creado`, `actualizado` | `DateTimeField` | auditoría básica |

Propiedades: `licencia_vigente`, `revision_tecnica_vigente`, `soat_vigente`,
`documentacion_completa`, `advertencias_total`, `tiene_asignacion_activa`, `asignacion_activa`,
`esta_activo`, `esta_de_baja`, `documentos_por_vencer()`.

### `transportistas.Advertencia`

`fecha` (por omisión la fecha local), `descripcion`, `transportista` (FK, `PROTECT`),
`asignacion` (FK opcional, `PROTECT`), `registrado_por` (FK al usuario, opcional), `creado`.
Al guardar aplica la regla de baja automática.

### `clientes.EmpresaCliente`

`ruc` (11 dígitos, único), `razon_social`, `direccion`, `actividad_economica`, `creado`,
`actualizado`.

### `ofertas.OfertaCarga`

`codigo` (único, autogenerado `OF-00001`), `empresa_cliente` (FK, `PROTECT`), `origen`,
`destino`, `tipo_vehiculo_requerido`, `nivel_requerido`, `remuneracion` (`Decimal(10,2)` > 0),
`estado` (Disponible / Cubierta), `creado`, `actualizado`.

### `asignaciones.Asignacion`

`transportista` (FK, `PROTECT`), `oferta` (**OneToOneField**, `PROTECT`), `fecha_inicio`,
`fecha_fin` (opcional, no anterior al inicio), `estado` (Activa / Finalizada / Cancelada), `creado`,
`actualizado`, y los métodos `finalizar(fecha)` y `cancelar(fecha=None)`, que cambian el estado sin
borrar nunca la fila (el historial se conserva). Índice sobre `estado`.
`actualizado`. Restricción `una_asignacion_activa_por_transportista`
(`UniqueConstraint` condicional sobre transportista + estado = ACTIVA).

### Relaciones

```
EmpresaCliente 1───N OfertaCarga          (PROTECT)
Transportista  1───N Asignacion           (PROTECT)
OfertaCarga    1───1 Asignacion           (PROTECT, OneToOne)
Transportista  1───N Advertencia          (PROTECT)
Asignacion     1───N Advertencia          (PROTECT, asignación opcional)
Usuario        1───N Advertencia          (PROTECT, registrado_por)
```

Ninguna relación usa `CASCADE`: el historial nunca se borra automáticamente.

---

## C. Reglas del negocio

| ID | Regla | Ubicación |
|---|---|---|
| R1 | No se registra ni se activa un transportista sin los requisitos documentales (campos base, licencia vigente, revisión técnica vigente y fotografía) | `TransportistaForm.clean`, `CambiarEstadoTransportistaForm.clean_estado` |
| R2 | Nivel derivado de la capacidad: < 5 t → 3; 5 a 20 t inclusive → 2; > 20 t → 1. El valor enviado por el cliente se ignora | `comun/choices.py:nivel_desde_capacidad`, `Transportista.clean/save` |
| R3 | Capacidad superior a 20 t exige certificación de carga peligrosa | `Transportista.clean` |
| R4 | Estados: Activo (asignable), En Reserva (no asignable), Baja (no asignable, no reactivable desde la interfaz) | `comun/choices.py`, `transportistas/forms.py`, `asignaciones/reglas.py` |
| R5 | Asignación solo si: oferta Disponible, transportista Activo, **nivel exactamente igual**, tipo de vehículo igual, SOAT vigente y certificación presente cuando la oferta es de Nivel 1. Al crear, la oferta pasa a Cubierta | `asignaciones/reglas.py:motivos_no_elegibilidad`, `crear_asignacion` |
| R6 | Un transportista no puede tener más de una asignación activa | Validación en `reglas.py` + `UniqueConstraint` parcial en `Asignacion.Meta` |
| R7 | Al registrar la tercera advertencia el transportista pasa automáticamente a Baja y se impiden nuevas asignaciones. El total se cuenta desde los registros (nunca un contador manual), la baja se aplica en la misma transacción con la fila del transportista bloqueada, una cuarta advertencia no lo reactiva y el formulario lleva un token de un solo uso que evita el doble registro | `transportistas/models.py` (`Advertencia.save` con `transaction.atomic` y `aplicar_limite_advertencias`), `transportistas/views.py` (`RegistrarAdvertenciaView`) |
| R8 | La advertencia asociada a una asignación debe pertenecer al mismo transportista | `Advertencia.clean` y queryset acotado en `AdvertenciaForm` |
| R9 | No se borran entidades con historial: `PROTECT` en todas las claves foráneas y ninguna vista de borrado | `models.py` de cada aplicación |
| R10 | Licencia y revisión técnica vigentes al registrar y al mantener el estado Activo; con En Reserva o Baja se puede guardar documentación vencida (se muestra en rojo) | `TransportistaForm.clean` |
| R11 | El SOAT se comprueba antes de asignar | `reglas.motivos_no_elegibilidad` |
| R12 | Valores positivos y `Decimal` (capacidad, remuneración), años ≥ 0, `fecha_fin >= fecha_inicio` | Validadores de campo y `clean()` de los modelos |
| R13 | Todas las comparaciones de vigencia usan la fecha local (`America/Lima`) | `comun/fechas.py` |
| R14 | Todas las vistas de negocio exigen sesión iniciada | `LoginRequiredMixin` |
| R15 | La placa se valida en formato (6 caracteres alfanuméricos, guion central opcional) y se guarda normalizada en mayúsculas; el número de documento exige 8 dígitos (DNI) u 11 (RUC). Sin consultas a SUNAT ni a ningún registro externo | `transportistas/models.py` (`validar_placa`, `normalizar_placa`) |
| R16 | Finalizar o cancelar una asignación nunca borra el historial: cambia el estado y conserva la fila, la oferta y el transportista. Cancelar no libera la oferta (sigue Cubierta), pero sí libera al transportista (la restricción única solo cuenta las Activas) | `asignaciones/models.py` (`finalizar`, `cancelar`), `comun/choices.py` |
| R17 | Con una asignación registrada, la oferta bloquea los cambios de empresa cliente, tipo de vehículo requerido y nivel requerido, porque invalidarían la asignación; sí permite ajustar origen, destino y remuneración | `ofertas/forms.py` (`CAMPOS_CRITICOS`, `OfertaCargaForm.clean`) |
| R18 | El estado de la oferta no se edita en el formulario: se cambia con una acción confirmada que impide volver a «Disponible» mientras exista asignación | `ofertas/forms.py` (`CambiarEstadoOfertaForm`), `ofertas/views.py` (`CambiarEstadoOfertaView`) |
| R19 | Para asignar se exige: transportista Activo, fotografía, licencia y revisión técnica vigentes, SOAT vigente, compatibilidad de nivel y tipo de vehículo, certificación si la oferta es de Nivel 1, sin otra asignación activa y oferta Disponible. Cada impedimento se explica con la forma de resolverlo | `asignaciones/reglas.py` (`motivos_no_elegibilidad`) |
| R20 | La asignación se crea en dos pasos: selección y **pantalla de resumen y confirmación**; al confirmar se revalidan las reglas y se crea todo dentro de una transacción (si algo falla, no queda asignación ni cambio de estado) | `asignaciones/views.py` (`AsignacionCrearView`, `ConfirmarAsignacionView`), `asignaciones/reglas.py` (`crear_asignacion`) |
| R21 | Finalizar y cancelar exigen una confirmación explícita, conservan el historial y dejan la oferta Cubierta | `asignaciones/views.py` (`FinalizarAsignacionView`, `CancelarAsignacionView`), `asignaciones/models.py` (`finalizar`, `cancelar`) |

Mensajes destacados (todos en español): «La capacidad supera las 20 toneladas (Nivel 1), por lo
que la certificación de carga peligrosa es obligatoria.», «Para registrar o mantener un
transportista como Activo, la licencia de conducir debe estar vigente (venció el dd/mm/aaaa)…»,
«El SOAT del transportista está vencido (venció el dd/mm/aaaa); no se puede asignar.», «La oferta
ya está cubierta: una oferta cubierta no puede recibir otra asignación.», «El transportista ya
tiene una asignación activa.», «El transportista alcanzó 3 advertencias y pasó automáticamente a
estado «Baja»…».

---

## D. Pantallas y rutas

### Autenticación y panel (`panel`)

| Ruta | Nombre | Vista |
|---|---|---|
| `/accounts/login/` | `login` | `LoginView` con `templates/registration/login.html` |
| `/accounts/logout/` | `logout` | `LogoutView` (solo POST, desde la barra superior) |
| `/` | `panel:inicio` | Panel: conteos, transportistas por nivel, últimas advertencias y vencimientos ≤ 30 días |

### Usuarios y roles (`panel`)

Gestión de cuentas solo para el Administrador (`auth.view/add/change_user`). Sin registro
público y sin borrado de cuentas (tampoco en el panel de administración de Django).

| Ruta | Nombre | Vista |
|---|---|---|
| `/usuarios/` | `panel:usuarios_lista` | Listado con búsqueda (usuario, nombre, correo), rol, estado y último acceso |
| `/usuarios/nuevo/` | `panel:usuarios_crear` | Alta con contraseña inicial y rol |
| `/usuarios/<pk>/editar/` | `panel:usuarios_editar` | Datos básicos, estado y rol (sin tocar la contraseña) |
| `/usuarios/<pk>/estado/` | `panel:usuarios_estado` | Activar/desactivar con confirmación; protege al último administrador |
| `/usuarios/<pk>/clave/` | `panel:usuarios_clave` | Restablecimiento administrativo (nunca muestra la anterior) |

Matriz implementada (`comun/permisos.py`, decisión D16): Administrador 21 permisos (acceso
completo + gestión de usuarios); Operador 18 (opera todo, no administra cuentas);
Consulta 5 (solo `view_*` de los cinco módulos). Roles exclusivos (un grupo por usuario).

### Transportistas (`transportistas`)

| Ruta | Nombre | Vista |
|---|---|---|
| `/transportistas/` | `transportistas:lista` | Búsqueda por nombre, documento o placa; filtros por estado y nivel; paginación |
| `/transportistas/advertencias/` | `transportistas:advertencias` | Listado general de advertencias con búsqueda y filtros por **transportista** y **rango de fechas**, más el resumen de totales por transportista (sección del menú) |
| `/transportistas/nuevo/` | `transportistas:crear` | Alta con R1, R2, R3 y R10 |
| `/transportistas/<pk>/` | `transportistas:detalle` | Ficha, documentación, fotografía, advertencias y asignaciones |
| `/transportistas/<pk>/editar/` | `transportistas:editar` | Recalcula el nivel |
| `/transportistas/<pk>/estado/` | `transportistas:cambiar_estado` | Activo exige documentación vigente |
| `/transportistas/<pk>/advertencia/` | `transportistas:registrar_advertencia` | Aplica R7 |

*(No existen rutas de borrado — R9.)*

### Empresas clientes (`clientes`)

`/clientes/` (`clientes:lista`), `/clientes/nuevo/` (`clientes:crear`), `/clientes/<pk>/`
(`clientes:detalle`), `/clientes/<pk>/editar/` (`clientes:editar`). El listado busca por RUC, razón
social o actividad económica y filtra por empresas con o sin ofertas registradas.

### Ofertas de carga (`ofertas`)

`/ofertas/` (`ofertas:lista`, con filtros por empresa cliente, nivel, estado y tipo de vehículo y
búsqueda por código, origen o destino), `/ofertas/nueva/` (`ofertas:crear`), `/ofertas/<pk>/`
(`ofertas:detalle`), `/ofertas/<pk>/editar/` (`ofertas:editar`), `/ofertas/<pk>/estado/`
(`ofertas:cambiar_estado`, con pantalla de confirmación), `/ofertas/<pk>/asignar/`
(`ofertas:asignar`, solo si la oferta está Disponible).

### Asignaciones (`asignaciones`)

`/asignaciones/` (`asignaciones:lista`, con conteos y filtro por estado), `/asignaciones/nueva/`
(`asignaciones:nueva`, elección de oferta Disponible y transportista), `/asignaciones/confirmar/`
(`asignaciones:confirmar`, resumen y creación), `/asignaciones/<pk>/` (`asignaciones:detalle`),
`/asignaciones/<pk>/finalizar/` y `/asignaciones/<pk>/cancelar/` (confirmaciones que conservan el
historial).

---

## E. Estructura de carpetas

```
C:\Users\Mariano\Documents\DEEP\
├─ .venv\                        entorno virtual (no versionado)
├─ .tmp\                         recursos del entorno de desarrollo (no versionado)
├─ .gitignore
├─ README.md
├─ requirements.txt
├─ manage.py
├─ config\                       settings.py, urls.py, wsgi.py, asgi.py
├─ comun\                        choices.py, fechas.py, forms.py, pruebas.py
├─ formats\es_PE\ y formats\es\   formatos regionales (dd/mm/aaaa, punto decimal)
├─ panel\                        views.py, urls.py, tests.py
│  └─ management\commands\       cargar_datos_demo.py
├─ transportistas\               models.py, forms.py, views.py, urls.py, admin.py, tests.py
├─ clientes\                     models.py, forms.py, views.py, urls.py, admin.py, tests.py
├─ ofertas\                      models.py, forms.py, views.py, urls.py, admin.py, tests.py
├─ asignaciones\                 models.py, reglas.py, forms.py, views.py, urls.py, admin.py, tests.py
├─ templates\                    base.html, includes\, registration\, panel\, transportistas\, clientes\, ofertas\, asignaciones\
├─ static\css\transcarga.css
├─ media\vehiculos\<año>\<mes>\  fotografías subidas
└─ docs\                         ARQUITECTURA.md, DECISIONES.md, LIMITACIONES.md
```

Cada aplicación con modelos tiene su carpeta `migrations\` con la migración inicial aplicada.

---

## F. Plan de iteraciones ejecutado

| # | Iteración | Entregable | Verificación |
|---|---|---|---|
| I0 | Andamiaje | Entorno virtual, Django 5.2.18 + Pillow, proyecto `config`, cinco aplicaciones, `comun/`, `base.html`, acceso en español, `.gitignore` y `README.md` | `manage.py check` sin incidencias; `/accounts/login/` responde |
| I1 | Modelos y migraciones | Cinco modelos, migración inicial aplicada, registro en el panel de administración | `makemigrations --check` sin cambios; pruebas de R2, R3 y R12 |
| I2 | Transportistas | Listado, alta, ficha, edición, cambio de estado y advertencias | 29 pruebas de R1, R2, R3, R4, R7, R8, R9 y R10 |
| I3 | Clientes y ofertas | CRUD de empresas clientes y de ofertas con código autogenerado | 14 pruebas (RUC, código único, remuneración, estado) |
| I4 | Asignaciones | `reglas.py`, formulario con motivos de rechazo, creación transaccional y finalización | 24 pruebas de R5, R6, R11 y R12 |
| I5 | Advertencias y panel | Baja automática visible, panel con conteos y vencimientos | 8 pruebas de panel y acceso protegido |
| I6 | Cierre | `cargar_datos_demo` idempotente, documentación y verificación integral | 75 pruebas en verde; recorrido de todas las pantallas con datos demo |
| Ampliación | Modelos de datos ampliados: placa validada y normalizada, estado Cancelada de la asignación, R1 movida al modelo e índices de estado | 101 pruebas en verde; datos demo y migraciones intactos |
| Interfaz | Estructura visual y de navegación: barra lateral responsiva, sección de advertencias, alertas de SOAT y estado vacío del panel | 112 pruebas en verde; las 18 rutas verificadas sobre los datos demo |
| Módulo Transportistas | Interfaz completa del módulo: listado con búsqueda y filtros, alta, ficha, edición, cambio de estado, fotografía y validaciones de carga de archivos | 125 pruebas en verde; ciclo completo verificado de extremo a extremo sobre los datos demo |
| Módulos Clientes y Ofertas | Búsqueda y filtros en ambos listados, edición, confirmación de estado de la oferta y bloqueo de campos críticos cuando ya existe asignación | 143 pruebas en verde; ciclo completo de ambos módulos verificado de extremo a extremo |
| Módulo Asignaciones | Flujo en dos pasos con resumen y confirmación, elegibilidad completa (documentación, SOAT, nivel, vehículo, certificación), finalización y cancelación confirmadas y listado con los tres estados | 152 pruebas en verde; flujo completo verificado de extremo a extremo sobre los datos demo |
| Módulo Advertencias | Registro desde la ficha del transportista con token de un solo uso, baja automática a la tercera advertencia dentro de una transacción, listado general con filtros por transportista y fecha, y panel con advertencias recientes y transportistas de baja | 166 pruebas en verde; ciclo completo verificado de extremo a extremo sobre los datos demo |
| Auditoría funcional y técnica | Revisión de modelos, formularios, vistas, rutas, plantillas, permisos y reglas; corrección de cuatro defectos (paginación que perdía filtros, errores no asociados a un campo sin mostrar, tablas sin desplazamiento en móvil, pruebas que escribían en `media/`) y 69 pruebas nuevas para los once escenarios críticos | 235 pruebas en verde; `check`, `makemigrations --check` y `migrate --check` sin incidencias; comando de datos demo verificado como idempotente |
| Datos de demostración ampliados | El comando `cargar_datos_demo` pasa a cargar un conjunto que cubre todos los casos del MVP (17 transportistas con niveles 1/2/3 y los tres estados, documentación vigente/por vencer/vencida, DNI y RUC, 0 años de experiencia y una baja administrativa; 18 ofertas; 7 asignaciones en los tres estados; 10 advertencias), sin dejar de ser idempotente y sin borrar ni modificar registros | 245 pruebas en verde; las 10 pruebas nuevas comprueban la cobertura del conjunto, su idempotencia y que el recorrido documentado tiene candidatos elegibles |

---

## G. Casos de prueba de las reglas críticas

245 pruebas (`manage.py test`): 96 transportistas, 62 asignaciones, 20 ofertas, 55 panel, 12 clientes.
Las fechas se construyen siempre relativas a `timezone.localdate()`, de modo que la suite no
caduca con el tiempo.

| ID | Caso | Prueba |
|---|---|---|
| T-01 | 4.99 t → Nivel 3 | `NivelPorCapacidadTests.test_limites_de_los_niveles` |
| T-02 | 5.00 t → Nivel 2 | ídem |
| T-03 | 20.00 t → Nivel 2 | ídem |
| T-04 | 20.01 t con certificación → Nivel 1 | ídem |
| T-05 | El nivel no se puede manipular desde el cliente | `FormularioTransportistaTests.test_el_nivel_no_puede_manipularse_desde_el_cliente` |
| T-06 | 25 t sin certificación → error | `CertificacionTests.test_capacidad_mayor_a_20_sin_certificacion_es_invalida` y `..._no_se_guarda` |
| T-07 | Certificación voluntaria en Nivel 2 → válida | `CertificacionTests.test_certificacion_voluntaria_en_nivel_2_es_valida` |
| T-08 | Alta sin fotografía → error | `test_no_se_registra_sin_fotografia` |
| T-09 | Licencia vencida al registrar → error | `test_no_se_registra_con_licencia_vencida_siendo_activo` |
| T-10 | Revisión técnica vencida → error | `test_no_se_registra_con_revision_tecnica_vencida` |
| T-11 | SOAT vencido al registrar → permitido | `test_el_soat_vencido_no_impide_el_registro` |
| T-12 | SOAT vencido al asignar → error | `CrearAsignacionTests.test_no_se_asigna_con_soat_vencido` |
| T-13 | Oferta cubierta no recibe otra asignación | `test_una_oferta_cubierta_no_recibe_otra_asignacion` |
| T-14 | Una sola asignación activa por transportista | `test_un_transportista_no_puede_tener_dos_asignaciones_activas` |
| T-15 | Transportista en Baja → no asignable | `test_no_se_asigna_a_un_transportista_de_baja` |
| T-16 | Transportista En Reserva → no asignable | `test_no_se_asigna_a_un_transportista_en_reserva` |
| T-17 | Nivel distinto → error | `test_el_nivel_debe_coincidir_exactamente` |
| T-18 | Tipo de vehículo distinto → error | `test_el_tipo_de_vehiculo_debe_coincidir` |
| T-19 | Asignación válida cubre la oferta | `test_asignacion_valida_marca_la_oferta_como_cubierta` y `VistasAsignacionTests.test_asignar_desde_la_pantalla` |
| T-20 | Finalizar libera al transportista | `test_finalizar_libera_al_transportista_para_otra_asignacion` |
| T-21 | Tercera advertencia → Baja automática | `AdvertenciaTests.test_tercera_advertencia_pasa_a_baja` y `test_baja_por_advertencias_impide_nuevas_asignaciones` |
| T-22 | Advertencia de otro transportista → error | `AdvertenciaTests.test_la_advertencia_debe_corresponder_al_mismo_transportista` |
| T-23 | No se borran entidades con historial | `HistorialProtegidoTests` (2 pruebas) |
| T-24 | Fecha de fin anterior al inicio → error | `test_la_fecha_de_fin_no_puede_ser_anterior_al_inicio` |
| T-25 | Remuneración o capacidad ≤ 0 → error | `OfertaCargaTests.test_remuneracion_mayor_que_cero`, `test_la_capacidad_debe_ser_mayor_que_cero` |
| T-26 | RUC distinto de 11 dígitos → error | `EmpresaClienteTests.test_ruc_debe_tener_11_digitos` y `..._solo_digitos` |
| T-27 | Un transportista en Baja no se reactiva desde la pantalla | `EstadoTransportistaTests.test_transportista_de_baja_no_se_reactiva_desde_la_pantalla` |
| T-28 | Vigencias según el estado resultante | `test_se_permite_guardar_vencido_en_reserva`, `test_activar_sin_documentacion_vigente_no_es_posible` |
| T-29 | Código autogenerado consecutivo | `CodigoDeOfertaTests.test_codigo_autogenerado_consecutivo` |
| T-30 | Todas las rutas exigen sesión | `panel.tests.AccesoProtegidoTests` |
| T-31 | Placa mal formada → error; `abc123` → `ABC-123`; la unicidad considera la normalización | `transportistas.tests_modelos.PlacaTests` (`test_el_modelo_rechaza_una_placa_mal_formada`, `test_normalizacion`, `test_la_unicidad_tiene_en_cuenta_la_normalizacion`) |
| T-32 | Cancelar conserva el historial, no libera la oferta y libera al transportista | `asignaciones.tests_modelos.EstadoCanceladaTests` (5 pruebas) |
| T-33 | Restricciones garantizadas en la base de datos, no solo en las reglas | `asignaciones.tests_modelos.RestriccionesBaseDeDatosTests` (3 pruebas) |
| T-34 | Documentación obligatoria y vigencia según el estado, validadas en el modelo | `transportistas.tests_modelos.DocumentacionObligatoriaTests` (7 pruebas) |
| T-35 | Carga de archivos del vehículo: obligatoria, solo imágenes JPG/PNG y máximo 5 MB | `transportistas.tests.FotografiaVehiculoTests` (4 pruebas) |
| T-36 | Ciclo completo del módulo de transportistas: alta válida, documento y placa duplicados, edición conservando la fotografía, ficha completa y cambio a En Reserva sin perder historial | `transportistas.tests.RegistroTransportistaTests` (9 pruebas) |
| T-37 | Módulo de empresas clientes: edición, búsqueda por RUC y razón social, filtro con/sin ofertas y ficha con sus ofertas | `clientes.tests.ModuloClientesTests` (5 pruebas) |
| T-38 | Módulo de ofertas: edición, empresa obligatoria, importes inválidos, filtros por empresa/nivel/estado, búsqueda por código/origen/destino y cambio de estado confirmado | `ofertas.tests.ModuloOfertasTests` (13 pruebas) |
| T-39 | Una oferta con asignación bloquea los campos críticos y no vuelve a «Disponible» | `ofertas.tests.ModuloOfertasTests` (`test_no_se_puede_cambiar_el_nivel_de_una_oferta_asignada`, `test_no_se_puede_cambiar_el_vehiculo_de_una_oferta_asignada`, `test_una_oferta_con_asignacion_no_vuelve_a_disponible`) |
| T-40 | Flujo de asignación en dos pasos con resumen y confirmación (nada se crea antes de confirmar) | `asignaciones.tests.VistasAsignacionTests` (`test_asignar_desde_la_oferta_se_confirma_en_dos_pasos`, `test_flujo_general_eligiendo_la_oferta_disponible`, `test_confirmar_sin_seleccion_pendiente`) |
| T-41 | Elegibilidad completa: documentación vigente, SOAT, nivel, tipo de vehículo, certificación, asignación activa y oferta disponible | `asignaciones.tests.CrearAsignacionTests`, `VistasAsignacionTests.test_no_se_asigna_si_la_documentacion_no_esta_completa_ni_vigente` |
| T-42 | Un fallo al crear no deja cambios parciales (transacción) | `asignaciones.tests.CrearAsignacionTests.test_un_fallo_al_crear_no_deja_cambios_parciales` |
| T-43 | Finalizar y cancelar con confirmación conservan el historial y dejan la oferta Cubierta | `asignaciones.tests.VistasAsignacionTests` (`test_finalizar_desde_la_pantalla_con_confirmacion`, `test_cancelar_desde_la_pantalla_conserva_el_historial`, `test_el_listado_muestra_los_conteos_por_estado`) |
| T-44 | Baja automática paso a paso: 1ª y 2ª advertencia habilitan, 3ª da de baja, 4ª no reactiva | `transportistas.tests.LimiteDeAdvertenciasTests` (8 pruebas) |
| T-45 | Un transportista de baja no se asigna por formulario, POST directo ni sesión manipulada, y su historial se conserva | `transportistas.tests.LimiteDeAdvertenciasTests.test_un_transportista_de_baja_no_puede_asignarse_por_ninguna_via`, `test_el_historial_de_asignaciones_se_conserva_al_dar_de_baja` |
| T-46 | Filtros del listado de advertencias por transportista y por rango de fechas | `transportistas.tests.FiltrosDeAdvertenciasTests` (4 pruebas) |
| T-47 | El panel muestra las advertencias recientes y los transportistas dados de baja | `panel.tests.PanelInicioTests` (`test_el_panel_lista_los_transportistas_dados_de_baja`, `test_el_panel_no_muestra_la_seccion_de_bajas_si_no_hay_ninguna`) |
| T-48 | Todos los indicadores del panel coinciden con consultas directas a la base de datos (conteos por estado, por nivel, listas de advertencias y de bajas, alertas de SOAT y vencimientos) | `panel.tests_auditoria.PanelCoincideConLaBaseDeDatosTests` (3 pruebas) |
| T-49 | Todas las pantallas de negocio se renderizan y ninguna es pública | `panel.tests_auditoria.PantallasTests` (`test_todas_las_pantallas_se_renderizan`, `test_ninguna_pantalla_de_negocio_es_publica`, `test_la_pantalla_de_acceso_es_la_unica_publica`) |
| T-50 | Presentación en móvil y escritorio: vista móvil declarada, barra lateral fija/deslizante y tablas anchas desplazables | `panel.tests_auditoria.PantallasTests` (`test_todas_las_pantallas_declaran_la_vista_movil`, `test_la_estructura_responsive_esta_presente`, `test_los_listados_con_datos_no_desbordan_en_movil`, `test_las_pantallas_de_ficha_tambien_son_desplazables`) |
| T-51 | Mensajes de éxito, de error y de aviso visibles para el operador (documento vencido, advertencia registrada, tercera advertencia, oferta ya cubierta, reactivación bloqueada) | `panel.tests_auditoria.MensajesDeInterfazTests` (6 pruebas) |
| T-52 | Documentos obligatorios ausentes (licencia, revisión técnica, SOAT, nombre y dirección) y límite del día de vencimiento | `transportistas.tests_auditoria.DocumentosObligatoriosTests` (6 pruebas) |
| T-53 | La edición no puede dejar Activo un transportista con documentos vencidos, pero sí guardar documentación vencida en En Reserva | `transportistas.tests_auditoria.EdicionDeVigenciasTests` (3 pruebas) |
| T-54 | Clasificación por toneladas comprobada desde la interfaz (4.99 / 5.00 / 20.00 / 20.01 / 60.00) y nivel no manipulable | `transportistas.tests_auditoria.ClasificacionDesdeLaInterfazTests` (4 pruebas) |
| T-55 | Carga de archivos: se rechaza un `.png` o un `.jpg` cuyo contenido no es una imagen | `transportistas.tests_auditoria.FotografiaSospechosaTests` (3 pruebas) |
| T-56 | Los filtros de los listados sobreviven a la paginación y la búsqueda viaja codificada | `transportistas.tests_auditoria.PaginacionDeAdvertenciasTests` (5 pruebas) |
| T-57 | Límite exacto de vigencia del SOAT (vence hoy = vigente; venció ayer = bloqueado) | `asignaciones.tests_auditoria.VigenciaDelSoatTests` (4 pruebas) |
| T-58 | Al confirmar se revalidan las reglas: si la oferta se cubrió o el transportista pasó a Baja entre los dos pasos, no se crea nada | `asignaciones.tests_auditoria.RevalidacionAlConfirmarTests` (4 pruebas) |
| T-59 | Los once escenarios críticos de la auditoría, concentrados en una sola clase | `asignaciones.tests_auditoria.EscenariosCriticosTests` (11 pruebas) |
| T-60 | El comando de datos ficticios es idempotente, no borra nada, no crea usuarios y deja el estado de demostración esperado | `panel.tests_comandos.DatosDemoTests` (18 pruebas: cobertura de niveles, estados, tipos de vehículo, documentación vencida y por vencer, estados de asignación, elegibilidad del recorrido documentado y formato de los identificadores) |

Pruebas adicionales relevantes: unicidad de documento y placa, unicidad de RUC, unicidad del
código de oferta, nivel recalculado al editar, coherencia de la advertencia con la asignación,
oferta cubierta que no vuelve a Disponible, motivos de no elegibilidad mostrados al operador,
filtros de los listados, panel con vencimientos próximos y contraseñas gestionadas por Django.

---

## H. Suposiciones, riesgos y decisiones pendientes

### Suposiciones

1. Runtime **Python 3.13.5** en lugar de 3.12 (decisión D1, justificada en DECISIONES.md).
2. La fotografía del vehículo es requisito obligatorio y el SOAT solo se exige antes de asignar.
3. El nivel no es editable: siempre se deriva de la capacidad; la certificación no lo altera.
4. Un solo vehículo por transportista (campos en la misma tabla, sin historial de vehículos).
5. La asignación es irrepetible por oferta (`OneToOne`), con estados Activa, Finalizada y Cancelada;
   cancelar conserva el historial pero no libera la oferta.
6. «En Reserva» no puede recibir asignaciones; «Baja» tampoco y no se reactiva desde la interfaz.
7. Sin registro público de usuarios: las cuentas las crea un Administrador en `/usuarios/` (o con `createsuperuser`); los permisos dependen del rol (D16).
8. Catálogos de nivel y tipo de vehículo como `TextChoices`, sin tablas de catálogo.
9. Moneda única (soles) sin campo de moneda; no se definieron comisiones ni penalidades.

### Riesgos y mitigación

| Riesgo | Mitigación aplicada |
|---|---|
| Desviación del runtime respecto al enunciado | Documentada (D1) y verificada: código sin características exclusivas de 3.13; migrar a 3.12 es inmediato |
| Dos operadores cubriendo la misma oferta a la vez | `transaction.atomic()` + `select_for_update()` + validación repetida dentro de la transacción + `UniqueConstraint` parcial |
| Pruebas que caducan con el tiempo | Fechas siempre relativas a `timezone.localdate()` |
| Fotografías grandes o de formato no válido | Validación de tamaño (≤ 5 MB) y extensión (JPG/PNG) en el modelo, **más** la comprobación del contenido real de la imagen que hace Django/Pillow al recibir el archivo (probada con archivos renombrados) |
| Documentos que vencen sin que nadie intervenga | El panel avisa de vencimientos ≤ 30 días; la asignación se bloquea con SOAT vencido. El cambio automático de estado por vencimiento no estaba especificado (P1) |
| Consultas N+1 al evaluar candidatos por oferta | Aceptable en el volumen del MVP; `select_related`/`prefetch_related` en los listados principales |

### Decisiones pendientes

P1 cambio automático de estado por vencimiento documental ·
P3 anulación/reasignación de ofertas cubiertas y penalidades ·
P4 reactivación de un transportista en Baja · P5 confirmación del formato `OF-00001`.
(P2 rechazo de reemplazo: resuelta, D19 · P6 roles de usuario: resuelta, D16 ·
P7 vigencia del SOAT frente al inicio: resuelta, D17 · P8 fórmulas financieras: adoptadas con pendientes, D20.)
Detalle en [DECISIONES.md](DECISIONES.md).

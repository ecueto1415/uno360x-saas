# Revisión del SaaS publicado — 1 de noviembre de 2026

Cambios realizados y comprobados sobre la VM del SaaS. Las marcas de respaldo y logs usan UTC, por lo que figuran como 2 de noviembre. El Odoo nativo que usa OUTSOLUTECH no se migró ni se reinició.

## Comportamiento corregido

- Al terminar la preparación o iniciar sesión, se abre automáticamente el resumen UNO360X. Un fallo de apertura conserva un botón para reintentar; una prueba vencida no se reactiva.
- La empresa se configura una sola vez al entrar. Los siguientes accesos conservan los ajustes del cliente y su nombre elegido.
- El inicio y la página de planes reconocen la sesión: muestran Salir y revocan el acceso al pulsarlo. Volver con Atrás vuelve a validar las páginas privadas.
- El estado público no revela correo, empresas ni el token CSRF general. Usa CORS limitado a los dos orígenes de la web y un token exclusivo para cerrar sesión.
- Base es la única selección inicial. Las opciones elegidas en precios pasan al alta; el historial conserva la selección y solo se aceptan los tres identificadores conocidos.
- Formularios, favicon, títulos y POS conservan la identidad UNO360X. El logo propio de cada empresa en documentos permanece independiente.
- POS conserva una salida segura, sincroniza el pedido y permite regresar al selector de cajas sin cerrar el turno. El arqueo se hace desde Cerrar caja registradora.
- Se corrigió una pantalla vacía causada por el rechazo inmediato de solicitudes concurrentes. Cuenta dispone de 8 conexiones y el espacio de 24, con cola breve y límites separados; no comparten el antiguo cupo global de 6. La infraestructura conserva sus límites de memoria, CPU y plazas.
- Los resultados de búsqueda abren un menú autorizado que tiene una acción real, en lugar del contenedor raíz sin pantalla. Solo la identificación del modelo de la acción usa sudo; las consultas a registros mantienen el usuario, sus reglas y su empresa.
- La copia pública describe la prueba real y los límites actuales de las funciones.

## Validación realizada

- 114 pruebas Python aprobadas en la VM y dos suites Node para el flujo real de JavaScript.
- 8 pruebas del addon aprobadas al migrar tanto la empresa ficticia como el tenant SaaS existente. Las cuatro combinaciones Base/opciones conservan la estructura de navegación y sus permisos.
- 147 rutas del menú y 134 cargas de vistas comprobadas con el propietario ficticio, sin errores.
- Recorrido público de planes, selección mensual/anual, alta, confirmación HTTPS, sesión y preparación de una empresa ficticia con los tres módulos opcionales. La entrada al resumen fue automática.
- Navegación visual de contactos y formulario nuevo, CRM, cotizaciones, facturas, gastos, proyectos, compras, inventario, empleados, asistencias, ausencias y tableros. Los ejemplos que se ven detrás del aviso de lista vacía son muestras del cliente web, no registros comerciales cargados en la base nueva.
- Jenifer respondió una consulta interna CxC de solo lectura. Búsqueda sin coincidencias y con resultados propios, incluido el enlace a contactos, verificadas con usuario no administrador.
- Caja ficticia en español/DOP: apertura cero, una venta de RD$100 en efectivo simulado, recibo UNO360X, salida, reentrada y cierre sin diferencia. Una nueva sesión queda únicamente en control de apertura tras el cierre; no se abrió otro turno con ventas.
- Cuenta y empresa duplicadas, rechazo entre empresas, origen ajeno, ausencia de CSRF y token de confirmación inválido cubiertos. La recuperación HTTPS revocó sesiones previas y rechazó tanto el token reutilizado como la contraseña antigua.
- Sitio y menú móvil revisados; módulos y resumen probados a 390 × 844. La emulación temporal se retiró al terminar.
- Salir desde la web principal y posterior Atrás/recarga bloquearon el espacio privado. Se dejó abierto el login anónimo real.
- Correo: TLS, autenticación SMTP y NOOP correctos. Esta revisión no envió mensajes de prueba a terceros; los avisos del fixture se capturaron en memoria. La recepción en un buzón externo no se certifica con esta revisión.
- El formulario comercial se revisó y se comprobó su validación obligatoria sin enviar una solicitud ni crear un lead en el Odoo operativo.

## Protección y limpieza

Odoo nativo: PID 2195, cero reinicios; SHA-256 de configuración c3f24e40bd65d4998d3f3d8bdae0bafcd87a93290cd6a99ac35021cb946d71aa. El administrador ecueto@outsolutech.com mantiene 67 grupos. Las fechas originales de la prueba magiccomputer permanecen iguales.

La cuenta ficticia de esta revisión quedó inactiva, sus sesiones revocadas y sus contenedores detenidos. Sus datos y archivos se conservan para auditoría. Queda un tenant activo y una plaza libre. No se cambiaron credenciales de correo, Jenifer ni DGII, ni se actualizó Ubuntu.

## Base común y próximos despliegues

La versión del entorno es 18.0.1.2.3 del addon uno360x_workspace. Cuenta, worker y master apuntan al mismo código comprobado; el perfil de instalación identifica el contenido con un fingerprint. Los clientes nuevos utilizan ese perfil.

Para actualizar clientes existentes, usar deployment/workspace_release.py por tenant, con --apply después del plan de solo lectura, deteniendo únicamente worker/pilot durante la migración. El procedimiento respalda control, base y archivos, ejecuta las pruebas, registra tenant_releases y conserva las fechas de prueba. Un push a GitHub por sí solo no migra las bases. No incluir el Odoo nativo ni bases ajenas al registro SaaS en este recorrido.

## Alcance pendiente del producto

La emisión fiscal requiere la integración y habilitación verificadas por empresa; no se validó una emisión DGII real. El cálculo legal de nómina y la conexión de Jenifer a IA externa continúan pendientes, al igual que precios y contratación comercial. No se certificaron impresoras físicas, bancos, pasarelas de pago ni todos los procesos contables posibles. Esta revisión cubre los accesos y recorridos descritos, no una auditoría completa de cada motor empresarial.

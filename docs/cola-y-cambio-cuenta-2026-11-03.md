# Cola de creación y cambio de cuenta — 2026-11-03

La solicitud de una tercera empresa permanecía en `queued/capacity` por la política anterior `max_active_tenants: 2`. Entrar con una sesión abierta llevaba nuevamente a la preparación y no ofrecía cambiar de cuenta en esa pantalla.

## Corrección publicada

- La pantalla de preparación ofrece **Iniciar sesión con otra cuenta**. Cierra la sesión central, limpia el borrador local y cancela el sondeo; la solicitud del servidor continúa sin duplicar ni cancelar la empresa.
- `/web/login?cambiar=cuenta` presenta la elección de cuenta cuando existe sesión, evitando el acceso automático hasta decidir.
- Las respuestas tardías del sondeo no deben reemplazar una pantalla posterior: se comprueba la revisión de pantalla tras las operaciones asíncronas.
- La admisión usa `max_active_tenants: null` y comprueba capacidad real y comprometida. No hay cupo comercial fijo; tampoco capacidad ilimitada. Cuando falta capacidad se conserva la cola y no se detiene otra empresa.
- El grupo SaaS conserva techo de 3 GiB y 150% CPU en esta VM. Cada aplicación tiene 640 MiB y PostgreSQL 192 MiB. Una nueva admisión exige 1088 MiB de margen y al menos 2 GiB disponibles en el host. Se reserva la capacidad máxima de los espacios ya asignados.
- La comprobación de expiraciones del trabajador se realiza cada 60 segundos, evitando consultas continuas al motor de contenedores. El acceso sigue validando la vigencia en cada solicitud.
- La base nueva espera a que termine el PostgreSQL de arranque y a que exista su base específica. El restaurador solo acepta plantillas verificadas de la misma versión y bases nuevas vacías; nunca sobreescribe una base de cliente.

## Alcance y comprobaciones

Se conservaron los módulos y las versiones de producto de las empresas existentes. Los cambios visuales en preparación no forman parte de esta corrección urgente. Solo se reinició el trabajador SaaS; Odoo nativo, aplicaciones de clientes y gateway no se reiniciaron.

Validación en la VM: 169 pruebas Python y las dos suites Node de alta y navegación, aprobadas. Comprobación del JavaScript servido por el origen y apertura del login público en navegador. Las pruebas de cambio de cuenta verifican que no se envía una nueva creación.

Las copias previas de código y configuración se conservan en directorios privados `incident-account-queue-*` y `admission-activation-*`. Para revertir la política hay que restaurar código y política compatibles juntos, detener primero el trabajador y respetar cualquier preparación ya iniciada; no se borran recursos ni bases.

La creación pendiente conserva su identificador y empieza sus 15 días solamente al alcanzar `ready_local`. El tiempo de creación de esta solicitud no representa el tiempo de restauración de las nuevas plantillas que siguen en validación.

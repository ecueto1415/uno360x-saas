# Recuperación del registro y prueba concurrente — 04/11/2026

## Incidente verificado

Se revisaron los dos intentos recientes sin duplicarlos. Carwash terminó en unos20 segundos y su acceso propietario al bridge Odoo y consulta de sesión pasaron. Prueba Empresa mantiene preparación queued/capacity, sin pasos ejecutados, cómputo asignado ni inicio de los15 días. Ambos correos están verificados.

La política es de admisión abierta con presupuesto protegido, no un cupo comercial ilimitado. La VM reportó7600568KiB de RAM física; el cgroup SaaS tiene3758096384bytes (3.5GiB). Hay cuatro empresas activas con aplicación de640MiB, PostgreSQL compartido y reserva de servicios/arranque. La comprobación conservadora de memoria comprometida rechaza la quinta. No se observó agotamiento total de RAM: había aproximadamente4.6GiB disponibles en el host. No se incrementaron límites, no se detuvieron clientes y no se retiró la protección para forzar otra empresa. Las15 reservas son bases/archivos preparados, no recursos de ejecución para15 aplicaciones simultáneas.

## Corrección publicada

La API de entrada distingue preparación, mantenimiento y espera de capacidad con códigos explícitos409. No intenta abrir una empresa en cola ni llama verificación de correo para resolver capacidad. Se reemplaza el aviso genérico de verificar por el estado real.

El cliente conserva la sesión ante fallos de red (solo401 limpia la sesión), cancela solicitudes sin respuesta a los20 segundos y reanuda la consulta de preparación tras un fallo. Los reintentos respetan cambios de pantalla; no vuelven a crear empresas y no repiten envíos de confirmación. La pantalla informa que correo y solicitud están confirmados cuando espera capacidad, permite cambiar de cuenta y ofrece entrada a quienes ya confirmaron el correo.

Publicación:2026-11-04-signup-recovery, fuente /srv/uno360x-saas/releases/signup-recovery-20261104T230508Z/source. Solo se cambiaron control/UI y sus pruebas; fingerprints de módulos y bases de clientes se conservaron.198 pruebas Python pasaron; suite Node del recorrido y prueba dirigida del timeout pasaron. Origen y recurso HTTPS externo se verificaron; la VM recibió403 al consultar Cloudflare, pero la comprobación externa desde el PC devolvió200 con el código nuevo. Servicios SaaS y Odoo nativo activos; el publicador confirmó que el nativo no cambió.

## Simulación de diez registros simultáneos

Se usó el mismo código HTTP publicado, en la misma VM, con diez clientes sincronizados por barrera en cada fase, base temporal independiente y entrega de correo capturada en memoria. Se limitó la prueba a50% de un núcleo y384MiB mediante systemd-run --user --scope. No tocó registros reales, no envió correo, no aprovisionó Odoo y eliminó sus datos ficticios al terminar.

Una primera ejecución con direcciones.example.test confirmó el rechazo esperado del filtro público para dominios sin correo real; no es un fallo de concurrencia. La ejecución válida usó direcciones ficticias bajo example.com con transporte capturado localmente.

Resultado válido:10/10 cuentas registradas y verificadas,10 sesiones iniciadas,10 solicitudes de empresa en cola. Se repitió la creación para cada cuenta:20 llamadas devolvieron las mismas10 empresas, sin duplicados.60 peticiones HTTP devolvieron200. Duración de la ráfaga completa4.299s; memoria máxima del proceso159.8MiB; CPU2.001s (46.5% medio de un núcleo bajo el límite50%). Memoria disponible mínima del host4618.8MiB. CPU total del host42.6% incluye también trabajo ajeno a la prueba. Accesos a identidad y Odoo respondieron200 antes y después; PID nativo no cambió.

Máximos por petición: registro0.144s, confirmación1.058s, login1.113s, creación0.849s y consulta0.345s. Es una única ráfaga controlada: no demuestra diez empresas Odoo operando, carga sostenida, correo real, TLS/Cloudflare ni clientes desde internet.

Reproducción: deployment/benchmark_signup_registration.py bajo la cuenta SaaS con límites de CPU/memoria. El script falla con código distinto de cero si no completan los diez clientes. Evidencia JSON privada en /var/lib/uno360x-saas/signup-burst-10-result.json y copia entregada al usuario. Sigue pendiente resolver capacidad de ejecución para activar Prueba Empresa y validar carga de empresas reales antes de comercializar.

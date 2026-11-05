# Veinte creaciones simultáneas sin admisión por capacidad

La tercera ronda completó veinte creaciones por HTTPS y veinte comprobaciones de acceso simultáneas. Las cuentas confirmadas eran una precondición: no se enviaron correos reales y el tiempo de correo no se incluyó. No se ejecutó carga comercial ni se enviaron comprobantes a DGII.

## Correcciones

- `enforce_admission` controla explícitamente la admisión del alta y del trabajador. Su valor ausente conserva la protección anterior. En esta VM el propietario solicitó `false`; los límites del sistema operativo y todas las comprobaciones de propiedad, imagen, red y credenciales permanecen.
- El límite de transporte de solicitudes autenticadas se aplica por cuenta, conservando la limitación por IP para tráfico anónimo y los límites de autenticación existentes. Así los clientes detrás del mismo proxy no comparten un contador de sondeo.
- El arranque de una instancia con una sola base validada redirige exclusivamente la conexión literal `postgres` de las notificaciones de Odoo a la base propia. No concede CONNECT a la base de mantenimiento ni modifica privilegios entre clientes. El proceso nativo de OUTSOLUTECH no carga este código.
- El grupo SaaS alcanzó `TasksMax=512`. Se aumentó a 1024, sin cambiar CPUQuota=150%, MemoryHigh=3G ni MemoryMax=3584M. El ejemplo de configuración registra estos valores.

## Medición

Los veinte actores se autenticaron, enviaron `/trial/create` al mismo tiempo, consultaron el estado normal, abrieron `/spaces/open` y consumieron su entrega de sesión mediante HTTPS. Cada HTML debía contener el nombre de su propia empresa. Al terminar se volvieron a pedir simultáneamente los veinte paneles autenticados. No hubo adaptador especial, prioridad de pruebas ni intervención para empujar las empresas. El trabajador normal procesa la preparación en serie. Al inicio también reconcilió las empresas existentes después de un reinicio.

El detalle y las métricas están en [el resultado estructurado](benchmarks/2026-11-04-open20.json). Primera empresa accesible: 57,5 s; última: 563,0 s. Preparación activa media: 26,3 s, con rango 17,9–39,0 s. La cola explica la espera acumulada de las últimas empresas.

## Rondas previas y precisión del medidor

La primera ronda aceptó veinte solicitudes pero preparó cinco; quince fallaron al notificar después de guardar el administrador. La comprobación adicional logró cuatro accesos y un error 500. La segunda preparó trece; siete fallaron en diversas etapas al alcanzar el límite de procesos. La tercera aprobó veinte preparaciones y veinte accesos, incluidos los veinte accesos finales juntos.

El medidor inicial reenviaba Origin en una redirección GET entre subdominios; se corrigió para imitar una navegación del navegador. En la segunda ronda también hubo un bloqueo transitorio del archivo temporal del medidor en Windows; la tercera incorpora reintentos del guardado sin alterar el flujo del servidor. Se conservaron los resultados originales y las comprobaciones complementarias, sin presentar esos errores del medidor como fallos demostrados del servicio.

## Validación y aislamiento

Pasaron 205 pruebas automatizadas, incluidas dos sobre el destino de las notificaciones y la preservación de las demás conexiones. La tercera ronda registró cero rechazos por procesos y cero OOM kills. OUTSOLUTECH conservó PID y configuración, sin reinicios ni fallos en los 279 sondeos HTTP de la ventana medida. Los sondeos fueron al acceso por loopback; no representan una sesión comercial completa.

Se borraron las tandas sintéticas entre rondas con validación de identificadores, etiquetas y vínculos de recursos. Antes del borrado del registro se comprobaron las huellas de las filas ajenas a la prueba. El servidor PostgreSQL compartido y las empresas reales no son objetivos de la limpieza. El cierre final y la restauración de los servicios SaaS se registran en el informe operativo.

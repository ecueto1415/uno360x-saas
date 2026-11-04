# Medición natural de veinte solicitudes de creación — 04/11/2026

El usuario canceló la ejecución controlada y pidió borrar las cuentas de simulación y medir el tiempo y los motivos de fallo mediante el flujo normal, sin excepciones de admisión ni supervisor de prueba.

## Retirada de la ejecución controlada anterior

Se detuvo inmediatamente la unidad de preparación y el supervisor. El lote2ed10ff6 había creado20 registros, asignado6 bases y validado5 espacios; quedó interrumpido por orden del usuario, sin ejecutar la fase de diez sesiones ni crear cotizaciones. Estos resultados NO representan el flujo natural y no se usan para afirmar capacidad comercial. Antes de detenerlo, las cinco preparaciones verificadas registraron39.563,42.380,45.392,43.505 y58.686s; otro intento había fallado en identidad y dos estaban en asignación de base al cancelarse.

Borrado autorizado del lote:6 bases PostgreSQL,6 contenedores de aplicación,6 volúmenes de archivos,8 redes y8 directorios de tenant. El servidor PostgreSQL compartido se conservó. Cada recurso se comprobó contra ID, etiquetas, binding y fingerprint del lote; se hicieron respaldos privados antes de eliminar. Después se borraron exactamente20 cuentas/empresas y sus relaciones; hashes de los registros ajenos al lote conservados. El supervisor especial quedó retirado. No se modificaron los límites generales ni las empresas reales.

## Medición mediante el servicio público real

Condición inicial:20 cuentas ficticias confirmadas antes de iniciar el cronómetro. Se prepararon utilizando los servicios normales de identidad y entrega local capturada, sin correo externo; el tiempo de correo y confirmación no forma parte de esta medición. El propietario había indicado notificaciones@uno360x.com; se usaron20 alias con sufijo de medición exclusivamente para los fixtures.

Los clientes se conectaron desde el PC a https://cuenta.uno360x.com mediante HTTPS público/Cloudflare, cada uno con su cookie y CSRF. Los20 inicios de sesión fueron aceptados. Una barrera lanzó20 POST /trial/create al mismo tiempo. No se alteró la admisión ni se forzó al worker a preparar espacios.

Resultado:0/20 empresas creadas,0/20 preparadas y0 accesos utilizables demostrados. Las20 respuestas fueron503 con código activation_capacity_unavailable. Tiempo medio de respuesta0.281s, máximo0.344s y duración total de la ráfaga0.375s. Es el tiempo de RECHAZO, no de creación. No hubo429, fallos de login ni bloqueos SQLite en esa ráfaga.

Causa observable: la política vigente informó ausencia de capacidad de ejecución y rechazó cada solicitud antes de reservar tenant o crear el trabajo. No se iniciaron veinte aplicaciones Odoo; esta medición no prueba saturación física, caída del servidor ni duración de aprovisionamiento sin esa política. Demuestra que el recorrido actual NO satisface veinte altas completas disponibles a la vez.

Se eliminaron los20 fixtures de cuentas sin empresa después de recoger resultados; no quedan cuentas ni clientes de ambos lotes. El panel se regeneró, SQLite quick_check correcto, servicios de identidad/worker/Odoo nativo activos. Reservas al cerrar:10 ready, sin entradas building; se dejó actuar al mecanismo normal de reposición. No se envió correo real, no se facturó y no se generaron cotizaciones.

Evidencia entregada: UNO360X_Medicion_20_Creaciones_Reales.json. Sigue pendiente resolver/dimensionar la capacidad y repetir el criterio correcto: veinte espacios utilizables y diez sesiones con actividad, contando cualquier rechazo o espera como fallo, no como éxito.

# Simulación visible de20 empresas: fallo, corrección y retirada — 04/11/2026

## Alcance y resultados reales

El propietario pidió20 empresas ficticias visibles en el administrador y actividad simultánea de diez. Posteriormente canceló la prueba y ordenó borrar esas empresas. Nunca se inició la fase de diez instancias Odoo ni se crearon cotizaciones: la admisión de ejecución seguía sin capacidad.

Se usaron los servicios normales de registro, confirmación, login y solicitud de empresa sobre el registro real, con veinte tareas concurrentes, nombres SIMULACIÓN20, transporte de correo capturado y credenciales sintéticas privadas. No fue una prueba del transporte HTTP público. Batch34b4ed3c. Primera oleada:16/20 completaron,4 fallaron por sqlite3.OperationalError database is locked. Todas las empresas creadas estaban queued; no hubo bases ni aplicaciones Odoo de prueba asignadas.

Después de corregir la concurrencia se recuperaron los cuatro intentos mediante operaciones idempotentes:20/20 solicitudes quedaron registradas, sin duplicados, en6.98 segundos en la pasada de recuperación. No se considera aprobada la activación de20 empresas: todas seguían esperando capacidad. El cupo de registros ya era abierto; no se eliminó la protección de RAM.

## Corrección de la base central

Registry usa WAL y busy_timeout15s. El cálculo scrypt de login se ejecuta antes de tomar el bloqueo de escritura. Dentro de la transacción se vuelven a comprobar hash, cuenta activa y verificación para impedir una carrera con cambios de contraseña. Se probaron20 altas concurrentes nuevas en base temporal y el caso de reset durante la comprobación de contraseña.200 pruebas pasaron en release2026-11-04-signup-concurrency, publicado23:22:07UTC.

El exportador administrativo necesitó compatibilidad con el índice SHM de WAL. Su sandbox permite acceso al directorio de control para ese índice, mantiene el fichero principal control.sqlite3 como ReadOnlyPaths y sigue conectando mediante mode=ro. Drop-in40-sqlite-wal-reader.conf; exportación reactivada correctamente. La unidad del repositorio refleja la misma configuración. No se actualizó Ubuntu ni la versión de SQLite.

## Eliminación autorizada

Tras detener brevemente el worker y respaldar el registro con la API de backup SQLite, se validaron los veinte IDs contra el manifiesto, nombres y correos exclusivos del lote. Se comprobaron cero directorios de tenant, bases enlazadas o recursos físicos. Se eliminaron exactamente20 cuentas,20 empresas,20 membresías,20 tokens,20 borradores de alta,20 solicitudes y20 fichas de prueba. Los hashes de todas las cuentas/empresas/solicitudes/fichas ajenas al lote se conservaron idénticos. FK e integridad SQLite correctas. Se conservaron las empresas reales. Se retiraron las contraseñas sintéticas del manifiesto. El panel fue regenerado y muestra cero empresas del lote.

## Evitar nuevas preparaciones indefinidas

El worker publica una señal de admisión cada5s. El HTTP de producción exige una señal positiva de hasta15s antes de crear una empresa nueva. Sin capacidad o con señal obsoleta devuelve503 activation_capacity_unavailable antes de reservar tenant o crear trabajo; el formulario conserva sus datos. Las solicitudes existentes siguen recuperables e idempotentes incluso si la capacidad se agota. No se impide registrar cuentas; se evita aceptar una activación que no puede arrancar.

201 pruebas pasaron en release2026-11-04-signup-admission, publicado23:33:28UTC, sin migrar bases de clientes ni modificar Odoo nativo. Comprobación con cuenta QA temporal y el servicio real de cuenta:503 correcto, cero empresas y trabajos creados, cuenta QA eliminada al terminar. Ruta actual /srv/uno360x-saas/releases/signup-admission-20261104T233215Z/source.

## Pendiente indispensable

No se ha demostrado actividad simultánea de diez empresas. Sigue pendiente dimensionar/ampliar/distribuir recursos de ejecución y repetir la prueba completa. El registro concurrente y la activación de una aplicación Odoo por empresa son capacidades diferentes. No se garantiza activación instantánea de20 empresas en la VM actual, ni que aumentar la espera de SQLite resuelva el presupuesto de memoria.

# Cobertura nocturna ClamAV para SaaS

Se conserva el escaner existente en /usr/local/sbin/uno360x-antivirus-scan y su servicio/timer. Se agregan releases y runtime de /srv/uno360x-saas, helpers de /usr/local/lib/uno360x, volumenes propios *-odoodata/_data (adjuntos y addons), temporales tmp/var/tmp de las capas de contenedores y carpetas uploads/tmp SaaS cuando existan. Los nuevos volumenes se descubren en cada ejecucion, sin seguir enlaces simbolicos ni salir de /var/lib/uno360x-saas.

No se recorre el almacenamiento completo de contenedores. Se excluyen explicitamente los volumenes PostgreSQL, control y tenants (credenciales/configuracion privada), sesiones, caches y las claves/certificados que ya excluia el escaner. La exclusion por nombre de claves no identifica certificados fiscales renombrados dentro del filestore; estos quedan bajo el escaneo local habitual de adjuntos, sin envio a terceros.

Se mantienen la ventana nocturna 01:00-05:00 America/Santo_Domingo, bloqueo contra actualizaciones simultaneas, comprobacion de memoria disponible y firmas, limites de archivos/recursion/tiempo, prioridad reducida y modo solo deteccion. No se activa borrado, traslado ni cuarentena automatica. No se modifica el unit, su aislamiento o sus limites de recursos.

Validado: sintaxis Python y plan de rutas sin ejecutar el motor, adjuntos existentes incluidos, volumenes de bases y credenciales fuera de objetivos, temporales encontrados, opciones de no seguir enlaces y solo deteccion conservadas. No se ejecuta un analisis completo de dia. La proxima ejecucion nocturna aplicara la cobertura nueva; el ultimo resultado de analisis no se sustituye por la validacion del plan.

Copiar deployment/uno360x-antivirus-scan.py al ejecutable root existente conservando sus permisos. Reversion: recuperar la copia root en /var/lib/uno360x-antivirus/config-backups/scanner-before-saas-*.py. No requiere reiniciar Odoo, SaaS o VM.

# OUTSOLUTECH: espera por intentos del acceso unificado

El usuario informó contraseña incorrecta y luego el mensaje
«Espera unos minutos antes de volver a intentarlo». La página nativa y
odoo18.service respondían, cuenta id 2 activa, última escritura 2026-11-13.
No se leyeron hashes ni se cambió ninguna contraseña.

El texto de espera proviene de control/unified_access.py: 8 intentos por email
en 300 segundos. Por petición explícita «desahabilitalo», se exime únicamente
a los emails que constan en el directorio operativo del servidor, vigente
durante 300 segundos. El directorio usa huellas y se actualiza por el servicio
existente. Ausente, malformado o vencido conserva el límite.

Se mantiene autenticación nativa, origen, CSRF, concesión de un solo uso,
control de transporte 60 solicitudes/minuto y controles del SaaS para el resto.
La excepción reduce protección frente a intentos dirigidos a cuentas operativas
conocidas; fue solicitada por el usuario y no elimina la comprobación de clave.
No afecta al límite de creación de empresas, al antibot ni al correo.

14 pruebas de acceso unificado aprobadas, incluida excepción operativa y
directorio vencido. Publicado únicamente el archivo del control unificado,
con copia previa unified_access.before-native-account-throttle-20261119.py.
Reiniciado uno360x-saas-pilot.service; no se reinició Odoo.
Verificación: directorio configurado, ecueto reconocido/exento, email desconocido
mantiene límite, ambos servicios activos y login ERP HTTP 200.

Esto no resuelve una clave que el autenticador nativo rechace. El usuario
debe completar su recuperación si persiste, sin compartir secretos con el agente.

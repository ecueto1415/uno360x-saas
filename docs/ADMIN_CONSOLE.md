# Consola privada de administración UNO360X

Estado al 2 de noviembre de 2026 (hora dominicana): servicio publicado en https://admin.uno360x.com, DNS proxied y regla por host Full (strict) verificados. Certificado de origen válido hasta 1 de febrero de 2027. Pendiente la activación personal del propietario (contraseña y TOTP).

## Funciones implementadas
Consulta de clientes reales del SaaS, módulos, pruebas y vencimientos, miembros y uso de base/archivos. Cuatro combinaciones comerciales visibles, precios por definir. Recursos globales CPU, RAM y disco, última ejecución e historial de ClamAV, firmas y próxima ejecución en hora dominicana. Registro de accesos del panel y eventos del SaaS.

Esta versión es de consulta: no procesa cobros, cambia planes, suspende clientes, amplía pruebas ni aplica cuotas. Los 5 GB y el aviso al 80% son referencias visuales; falta implementar y probar el bloqueo técnico. No confundir la existencia de estas vistas con facturación o administración comercial completa.

## Aislamiento
Usuario de sistema uno360x-admin sin shell, sudo ni acceso al grupo SaaS; código exclusivo en /opt/uno360x-admin/current. Servicio 127.0.0.1:18185, limitado a 25% de una CPU y 192 MB. Exportador root de operaciones fijas y lectura, cada minuto; publica un JSON reducido sin documentos, certificados ni claves. El panel no puede leer /etc/odoo18.conf ni control.sqlite3.

OUTSOLUTECH conserva servicio odoo18, configuración, cuenta y 67 grupos del administrador. No se reinicia ni cambia su base, fechas de prueba, correo, Jenifer o credenciales DGII. El consumo del servidor sí incluye ambos entornos compartidos.

## Autenticación y primera activación
Propietario exclusivo ecueto@outsolutech.com. Credenciales propias: contraseña scrypt de 12–128 caracteres y TOTP obligatorio con protección contra repetición; ocho códigos de recuperación de un solo uso. Contraseña sola no habilita el panel. Sesión de 8 horas máximo y 30 minutos sin actividad humana; cookies Secure/HttpOnly/SameSite=Strict de host exclusivo. Registro de eventos sin contraseñas, tokens ni semillas. Limitación de intentos por IP y cuenta, comprobación de host y origen, CSRF y CSP.

Estado privado en /var/lib/uno360x-admin (0700), auth.sqlite3 y mfa.key (0600). La semilla está cifrada con la clave separada. No guardar esos archivos, enlaces de activación o códigos de recuperación en Git ni en informes.

Una vez publicado HTTPS y confirmado el acceso cerrado sin sesión, emitir localmente un enlace de activación mediante Auth('/var/lib/uno360x-admin','ecueto@outsolutech.com').new_enrollment() ejecutado como uno360x-admin, desde /opt/uno360x-admin/current. Enlace /activar#token=VALOR: dura 24 horas y se consume una vez; una nueva emisión invalida la anterior. Solo funciona si el propietario aún no está configurado. Entregar privadamente al propietario: él introduce y confirma su nueva contraseña y configura TOTP; el agente no escribe credenciales nuevas. Guardar los ocho códigos de recuperación fuera del navegador. No existe recuperación pública ni restablecimiento por correo en esta versión. La recuperación operativa del propietario y el respaldo cifrado del estado de autenticación siguen pendientes de definir antes de comercializar.

## Publicación aprobada y ejecutada
Nuevo A admin.uno360x.com a 140.82.47.80 con proxy Cloudflare; no cambiar registros existentes, MX, SPF o DKIM. Tras aprobación específica de la exposición administrativa, ejecutar deployment/publish_admin_https.py como root. Crea únicamente el vhost nuevo, obtiene un certificado dedicado mediante webroot usando la cuenta ACME existente y recarga nginx tras nginx -t. Si falla elimina solo su nuevo enlace y mantiene cerrado el proxy. Requiere directorio /var/lib/uno360x-acme y certbot existentes.

Extender la regla por host de Cloudflare Full (strict) a admin.uno360x.com después de obtener el certificado; conservar el modo y reglas del resto de hosts. Probar HTTPS público, /health, /api/overview=401, propietario activable, contraseña incorrecta, TOTP, sesión y cierre. No publicar como terminado antes de estas pruebas. Plantilla de nginx en deployment/nginx-admin-console.conf.

## Operación y reversión
Unidades deployment/uno360x-admin.service y uno360x-admin-export.{service,timer}. Exportador instalado en /usr/local/lib/uno360x-admin/export.py; snapshot /var/lib/uno360x-admin-export/snapshot.json root:uno360x-admin 0640. El exportador necesita acceso de escritura a los locks de Podman, no efectúa modificaciones de empresas.

Para revertir: deshabilitar exclusivamente el nuevo vhost admin, comprobar nginx -t y recargar nginx; detener y deshabilitar uno360x-admin y uno360x-admin-export.timer. Conservar el estado privado para recuperación; no borrar recursos ni detener servicios Odoo/SaaS. El código del panel se revierte cambiando únicamente /opt/uno360x-admin/current a una release previa y reiniciando uno360x-admin. No modificar la línea base del monitor de seguridad para ocultar cambios autorizados.

## Verificación
11 pruebas de autenticación/HTTP incluidas en tests/test_admin_console.py. Regresión VM: 146 pruebas Python y dos suites Node aprobadas, logs /var/lib/uno360x-saas/qa-runs/20261103T011044Z. Recorrido de vistas, búsqueda y ficha en escritorio; menú y recursos en móvil 390 px sin desbordamiento horizontal de página. QA visual usa frontend exacto desplegado y snapshot real con autenticación simulada solo en un servidor temporal localhost; no existe ese acceso simulado en el servicio desplegado. Activación real y recorrido por HTTPS público pendientes de los pasos anteriores.

Verificación pública posterior a publicación: inicio y health HTTP 200; APIs overview/session/activity HTTP 401 sin sesión; certificado de origen validado por CA y hostname, TLS 1.3. Regla Cloudflare d7938cbb203c4c0ab5826b835ebedc27 ampliada únicamente con admin.uno360x.com, manteniendo cuenta y piloto en Strict. Odoo PID 2195, cero reinicios, configuración y 67 grupos intactos. Alta del propietario y recorrido autenticado real pendientes de su intervención personal.

# Login unico: OUTSOLUTECH y SaaS

Entrada comun: https://cuenta.uno360x.com/web/login. Se verifican las credenciales SaaS y, para correos presentes en el directorio operativo, las credenciales nativas contra Odoo. No se copian hashes ni contrasenas entre sistemas y no se crean usuarios nativos. Si ambas autenticaciones autorizan espacios para el mismo correo, se muestran sus empresas. Si las contrasenas difieren, cada contrasena solo habilita su identidad autenticada. Una sesion de otro correo no se combina con la actual.

OUTSOLUTECH conserva la base operativa Outsolutech_prueba, credenciales, grupos y servicio original. Acceso directo de respaldo: https://erp.uno360x.com/web/login?db=Outsolutech_prueba. Salir en el entorno nativo primero cierra esa sesion y despues lleva al login central.

El acceso nativo usa JSON-RPC de Odoo en loopback con origen y base fijos, sin proxies de entorno ni redirecciones. La sesion autenticada se conserva solo en memoria del acceso central durante una hora. No se devuelve la cookie de Odoo a JavaScript. La entrada al ERP consume un pase aleatorio de 30 segundos de un solo uso via POST, con comprobacion del Origin central y Host ERP. La cookie nativa es HttpOnly, Secure y solo para ese host. Se verifica nuevamente uid y base antes de abrir. MFA pendiente no obtiene un pase: puede completarse mediante el acceso directo habitual. Las sesiones centrales nativas en memoria vencen al reiniciar el servicio de acceso; no se afectan las sesiones ya abiertas directamente en Odoo.

El directorio privado contiene solamente hashes SHA-256 de correos activos y fecha de actualizacion. Una tarea root de lectura SQL lo renueva cada minuto; no copia claves ni grupos. Si supera cinco minutos de antiguedad, la autenticacion nativa falla cerrada. La validacion nativa sigue siendo la autoridad sobre contrasena y acceso. El cliente remoto se conserva para los limites de intentos de Odoo; CF-Connecting-IP solo se utiliza desde las redes oficiales de Cloudflare verificadas en https://www.cloudflare.com/ips-v4 y https://www.cloudflare.com/ips-v6. Las demas conexiones usan su IP real de conexion. Nginx reemplaza la cabecera interna.

## Instalacion y reversibilidad

1. Copiar deployment/nginx-login-client-ip.conf al contexto http de Nginx (/etc/nginx/conf.d/uno360x-login-client-ip.conf). Revisar las redes de Cloudflare cuando cambien.
2. Instalar deployment/nginx-operational-access.conf en el snippet nativo ya incluido por los servidores 80 y 443. El selector estatico y el bloqueo del administrador de bases siguen vigentes.
3. Aplicar la cabecera X-UNO360X-Client-IP en el virtualhost central, como deployment/nginx-https-pilot.conf. Validar nginx -t antes de recargar.
4. Copiar deployment/refresh_operational_directory.py a /usr/local/lib/uno360x/refresh-operational-directory.py, root:root, sin escritura para SaaS. Instalar los dos units deployment/uno360x-operational-directory.*, daemon-reload, ejecutar el servicio y habilitar el timer. El fichero generado es root con grupo del usuario SaaS, modo 0640.
5. En /etc/uno360x-saas/https-pilot.json preservar el resto de las opciones y activar operational_login=true y operational_directory=/var/lib/uno360x-saas/operational-directory.json. Reiniciar solo uno360x-saas-pilot. No reiniciar Odoo ni el trabajador de aprovisionamiento.
6. Para revertir, operational_login=false y reiniciar solo el acceso SaaS. El acceso directo ERP permanece disponible. Las copias de configuracion previas estan en /var/lib/uno360x-saas/before-unified-login-* y unified-nginx-*.

## Validacion

135 pruebas Python aprobadas, incluyendo 12 de autenticacion unificada, caducidad, concurrencia de un pase, aislamiento, CSRF, Origin, directorio, MFA pendiente y direccion RPC fija; dos suites Node, con prueba de entrada nativa sin pasos de creacion y rechazo de destinos alterados. La autenticacion nativa correcta en estas pruebas se simula: no se conoce ni se ha cambiado la contrasena real del administrador.

Por HTTPS real se comprobaron login SaaS con cuenta ficticia verificada, cookie segura, sesion, aislamiento de empresas, rechazo de pase nativo para sesion solo SaaS, logout, clave incorrecta, origen ajeno, CSP, selector operativo 200, administrador de bases 404 y logout nativo hacia login central. La cuenta ficticia queda inactiva, sin empresa y sin correos reales. RPC nativo alcanzable sin autenticar. Pantalla publicada revisada en navegador.

Guardia operativa final: Odoo PID 2195, sin reinicios; hash de configuracion original conservado; administrador uid 2 conserva 67 grupos; fechas y perfil del cliente Magiccomputer intactos. No se modificaron datos comerciales, correo, Jenifer ni DGII.

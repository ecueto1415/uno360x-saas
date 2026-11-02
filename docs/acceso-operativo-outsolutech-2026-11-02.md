# Acceso operativo OUTSOLUTECH

La continuidad y la actividad reciente identifican Outsolutech_prueba como la base operativa. OUTSOLUTECH es otra base; no cambiar el destino por semejanza del nombre.

El selector enlazado desde el login estaba bloqueado por Nginx. Se habilita exclusivamente /web/database/selector como pagina estatica con el acceso a la base operativa ya permitida. Los endpoints de administracion, listado, backup y restauracion siguen bloqueados. El login SaaS incorpora un enlace separado al acceso operativo.

Instalacion: copiar deployment/nginx-operational-access.conf a /etc/nginx/snippets/uno360x-operational-access.conf y deployment/operational-access.html a /var/www/uno360x-operational-access.html. Incluir el snippet en ambos servidores nativos (80 y 443), antes del bloqueo /web/database. Ejecutar nginx -t y recargar Nginx. No reiniciar Odoo.

Verificado en vivo: selector 200; login operativo 200 y formulario de contrasena; manager y backup 404; enlace central publicado. No se dispone de la contrasena del administrador para verificar una autenticacion real. Sin cambios en datos, configuracion Odoo ni credenciales.

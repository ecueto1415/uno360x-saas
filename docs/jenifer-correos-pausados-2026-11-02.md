# Correos Jenifer pausados a solicitud de Cueto

Se deshabilito y detuvo jenifer-directa.timer y se detuvo jenifer-directa.service. El drop-in /etc/systemd/system/jenifer-directa.service.d/99-user-mail-pause.conf fija JENIFER_ALLOW_LIVE=no; el worker ya rechaza --live con ese valor. No se cambio su codigo ni las credenciales Microsoft 365.

En la base operativa Outsolutech_prueba se desactivaron solo las tareas Jenifer 54 (nomina dias de corte) y 55 (comprobantes automaticos de jornadas). Estas rutinas tambien preparan documentos: quedan pausadas sus ejecuciones automaticas completas; los registros existentes y el uso manual de Odoo se conservan. El usuario solicito detener los correos de Jenifer. No se desactivo la cola general de Odoo ni otros servidores de correo.

Se comprobo la cola de mail.mail del remitente de Jenifer: cero mensajes outgoing o exception al aplicar la pausa. No hubo mensajes que cancelar ni borrar. Queda registro de estados previos y tareas en /var/lib/jenifer-directa/mail-pause-20261102T143900Z.json, root 0600, fuera de Git.

Verificacion: timer disabled/inactive, worker inactive con JENIFER_ALLOW_LIVE=no, ambas tareas inactivas, cero correos Jenifer en salida. No se reinicio Odoo ni la VM. No se cambiaron contrasenas, permisos del administrador, DGII o correo SaaS.

Reactivacion solamente a nueva solicitud: revisar el registro previo, retirar el drop-in de pausa, daemon-reload, habilitar/iniciar el timer y restaurar los estados anteriores de las dos tareas mediante administracion de Odoo. Revisar primero envios pendientes; no reenviar automaticamente correos historicos.

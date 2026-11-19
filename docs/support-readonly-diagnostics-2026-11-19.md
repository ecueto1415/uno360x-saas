# Jenifer: orientación con configuración verificada

Ampliación del soporte solicitada para INCIVI y la versión común del SaaS. OUTSOLUTECH queda excluido.

## Qué verifica

El método público fijo `uno360x.workspace.support_diagnostics()` exige usuario interno y usa su entorno normal de Odoo. Recorre los menús autorizados y agrega una guía revisada de Contactos, CRM, Ventas, plantillas, facturación, bancos, cheques, Compras, Inventario, faltantes, ajustes de stock, POS, Proyectos, Mantenimiento, empleados, Nómina, contratos, adicionales, asistencia, ausencias, Jenifer y tableros. Mi empresa incluye razón social/RNC, logo, plantilla, USD, asistente fiscal y secuencias.

Comprueba presencia del RNC, moneda base, plantilla seleccionada, logo, monedas de tarifas, diarios por tipo, impuestos de venta, almacenes y estado local de habilitación fiscal y rangos por tipo/vencimiento. No devuelve claves, certificados privados, contenido de documentos, salarios, saldos ni facturas. La presencia de un certificado o rango local no equivale a una nueva validación o aprobación remota de DGII.

El gateway conserva la cuenta y la empresa de la sesión validada. Hace una única RPC fija con plazo de seis segundos y vuelve a validar los accesos después. No acepta nombres de modelo, métodos, dominios o tenant elegidos por el navegador. El diagnóstico se vincula al mensaje en `message_context`, con empresa y cuenta; una evidencia de más de diez minutos deja de presentarse como vigente. El redactor no tiene conexión directa a las bases de negocio.

Los mensajes humanos o reintentos ya registrados no generan otra consulta. Se validan formato y límites antes de leer Odoo. Un diagnóstico no disponible no pierde el mensaje del cliente: la respuesta debe reconocer qué no pudo verificar. La revocación de acceso sí se propaga y bloquea la operación.

Jenifer debe usar la evidencia en lugar de decir que carece de herramientas. Las consultas normales de uso no se pasan al equipo automáticamente si se pueden responder con el diagnóstico. El botón Hablar con el equipo conserva su función: detiene la IA y deja el hilo en la cola del propietario.

## Validación realizada

- 18 pruebas unitarias de almacenamiento y captura: aislamiento, evidencia expirada, identidad incorrecta, revocación, permisos y operaciones fijas.
- Pruebas HTTP del gateway y panel: autenticación, origen, CSRF y reintentos.
- Un recorrido HTTP integrado aislado: cliente envía, worker responde, cliente pide equipo, propietario recibe la misma conversación y responde, cliente ve la respuesta, y la IA permanece detenida. Un reintento no duplica la respuesta humana.
- INCIVI real: diagnóstico ejecutado dentro de una transacción PostgreSQL de solo lectura. Confirmó RNC configurado, DOP, plantilla y configuración local, con seis documentos y seis rangos sin cambios en los cursores fiscales.
- Llamada real acotada a la conexión existente de Jenifer, en conversación QA aislada con la evidencia de INCIVI: ubicó las plantillas, confirmó RNC configurado y detectó que solo DOP estaba habilitado. No derivó innecesariamente al humano. No se emitió ni firmó ningún comprobante.
- Empresa SaaS con todos los módulos: guía disponible de 25 opciones y menús autorizados. Usuario de RR. HH. temporal, eliminado por rollback: acceso de empleados y sin acceso de Nómina o contratos. No quedó un usuario nuevo ni se enviaron invitaciones.
- Ocho combinaciones de módulos reconstruidas desde plantillas limpias y verificadas; una reserva preparada según el objetivo de desarrollo de un espacio. Perfiles de las dos empresas actuales sincronizados. Worker de preparación y timer de reservas restaurados.

La comprobación visual final en las sesiones reales de cliente y propietario sigue pendiente de que el usuario inicie sesión en el navegador integrado. No se sustituyó esa comprobación por sesiones fabricadas ni se afirma que esté terminada.

## Publicación y reversión

Código común en `addons/uno360x_workspace/models/support.py` y `support_guide.py`; capturador en `control/support_context.py`; cola y redactor en `support_center`. No se cambiaron credenciales ni permisos de negocio. La guía se instala tanto para Base Empresarial como para las combinaciones de módulos; solo muestra lo que corresponde al plan y usuario.

Respaldo anterior en `/var/backups/uno360x-support-diagnostics-20261119`. Revertir exige restaurar modelos y soporte previos y volver a sincronizar huellas, empresas y reservas del SaaS. Conservar las conversaciones y la tabla adicional; no borrarlas para revertir código. El proceso Odoo de OUTSOLUTECH no se reinició.

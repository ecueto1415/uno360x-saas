# Captura de gastos desde fotos conectada a Jenifer en OUTSOLUTECH

El usuario autorizó conectar el chat productivo y crear únicamente borradores
para revisión de contabilidad. Se reutilizó la conexión IA existente, sin
crear/modificar claves. El Formato 606 continúa sin instalarse en producción.

## Implementación
- Módulo independiente de account/mail; compatible con Odoo SaaS 18.0 y nativo
  18.2alpha1 mediante versión sin prefijo y declaraciones de restricciones
  adecuadas a cada ORM.
- Instala los campos de captura, imagen original y sección de pendientes en
  la factura de proveedor. Conserva el NCF en la referencia y en la evidencia.
- Si existe el módulo 606, rellena sus campos reutilizables y mantiene
  uno606_reviewed=False. En OUTSOLUTECH no instala el 606 ni habilita su menú.
- Solo contabilidad con permisos existentes para crear facturas. La vía del
  chat mantiene su lista previa de interlocutores autorizados; no amplía
  acceso de empleados ni otros usuarios.
- Nuevo adaptador expense_bridge.py, herramientas en agente_jenifer.py,
  despacho en comercio_jenifer.py y lista de rutas en worker.py.
  deployment/connect_native_expense_chat.py genera los candidatos con
  anclas verificadas, sin modificar directamente archivos activos.
- No cambia SMTP, DGII, cobros, pagos, sueldos ni configuración fiscal.

## Pruebas completadas
En copia reciente de OUTSOLUTECH, PostgreSQL privado puerto 18192:
- OCR real de foto ficticia, sin registrar como válida ante DGII.
- Borrador con proveedor existente, NCF B01/E31, fecha, moneda, partidas,
  ITBIS configurado y foto adjunta; no confirma ni paga.
- Misma imagen y otra imagen del mismo NCF devuelven el único borrador.
- Despacho del worker y las herramientas comerciales originales.
- Llamada real a la IA existente, solo con datos ficticios: eligió
  leer_factura_gasto y preparar_gasto_desde_foto; informó borrador existente,
  enlace, saldo y revisión pendiente sin duplicar.
- Dos solicitudes simultáneas con fotos distintas del mismo comprobante:
  un borrador y un UserError de registro simultáneo, total un registro.
  Se añadieron restricciones únicas SQL por empresa/huella y
  empresa/proveedor/NCF para no depender solo del bloqueo de aplicación.
- Las facturas y proveedores ficticios se revirtieron o eliminaron solo
  de la copia QA; no se emitió ningún comprobante ni se enviaron correos.
- Tres pruebas unitarias del adaptador aprobadas.

## Publicación y verificación
Módulo uno360x_expense_capture instalado en Outsolutech_prueba del servidor
nativo. Solo se instaló/actualizó este módulo. El chat existente carga las
dos herramientas nuevas. Odoo se reinició para cargar el código.
Verificado: servicio activo, login ERP HTTP 200, permiso contable del
administrador y ambas restricciones SQL presentes. 606 no instalado.
No se crearon facturas ficticias persistentes en producción.

Copias previas y logs: /var/lib/uno360x-expense-stage-20261119:
outsolutech-before-expense.dump, runtime-before/, runtime-change-proof.json,
native-qa-validation.log, native-qa-live-model.log, native-concurrency.log,
native-install-live.log y native-upgrade-live.log.
La copia DB es de 24 MB y tiene acceso restringido.

## Cómo usar
En el chat privado de Jenifer, adjuntar una foto clara JPEG/PNG de hasta
2 MB y pedir «Registra este gasto y déjalo en borrador».
Debe existir un proveedor único con ese RNC y un diario de compra para
la empresa. Si no existe o hay datos ilegibles, Jenifer pide completarlos.
Fase inicial B01/E31; otros comprobantes, retenciones, propinas o impuestos
compuestos requieren revisión contable. No supone que una factura está pagada.
La foto queda adjunta al borrador y contabilidad confirma por su flujo habitual.

## Reversión
Restituir únicamente los tres archivos del agente desde runtime-before y
reiniciar Odoo desactiva las herramientas nuevas. Conservar instalado el
módulo y sus borradores/evidencias evita pérdida de datos.
No restaurar toda la base sobre trabajo posterior ni desinstalar el módulo
como reversión rutinaria.

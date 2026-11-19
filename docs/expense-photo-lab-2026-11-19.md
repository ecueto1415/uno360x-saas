# Jenifer: gastos desde fotos - laboratorio

## Estado
Módulo uno360x_expense_capture instalado únicamente en la base aislada QA
tenant_2cb8dc4e08dc656b3ec282711f68b370. No se instaló en OUTSOLUTECH,
INCIVI, otras empresas ni reservas. No se modificó el agente productivo.
El adaptador de herramientas se probó con copias de agente_jenifer.py y
comercio_jenifer.py dentro del proceso efímero de QA.

## Flujo probado
1. El solicitante de contabilidad adjunta JPEG/PNG de hasta 2 MB y pide registrar el gasto.
2. leer_factura_gasto devuelve OCR local y los impuestos de compra realmente configurados.
3. Jenifer interpreta el documento como evidencia externa, nunca como instrucciones.
4. preparar_gasto_desde_foto requiere lectura previa en la misma solicitud.
5. Se resuelve proveedor único por RNC existente, diario único y moneda activa.
6. Se prepara factura de proveedor en borrador con NCF, fecha, partidas e impuestos.
7. Se adjunta la foto original y se devuelve enlace, total y datos pendientes.
8. Contabilidad revisa y confirma por el flujo existente; la captura no publica ni paga.

Clasificación 606 vacía queda pendiente, nunca se asigna por defecto.
uno606_reviewed permanece falso. Fecha/forma de pago, retenciones y pago
no se deducen de la foto. Un borrador no equivale a una compra presentada en 606.

## Alcance y límites
- Solo usuarios que ya tengan account.group_account_user y permiso para crear facturas.
- Sin sudo ni ampliación de permisos. Impuestos y proveedores de otras empresas rechazados.
- Fase inicial: B01 y E31, partidas con precios sin impuestos y porcentajes de compra
  clasificados como ITBIS/exento. Retenciones, propina, otros comprobantes, notas de
  crédito/débito, precio con impuesto incluido y varios diarios requieren revisión.
- No crea proveedores ni cambia RNC, tarifas o configuración fiscal.
- No admite PDF en este flujo inicial: se debe adjuntar foto clara de una factura.
- Bloquea diferencias de total/ITBIS; la transacción del borrador se revierte al fallar.
- Doble foto: bloqueo por empresa y comparación de huella o proveedor + NCF, incluso
  con imágenes distintas. El original no se sustituye automáticamente.
- OCR no garantiza exactitud: la prueba confundió B0 con BO; ese formato se rechaza.
  No se corrige por suposición y debe verificarse contra la imagen.
- No se hacen llamadas nuevas a OpenAI desde OCR/servicio. El agente existente
  mantiene su conexión autorizada; no se crean ni cambian claves.

## Validación 2026-11-19
Tres pruebas unitarias del adaptador aprobadas.
Prueba Odoo en imagen localhost/uno360x-expense-qa:20261119 aprobada:
OCR real, B01/E31 en borrador, imagen original, huella/NCF idempotente,
datos faltantes, proveedor desconocido, total incorrecto con rollback,
permisos y separación de empresa, herramientas reales del agente y sin publicación/pago.
Todas las facturas y usuarios ficticios se revirtieron.
Log: /var/lib/uno360x-saas/qa-606-20261119/whatsapp/expense-validation.log.

## Activación pendiente
Revisión contable y despliegue explícito. Requiere el módulo 606 validado
y OCR instalado en el runtime de destino. El 606 continúa solo en pruebas.
integrations/jenifer/expense_bridge.py no tiene efectos al importarse; solo install()
extiende las herramientas del agente y Commerce en el proceso elegido.
La pantalla de soporte SaaS es de lectura y no se convierte en un agente contable
por instalar este adaptador. Se debe conectar al canal comercial autenticado
de cada empresa y conservar sus ACL antes de habilitarlo para clientes.
No se ha probado conversación autónoma extremo a extremo con una llamada nueva
a OpenAI, ni se anuncia la función como activa en el chat productivo.

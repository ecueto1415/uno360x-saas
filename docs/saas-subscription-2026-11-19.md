# Suscripción del servicio UNO360X

Publicado el 19 de noviembre de 2026, conforme a la propuesta visual aprobada. Acceso: engranaje junto al nombre del usuario → Suscripción. El lateral, el logo y la cabecera siguen siendo los del espacio autenticado. La ruta es `/uno360x-suscripcion`, con pestañas Resumen, Método de pago e Historial.

## Alcance y permisos

El gateway valida la sesión y la membresía vigente en cada petición. Solo `owner` y `admin` de esa empresa pueden ver la página, descargar sus facturas o guardar sus preferencias. Un empleado recibe 403 aunque conozca la URL; los identificadores de otra empresa tampoco permiten consultar o reportar pagos. Los formularios exigen origen del espacio y un CSRF específico de suscripción. No se habilitan rutas administrativas de Odoo.

La implementación está en el código común del gateway, no en una adaptación de INCIVI ni en un módulo condicionado por plan. Aplica a las empresas existentes y a las nuevas cuentas, incluidas las que se asignen desde reservas, sin reconstruir las plantillas. OUTSOLUTECH y su Odoo nativo no participan en este gateway.

## Datos y pagos

Cinco tablas `subscription_*` en el plano de control guardan preferencias, condiciones comerciales, documentos de suscripción, comprobantes de transferencia y auditoría. No se usan eventos sandbox como pagos reales. Las condiciones actuales del espacio y el vencimiento de la prueba permanecen intactos.

- Resumen: Base Empresarial y los módulos contratados, condición vigente, importe y próxima fecha si el operador ya los configuró.
- Método de pago: preferencia de transferencia y correo de facturación editable. Razón social y RNC siguen gestionándose en Mi empresa.
- Historial: documentos reales importados por el operador, filtros por año/estado/número y descarga con el número del documento como nombre del PDF. En móvil la tabla se presenta como tarjetas.
- Comprobantes: PDF, JPG o PNG, hasta 3 MB; solo para una factura propia pendiente. Referencia y adjunto se conservan con actor y fecha. Reintentos y selección repetida del mismo archivo no duplican el registro. No hay confirmación automática del pago ni cambio de acceso.

Las tarjetas están explícitamente pendientes de conectar un proveedor. No existen campos para PAN, CVV ni credenciales de pago. Tampoco se inventa una tarifa, renovación o factura para INCIVI. Sin condiciones comerciales registradas, se muestra Por configurar. Sin documentos, el historial muestra su estado vacío.

## Operación del historial

`python3 -m deployment.subscription_ledger` importa localmente un PDF de una factura de suscripción ya emitida. Exige operador root en la VM, empresa, número, importe en unidades mínimas, moneda, fecha, vencimiento opcional y archivo PDF de hasta 5 MB. No emite un e-CF, procesa un cargo ni marca la factura como pagada. Reimportar el mismo documento es idempotente; una coincidencia de número con otros datos se rechaza.

Ejemplo exclusivamente ilustrativo de los argumentos, no ejecutado en una empresa real:

```text
python3 -m deployment.subscription_ledger --tenant ID --number NUMERO_EXISTENTE --amount-minor 4500 --currency USD --issued EPOCH --pdf /ruta/factura_ya_emitida.pdf
```

La conexión comercial del proveedor de tarjetas, generación periódica de cobros, conciliación y gestión de tarifas desde el panel del operador son trabajo posterior; la página no las presenta como activas. La consulta de suscripción tampoco convierte automáticamente la cuenta de INCIVI en una nueva contratación.

## Validación y publicación

Pasaron once pruebas del módulo, cuatro del capturador autorizado de soporte y un recorrido HTTP con identidad real de prueba. Se comprobaron autorización vigente, rechazo directo para empleados, CSRF/origen, aislamiento de facturas y adjuntos, importación y reintentos idempotentes, rechazo de archivos no admitidos y facturas ya pagadas, filtros, HTML escapado y descarga con nombre correcto. El empleado siguió pudiendo usar el resto del espacio.

En el navegador real de INCIVI se abrió desde el engranaje, se guardó transferencia con su correo de cuenta y se verificó la persistencia al volver al Resumen. Se revisaron método de pago, historial vacío, filtros enviados al servidor con respuesta 200 y disposición móvil de 390 px sin desbordamiento horizontal. No se crearon facturas, cargos ni comprobantes ficticios en INCIVI. Capturas guardadas en `outputs/UNO360X_INCIVI_suscripcion.jpg` y `outputs/UNO360X_INCIVI_suscripcion_movil.jpg` del espacio de trabajo.

Respaldo de código y SQLite previo a la publicación: `/var/backups/uno360x-subscription-20261119`, accesible por root. Solo se reinició `uno360x-saas-pilot.service`. El PID del Odoo nativo de OUTSOLUTECH permaneció igual; las fechas de todas las pruebas permanecieron idénticas. La publicación añadió tablas, sin borrar datos anteriores.

Para revertir el código, restaurar `control/gateway.py`, `control/team_access.py` y `control/support_context.py` del respaldo y reiniciar únicamente el gateway SaaS. Conservar las tablas y documentos actuales; restaurar una copia antigua de toda la base perdería mensajes, preferencias u otros cambios posteriores. La consulta de Jenifer incorpora la ruta y el alcance real de la nueva opción según el rol del solicitante.

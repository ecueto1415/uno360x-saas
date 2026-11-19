# Jenifer: gastos desde fotos en todo el SaaS

Publicado 19/11/2026. Fuente activa:
/srv/uno360x-saas/releases/expense-chat-20261119-v2/source.
La instalación nativa de OUTSOLUTECH no se cambió en esta publicación.

## Uso
Entrar a la empresa y abrir Soporte → Registrar gasto con foto.
También hay un acceso desde la página de Jenifer para los usuarios con
contabilidad. Ruta relativa: /uno360x/jenifer/gastos.
Adjuntar una factura JPEG/PNG de hasta 2 MB, añadir cualquier aclaración
y pulsar Preparar borrador. Se devuelve el vínculo de la factura de proveedor.
El historial muestra los últimos 30 gastos preparados por ese usuario.
El proveedor debe existir y tener un RNC único. Si falta, no se inventa ni
se crea automáticamente. Esta fase admite B01/E31, impuestos simples y
precios sin impuesto; retenciones/propina y otros documentos necesitan revisión.
Contabilidad revisa imagen, comprobante, clasificación e impuestos antes de confirmar.

## Separación y permisos
- Cuenta y empresa proceden del handle autenticado del gateway, no del cuerpo.
- RPC con la sesión exacta del solicitante; sin sudo ni cuenta operadora.
- Solo contabilidad o su administrador con permiso real de crear facturas.
- Revalidación de sesión/membresía antes y después de las RPC y tras la IA.
- CSRF propio del flujo; origen validado por el gateway existente.
- Foto validada como JPEG/PNG, máximo 2 MB/12 MP y OCR limitado por tiempo.
- Texto OCR no confiable: extracción con esquema estricto y sin herramientas
  para pagar, emitir comprobantes, modificar permisos o enviar mensajes.
- La foto original se guarda en el tenant al crear el borrador. Las fotos
  y resultados contables no se almacenan en los casos centrales de soporte.
- NCF, total e ITBIS se verifican en el servicio común. No marca como pagado,
  no confirma, no emite a DGII ni presenta el 606.
- Huella y proveedor/NCF tienen restricciones únicas por empresa. No depende
  únicamente de un bloqueo de aplicación bajo transacciones simultáneas.

## Procesamiento
El proceso de soporte reutiliza la conexión autorizada de Jenifer, sin crear
ni cambiar claves. La extensión de OCR/IA recibe solicitudes mediante un
socket Unix privado, una lectura activa a la vez y sin persistir fotos.
Código del proceso root-owned, privilegios reducidos al usuario SaaS antes
de atender solicitudes. El gateway conserva la autoridad de escritura:
el procesador solo devuelve datos extraídos. Se usa store=False.
El intérprete existente proporciona PIL; no se modificó su instalación.
Límite del servicio de soporte: 320 MB y 35% CPU; no cambia las cuotas de tenants.

## Publicación
Los dos únicos addons añadidos a los perfiles son uno360x_expense_capture
y uno360x_expense_chat. Todos los addons que ya estaban en cada perfil
mantuvieron exactamente su versión y hash de fuente. Se conservaron
respaldos de base, archivos y metadatos por tenant antes de instalar.
Incivi y CuetoExpress: ambos módulos instalados y dos restricciones SQL presentes.
Las ocho combinaciones de módulos tienen plantillas actualizadas desde
plantillas prístinas verificadas. Reserva lista: 1, con ambos módulos y
0 account.move, respetando la política de desarrollo vigente.
OUTSOLUTECH mantuvo PID 1418368 y el mismo hash de configuración.
Sus servicios no se reiniciaron en esta tarea.

## Verificación
- 6 pruebas del gateway de gastos: actor/empresa, revocación durante IA,
  datos ilegibles sin escritura, lista fija de métodos y CSRF.
- 15 pruebas de transporte/soporte: sesión, origen, aislamiento, caducidad,
  mensajes idempotentes y cookies privadas.
- 11 pruebas del chat en navegador simulado, incluido acceso condicional al flujo.
- 3 pruebas de catálogo y 3 de publicación selectiva.
- OCR e IA reales sobre una factura ficticia; datos resultantes enviados
  a capture_draft del laboratorio con permisos de administrador contable.
- Dos solicitudes simultáneas en SaaS QA: un borrador y una solicitud rechazada,
  un solo registro. Se limpiaron únicamente los registros ficticios de QA.
- Repetición de foto, historial por usuario y bloqueo de selección de otra compañía.
- Pantalla real de INCIVI abierta con sesión existente: Preparar borrador habilitado.
  Verificada en computadora y a 390px; scrollWidth 375, sin desbordamiento horizontal.
  No se crearon facturas ficticias en empresas de clientes.
- Hash y cantidad de documentos contables de ambos tenants idénticos antes/después.

Logs privados: /var/lib/uno360x-saas/expense-chat-validation/ y
/var/lib/uno360x-saas/qa-606-20261119/whatsapp/.
Registro de publicación: /var/lib/uno360x-saas/published-release.json.

## Reconciliación de fuente y preparación
Se detectaron archivos activos ausentes de esta copia Git, entre ellos
componentes de inventario, nómina, cotizaciones, tasa BCRD y publicación rápida.
Se respaldó la fuente que YA estaba ejecutándose antes de añadir el flujo.
No representan cambios nuevos a esos módulos: los perfiles base/completo
del repositorio local coinciden con los publicados.
La primera preparación desde cero detectó pruebas antiguas de workspace
que intentaban renderizar sin request HTTP. Se utilizó la vía incremental
de las plantillas prístinas ya verificadas, instalando solo los dos módulos
nuevos. No se desactivaron validaciones de datos ni se usaron bases de clientes.
Dos marcadores de publicación anteriores, distintos al estado activo, fueron
archivados únicamente después de verificar runtime, módulos y marcador vigente.
Se conservan como workspace-obsolete-before-expense-20261119.json por tenant.

## Reversión
Los respaldos por tenant y el registro de flota conservan la versión anterior.
Para deshabilitar la entrada se puede retirar el enlace y el despacho de
/__expenses, conservando los borradores y evidencias en sus empresas.
No desinstalar el módulo ni restaurar toda una base sobre trabajo nuevo como
reversión rutinaria. El soporte conserva su enlace y unidad anteriores en
el directorio privado de validación.

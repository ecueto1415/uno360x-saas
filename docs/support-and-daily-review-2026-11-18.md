# Soporte UNO360X y revisión diaria

Publicado el 18 de noviembre de 2026. Todas las horas de producto se interpretan en America/Santo_Domingo.

## Acceso

- Clientes: botón **Soporte** en la esquina inferior derecha o **Ayuda y soporte** del menú. Disponible en las páginas comunes y en el cliente nativo del SaaS.
- Propietario: https://admin.uno360x.com/#soporte, **Soporte y mejoras**. Permite leer, responder en el chat y marcar conversaciones resueltas. Conserva la autenticación y el segundo factor del panel.
- Las conversaciones son privadas por empresa y cuenta. Otro empleado de la misma empresa no recibe el historial de un compañero.
- Al elegir **Hablar con el equipo**, cesan las respuestas automáticas del hilo. Los mensajes del equipo quedan registrados. No envía correos ni crea documentos comerciales.

## Arquitectura y seguridad

`control/support.py` se ejecuta en el gateway después de validar la sesión central y la membresía. El cliente nunca selecciona el tenant o el usuario de la API. El POST exige origen válido, JSON limitado y token CSRF específico del soporte. Las peticiones se deduplican por un identificador de mensaje, incluso al crear una conversación nueva. La cola se reclama con transacción SQLite inmediata; una ejecución incierta se deriva al equipo, sin repetir ciegamente la llamada al proveedor.

Datos en `/var/lib/uno360x-support/support.sqlite3`, directorio 2770 y archivo 0660, propietario `uno360x-saas`, grupo `uno360x-admin`. El directorio privado general del SaaS conserva 0700. El soporte no usa ni modifica las bases de negocio, las secuencias o los certificados. Las sugerencias se agrupan por tema; no se afirma que exista deduplicación semántica perfecta entre textos diferentes.

El servicio `uno360x-support.service` inicia desde código root en `/opt/uno360x-support/current`. Lee en memoria la conexión OpenAI ya utilizada por Jenifer desde el proceso Odoo existente, sin copiar la clave a un archivo ni modificar el servicio original. Inmediatamente reduce su identidad a `uno360x-saas`, sin grupos adicionales. Solo tiene un redactor de soporte con Responses API y `store:false`; no dispone de herramientas, acceso a registros comerciales ni capacidad de desplegar cambios. Usa el modelo de la conexión existente. Si esa conexión no está disponible o la llamada falla, conserva el mensaje y lo deriva al equipo.

El proceso permanece ligero y consulta la cola cada cinco segundos. **Sin mensajes pendientes no llama a OpenAI.** El chat cerrado tampoco hace peticiones. La respuesta se consulta cada cuatro segundos mientras está pendiente y cada treinta cuando el chat está visible; se suspende al cerrar u ocultar la pestaña. Una consulta de soporte no concede permisos de negocio ni autoriza descuentos.

## Rendimiento e informe

El gateway agrega tiempos de entrega de páginas autenticadas por empresa, hora y área. Guarda cantidad, suma, máximo, cargas de al menos 2.5 s y respuestas 5xx. No registra URL, query string, identificador del documento, formularios, teclas o contenido comercial. No pretende medir toda la latencia del navegador ni las consultas RPC nativas. La escritura de telemetría espera como máximo 25 ms y se omite ante un fallo, sin impedir la operación principal.

El informe se prepara una vez al día a partir de las 10:58 para la revisión de las 11:00. Agrega aproximadamente las últimas 24 horas, identifica los límites de cobertura, agrupa temas y propone acciones con evidencia. No hace llamadas adicionales a IA para generar las estadísticas. Las mediciones horarias se conservan 30 días, los informes 90; las conversaciones quedan para seguimiento. No hay borrado automático del historial de clientes.

La automatización de Codex `revisi-n-diaria-de-soporte-y-mejoras-uno360x` publica la revisión diaria en el chat existente. Su instrucción apunta a la base real con lectura SQLite `mode=ro` y `query_only=ON`. Si la aplicación o la conexión necesaria para ejecutar la automatización no están disponibles, debe informar la falta de evidencia en vez de inventarla. El informe también queda accesible en el panel aunque no se haya ejecutado la revisión de Codex. Ninguno de los dos componentes aprueba ni despliega cambios automáticamente.

## Publicación común

La incorporación ocurre en el gateway compartido y en el panel de administración. Por ello alcanza a las empresas actuales, las reservas y las futuras cuentas al acceder por el gateway, independientemente de su plan. No cambia los addons ni sus huellas, no reconstruye las ocho plantillas y no pone a los clientes en modo actualización. Se reinicia únicamente el gateway y el panel; la sesión central permite volver a abrir el espacio. OUTSOLUTECH, su proceso Odoo y su facturación quedan fuera.

## Validación

- 11 pruebas de almacenamiento: aislamiento tenant/cuenta, reintentos, concurrencia de cinco envíos, reclamación única entre dos workers, derivación humana, estado incierto, límites locales y reportes.
- 1 prueba HTTP específica del gateway: sesión, origen, CSRF, ruta, contenido e idempotencia.
- 1 prueba HTTP específica del panel: sesión, CSRF, respuesta y deduplicación.
- 27 pruebas existentes del gateway y autenticación del panel aprobadas.
- 4 pruebas DOM: chat inactivo, apertura/cierre, doble envío, XSS como texto, inglés e inicialización única.
- Llamada real acotada con pregunta ficticia de inventario y la conexión de Jenifer: respuesta recibida y guardada una sola vez. No emitió documentos ni envió emails.
- Revisión visual en Chrome del panel y del chat de INCIVI. El usuario pudo abrir una conversación real y el servicio registró una respuesta del asistente.
- Vista móvil aislada con los mismos archivos publicados: 390 × 700 y 320 × 480. Se detectó y corrigió el recorte de los botones en poca altura; el botón Enviar queda dentro del panel y no hay desplazamiento horizontal. Esta prueba usa datos ficticios y respuestas simuladas; la conexión real se verificó por separado.
- Servicio persistente verificado con UID/GID de `uno360x-saas`, sin capacidades efectivas y aproximadamente 11 MB de memoria. El proceso Odoo de OUTSOLUTECH conserva su instante de arranque anterior.

## Operación y reversión

Tras rotar la conexión existente de Jenifer, reiniciar únicamente `uno360x-support.service` para que vuelva a cargarla. Nunca imprimir entorno, credenciales ni cuerpos del proveedor en los logs. Los logs del soporte solo deben indicar cantidades o clases de error.

Respaldo previo: `/var/backups/uno360x-support-20261118/`, con la versión anterior del gateway y el enlace de la versión anterior del panel. Para revertir, detener el nuevo servicio, restaurar `control/gateway.py`, volver al enlace administrativo guardado y reiniciar solo gateway/panel. Conservar el archivo SQLite del soporte; no borrar conversaciones para revertir código. No reiniciar ni modificar Odoo de OUTSOLUTECH.

# Firma y sello por empresa

Mi empresa permite al administrador cargar, sustituir o retirar una imagen PNG/JPG de hasta 2 MB y 4096 px. La imagen se guarda como un adjunto de res.company, no como un recurso compartido entre clientes. La comprobación de permisos cubre tanto el controlador con CSRF como las escrituras ORM sin sudo. Se reutiliza la validación de imágenes del logo.

Las cotizaciones y los cuatro estilos de factura toman la imagen de la empresa del documento. En el estilo moderno, una tabla indivisible sitúa el QR a la izquierda y la imagen a la derecha; se conservan el código de seguridad, fecha de firma y márgenes del diseño existente. La imagen visual no interviene en XML, certificado, secuencias, firma criptográfica ni transmisión a DGII. Sin imagen no aparece un recuadro vacío.

Validación en INCIVI: carga real desde navegador, vista previa, guardado y retirada de la imagen ficticia; formulario a 390 px sin desbordamiento horizontal; generación de cotización y factura borrador en una transacción revertida; PDF de una nota fiscal existente generado solamente para lectura con sello ficticio, QR y sello en columnas opuestas. No se emitieron documentos. Escritura de sello por vendedor rechazada. Datos de prueba revertidos y sello ficticio retirado después de la prueba web. PDFs inspeccionados mediante Poppler.

Publicación común para los dos clientes actuales, ocho combinaciones de módulos y una reserva de desarrollo. Respaldo de fuente y estados: /var/backups/uno360x-signature-20261119. Registros privados de actualización y validación: /var/lib/uno360x-saas/signature-release-20261119. OUTSOLUTECH no recibe esta publicación. Reversión: restaurar las cuatro fuentes del respaldo, actualizar el módulo común y regenerar cachés/reservas; no restaurar bases completas.

También se completó el recorrido CRM pendiente: oportunidad ficticia creada, etapa nueva creada, oportunidad movida y responsable cambiado de gladis a Administrator; la tarjeta reflejó ambos cambios. Se retiraron únicamente oportunidad, etapa y preferencia creadas por la prueba, conservando la oportunidad previa. Sin cambios de certificados ni secuencias.

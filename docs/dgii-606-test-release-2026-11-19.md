# Formato 606 · Instalación exclusivamente en pruebas

## Alcance y fuentes verificadas

Motor único `addons/uno360x_dgii_606/engine.py`, adaptador ORM único y menú Contabilidad → DGII → Formato 606. No depende de `uno360x_workspace`, por lo que funciona en el SaaS y en la instalación nativa con los permisos contables existentes. No envía archivos a la DGII ni altera pagos, comprobantes, secuencias o certificados.

Fuentes oficiales consultadas el 19/11/2026:

- [Instructivo de llenado y remisión del 606](https://dgii.gov.do/publicacionesOficiales/bibliotecaVirtual/contribuyentes/formatoEnvioDatos/Documents/4-LlenadoyEnvioFormato606.pdf), edición febrero 2026, catálogo DGII modificado 12/02/2026. Secciones de llenado, notas, retenciones, validaciones y repetición por pago posterior.
- [Plantilla oficial de envío](https://dgii.gov.do/herramientas/formularios/formatoEnvioDatos/Paginas/default.aspx), paquete NG07-2018/05-2019, catálogo modificado 28/10/2025. Se descargó el XLS y se inspeccionó su generación de texto sin ejecutar sus macros: encabezado de cuatro campos y detalle de 23 campos separados por barra vertical, fechas AAAAMMDD, cifras sin separadores de miles y separador decimal punto, nombre DGII_F_606_RNC_AAAAMM.TXT. CRLF entre líneas y sin línea adicional al final, como la macro publicada.
- [Tratamiento de compras a crédito](https://ayuda.dgii.gov.do/conversations/formatos-de-envo-de-datos/ca3506-cmo-debo-reportar-las-facturas-a-crdito-en-los-formatos-606-y-607/5f3c17698cd858ce879c4214): factura en su período de emisión; repetición en un período posterior únicamente por retenciones pagadas, preservando la fecha original.
- [Prevalidador oficial](https://dgii.gov.do/herramientas/formularios/pre-validacion/Paginas/default.aspx), catálogo modificado 31/07/2026. La herramienta publicada es un instalador Windows; no está instalada en el laboratorio Linux. La validación con esa herramienta queda pendiente y no se sustituye por nuestras pruebas.

## Auditoría y reutilización

Se inspeccionó la instalación real, sin modificarla: 49 documentos de proveedor y localización `l10n_do` instalada. Las facturas de proveedor consultadas no tenían NCF en Referencia; su número FACTU/... es interno y no se usa como NCF. No existían campos activos de tipo de gasto/retención 606. Se encontró una carpeta antigua `ncf_dgii_reports`, no instalada, incompatible con el runtime y con licencia OPL: no se copió su implementación.

Se reutilizan proveedor/RNC, fecha de factura, tipo de documento, factura revertida, balances contables en DOP y conciliaciones. Si existen campos `l10n_latam_document_number`, `ncf` o `expense_type` se consultan primero; si varios campos contienen NCF válidos distintos, se exige corregir la discrepancia. Se reutilizan las clasificaciones `outs_ecf_category` y `uno360x_ecf_retention` cuando están presentes. El resto de impuestos requiere clasificación explícita, sin inferirlo por su nombre ni por un porcentaje aislado.

Los campos nuevos están en la pestaña Datos fiscales 606 de la factura de proveedor: NCF, comprobante modificado, tipo de gasto, revisión contable y tratamiento del ITBIS. Bienes/servicios se obtiene del producto, o de la clasificación explícita de la línea cuando no tiene producto. Los importes proceden del balance en moneda contable DOP, de modo que una compra en USD usa el importe contabilizado, no la tasa actual. Si la moneda base no es DOP se bloquea, sin conversión implícita.

Los pagos/retenciones se registran como detalle fiscal, no como un segundo pago contable. El pago conciliado puede vincularse y se comprueban empresa, fecha y factura. La clasificación configurada en el diario se reutiliza al seleccionarlo. Para datos históricos se requiere referencia/evidencia y revisión expresa de contabilidad. Retenciones de distintos períodos se conservan en eventos separados. Más de un tipo ISR en el mismo NCF/período exige revisión, en lugar de escoger uno arbitrariamente.

## Comportamiento

- Empresa, mes y año; vista previa con comprobantes, totales y errores enlazados a factura/campo.
- NCF B/E de compras, notas de crédito/débito con comprobante original. Notas con montos positivos en TXT y signo negativo solo en el resumen neto. Si el original no aparece en el reporte actual, contabilidad debe confirmar expresamente que fue reportado previamente.
- Retenciones solo en su período de pago. Una repetición por retenciones conserva importes/fecha del comprobante en TXT y no vuelve a sumar compra e ITBIS al resumen de operaciones del mes.
- Fecha de pago obligatoria para retenciones; tipo ISR y fecha validables; comprobantes duplicados del mismo proveedor/empresa bloqueados aunque estén en otra fecha.
- Sin operaciones: muestra el trámite informativo en cero, no inventa un TXT con movimientos.
- Revisiones pendientes, datos fiscales ausentes, impuestos sin clasificar o inconsistencias bloquean descarga. Al descargar se reconstruye desde registros autorizados, sin confiar en una vista previa modificada.
- ACL de contabilidad y reglas por empresa en reporte y eventos. Ventas no puede crearlo ni exportarlo. Los binarios son transitorios y conservan las restricciones de lectura de Odoo.

## Pruebas y estado

10 pruebas unitarias del motor aprobadas. Validación ORM aprobada en ambos runtimes: SaaS Odoo 18.0-20261015 y copia aislada del servidor nativo, cuyo runtime se identifica como 18.2alpha1. Se usa versión de módulo 1.0.0 para que cada runtime aplique su prefijo, sin modificar Odoo.

Para repetir las pruebas unitarias: instalar `tests/requirements-606.txt` y ejecutar `python tests/test_606_engine.py`. Para la validación ORM nativa, ejecutar el archivo `deployment/validate_606_lab.py` en Odoo shell con `/var/lib/uno360x-606-lab/odoo.conf`; el propio script rechaza cualquier conexión distinta del PostgreSQL aislado en 18192. No ejecutarlo con `/etc/odoo18.conf`.

`deployment/validate_606_lab.py` comprueba facturas B/E, E34, retenciones de octubre pagadas en noviembre, pago contable conciliado, duplicados, datos faltantes, rechazo de Ventas y acceso entre empresas. Todos los documentos ficticios se revierten. En SaaS limpio se comprueba también una descarga válida. En la copia nativa se detectaron 22 incidencias de los datos anteriores y se comprobó que no se exportaran silenciosamente. No son errores generados mediante cambios en producción.

La copia nativa conserva el nombre Outsolutech_prueba, pero está en un PostgreSQL separado con socket privado y puerto 18192, bajo /var/lib/uno360x-606-lab. El test exige comprobar ese puerto antes de operar. Cron, correo y proveedores de pago están desactivados en la copia. La base operativa del mismo nombre, puerto 5432, no recibe la instalación. El dump de origen se conserva privado en /var/backups/uno360x-606-outsolutech-20261119.dump.

El SaaS de prueba está bajo /var/lib/uno360x-saas/qa-606-20261119, con recursos propios. El módulo fuente está disponible en el master para instalación explícita, pero no se añadió al catálogo de planes ni se instaló en INCIVI, CuetoExpress o las reservas comerciales. Esto respeta la instrucción de mantenerlo en pruebas.

Pendientes expresos: cotejo con el 606 de contabilidad (noviembre sigue en curso; no se recibió archivo de comparación), prevalidación oficial Windows y confirmación contable. No se presenta el módulo como fiscalmente aprobado.

## Habilitación tras confirmación

1. Revisar con contabilidad la tabla de impuestos y formas de pago de diarios; completar la pestaña 606 en documentos anteriores. No modificar números internos ni recrear las facturas.
2. Generar el mes de comparación, contrastar todas las filas/totales con contabilidad y ejecutar el prevalidador oficial sobre el TXT.
3. Solo tras confirmación, instalar `uno360x_dgii_606` en la empresa nativa y añadirlo a la instalación común del SaaS; actualizar exclusivamente las bases afectadas y preparar reservas nuevas con esa versión. La lógica seguirá siendo la misma.
4. Autorizar usuarios mediante el grupo contable existente. En la interfaz UNO360X conservar el menú actual, bajo Contabilidad/DGII. Usuarios de ventas no reciben el acceso por tener permiso para facturar.
5. Descargar manualmente el TXT y cargarlo en Oficina Virtual. Este módulo no presenta ni rectifica declaraciones por sí mismo.

Reversión en pruebas: desactivar el menú/desinstalar en los laboratorios o restaurar exclusivamente el laboratorio. No restaurar ni manipular la base operativa para retirar una prueba.

# Emision E31/E45 desde Odoo de OUTSOLUTECH

Modulo independiente `native_addons/outsolutech_ecf_production`, version
18.2.1.0.1, exclusivo de la instancia nativa `Outsolutech_prueba` y del RNC
132364805. No se instala en el SaaS ni comparte la identidad de OUTSOLUTECH
con otros clientes. Depende del modulo nativo de precertificacion ya instalado
y conserva los documentos anteriores, las acciones de pruebas y sus secuencias.

## Uso

En una factura de cliente confirmada: **Factura fiscal electronica**.
Seleccionar E31 o E45, revisar tipo de ingreso, contado/credito, cliente/RNC y
total. **Comprobar datos** no reserva secuencias. **Asignar e-NCF y firmar**
reserva dentro de la autorizacion y protege los datos. **Emitir factura fiscal**
requiere confirmacion del usuario y encola el envio real a DGII. El worker
existente procesa la cola cada minuto. Consultar la respuesta hasta aceptacion.
El XML firmado puede descargarse. El PDF fiscal se habilita tras aceptacion o
aceptacion condicional y el informe normal de la factura incorpora e-NCF,
vencimiento, codigo de seguridad, firma y QR de produccion. Conserva el layout
existente de la empresa.

Menus: Facturacion electronica (accion 1036); en configuracion,
Secuencias e-NCF autorizadas (accion 1037). Usuario ecueto@outsolutech.com
comprobado con permisos contables para consultar las seis autorizaciones.

## Autorizaciones

Se importaron las seis constancias OFV aportadas por el usuario como adjuntos
privados vinculados a la empresa. E31 y E45 habilitados en el adaptador;
E33/E34/E43/E44 registrados con bloqueo de reserva/emision hasta implementar
sus flujos. E34 conserva ausencia de vencimiento, tal como N/A en su constancia.
No se configura E32 por no haberse aportado su autorizacion. Las fotos y los
numeros de autorizacion se conservan en el entorno del cliente, fuera de Git.

Cada rango tiene inicio, fin, siguiente, vencimiento, referencia y constancia.
Bloqueo transaccional/advisory impide solapamientos y doble asignacion. No se
crean secuencias productivas automaticamente a partir de valores de prueba.
Rangos utilizados no se editan ni eliminan; no se reutilizan numeros. La
reserva y firma son atomicas. Un documento de precertificacion no se convierte
a produccion sobre la misma factura.

## Transporte y seguridad

Autenticacion real productiva verificada con el certificado existente y su
cadena/revocacion; no se alteraron sus archivos o contrasena. Client exclusivo
del ambiente `ecf`, TLS 1.2 con validacion de CA y hostname, cookies de sesion
en memoria por cliente y Accept XML para semilla/JSON para las demas respuestas.
En esta VM, TLS 1.3 y negociacion de contenido incorrecta provocaron resets.
Se espacian peticiones; solo GET reintenta ante fallo de transporte. Nunca se
repite automaticamente un POST de factura. El TrackId perdido exige conciliacion.
La respuesta oficial HTTP 400 codigo 0 / TrackId no encontrado se distingue de
otros errores 400, sin autorizar reenvios. Se verifico ausencia de TrackIds para
los primeros E31/E45 de los rangos nuevos mediante consultas de solo lectura.

Tras firmar se comprueba integridad de datos, huella del XML, certificado y
firma, ambiente y rango antes de enviar. Aceptacion se vincula a RNC/e-NCF y
TrackId. Certificado diferente, revocado, vencido o sin CRL vigente bloquea
el proceso. Solo responsables de contabilidad y empresa seleccionada pueden
operarlo. Los defaults del contexto no pueden inyectar estado o XML protegido.

## Despliegue y validacion

Fuente inmutable root:
`/opt/uno360x-outsolutech-ecf/releases/20261104T154644Z`, enlazada como addon
nativo. No se carga codigo editable por el usuario SaaS en el proceso Odoo.
Instalacion ORM, sin reiniciar el proceso Odoo (PID 2195, NRestarts=0), con
configuracion de servicio y credenciales intactas. Copia previa completa de DB
y filestore en `/var/backups/uno360x-ecf-emission/20261104T154719Z`.

15 pruebas Odoo aprobadas en PostgreSQL separado de laboratorio: numeracion,
firma/integridad, rangos independientes E31/E45, bloqueo de otros tipos,
vencimiento, ausencia/solapamiento de rangos, autorizacion inmutable, contextos
protegidos, QR, informe normal con e-NCF, resultado DGII de otra identidad,
envio incierto sin duplicado y reintentos solo de lecturas.

En vivo: acceso del operador y formularios comprobados; factura anterior
renderizada correctamente sin modificarla; seis rangos visibles con siguiente
igual al inicio y contador cero. Conexion DGII productiva autenticada. No se
creo, firmo ni transmitio una factura real para probar y no se consumieron
e-NCF. La primera aceptacion real se comprobara al emitir la factura elegida
por el usuario; las pruebas de laboratorio no equivalen a esa aceptacion.

## Reversion

Deshabilitar el flag productivo de la empresa y vaciar la cola pendiente
mediante revision fiscal, sin eliminar documentos ni devolver secuencias.
Conservar addon/historial una vez existan comprobantes; no desinstalar ni
restaurar una DB antigua sobre nuevas facturas. En caso de fallo de codigo,
restaurar la version compatible del addon manteniendo DB, adjuntos y acuses.
La copia completa previa es recuperacion de emergencia con revision de
operaciones posteriores, no reversion automatica de datos financieros.

## Confirmacion y entrada visible (18.2.1.0.1)

El boton Factura fiscal electronica se muestra tambien en borrador, con una
indicacion de confirmar primero la factura; esa confirmacion contable no envia
un e-CF. El generador y bloque legacy Laboratorio e-CF se ocultan cuando la
empresa tiene emision productiva habilitada. Los borradores anteriores se
conservan. La vista productiva y la vista fallback muestran el mismo aviso:

Enviar este comprobante real a la DGII; revisar cliente, RNC, tipo y total.
Una vez aceptado no se edita ni elimina y una correccion puede requerir nota
de credito. Cancelar conserva el XML preparado sin enviarlo.

Titulo: Confirmar emision fiscal. Botones: Si, enviar a la DGII / Cancelar.
Se usa ConfirmationDialog estandar de Odoo: solo confirm ejecuta la accion;
cancel no la ejecuta. Esto fue verificado en el codigo frontend instalado y
ambas vistas compiladas con los permisos y lenguaje del operador. La nueva
vista heredada del laboratorio fue validada por Odoo en el upgrade. No se
crearon comprobantes ni se reservaron numeros por este cambio.

Fuente actual: /opt/uno360x-outsolutech-ecf/releases/20261104T160953Z.
Backup de vistas y fuente anterior en
/var/lib/uno360x-dgii-install/confirmation-20261104T160953Z.

Criterio de correcciones: [Preguntas frecuentes DGII](https://dgii.gov.do/publicacionesOficiales/bibliotecaVirtual/contribuyentes/Otros/Documents/Preguntas-frecuentes-Nuevos-Contribuyentes.pdf), pregunta 22.

### Corrección de contexto al facturar — 18.2.1.0.2

La acción de factura transportaba valores predeterminados de account.move al expediente fiscal. Ahora elimina esos valores al cruzar de modelo y la protección de creación distingue campos fiscales reales de valores ajenos. Se conservan los bloqueos de estado, XML firmado y demás datos protegidos.

Validación: 17 pruebas sin fallos en PostgreSQL aislado; respaldo previo 20261104T171846Z; versión publicada en /opt/uno360x-outsolutech-ecf/releases/20261104T172201Z, con reinicio controlado de odoo18 y HTTP 200. Comprobación transaccional revertida con usuario 2: factura confirmada 1078 abre expediente productivo vacío, sin reservar e-NCF ni enviar. La factura 1083 está en borrador y correctamente solicita confirmar antes de abrir expediente. No se confirmó ninguna factura como parte de estas verificaciones.

### Retirada de numeración B — 18.2.1.0.3

Por instrucción del propietario, se bloquea _post de facturas y notas de cliente en diarios Bxx cuando la empresa tiene producción e-CF habilitada. No afecta facturas de proveedores ni empresas sin esa habilitación. El e-NCF sigue reservado exclusivamente por el expediente fiscal.

OUTSOLUTECH: diario nuevo FAC (id36), nombre Facturas electrónicas UNO360X y prioridad1, con cuentas copiadas del diario9. Se movieron únicamente seis borradores sin número ni publicación previa (1088,1086,1085,1083,1082,1081), conservando importes. Diarios B02/B14/B15/B16 archivados y cinco secuencias ir.sequence B archivadas sin alterar contadores. B01 se conserva activo por la restricción estándar de Odoo ante dos borradores históricos previamente publicados (139,526); nombre Histórico B01 - emisión desactivada, prioridad99 y emisión bloqueada por código. No se forzó el archivado ni se renumeró el historial. Factura1087 conserva B0100000270.

Respaldo previo: 20261104T173113Z. Validación: 18 pruebas sin errores en base aislada, bloqueo en producción comprobado sobre borrador histórico sin publicación, selección predeterminada FAC, rangos electrónicos intactos y 261 asientos publicados preservados. Release /opt/uno360x-outsolutech-ecf/releases/20261104T173347Z; reinicio controlado y HTTP200. No se enviaron comprobantes a DGII.

### Primera emisión real aceptada y descripciones — 18.2.1.0.5

El propietario autorizó expresamente enviar FAC/2026/00001 (account.move1088). La descripción de línea de105 caracteres impedía preparar el XML: NombreItem admite80. El adaptador productivo conserva la etiqueta completa en DescripcionItem (máximo1000), usa la primera línea abreviada como NombreItem y valida nuevamente el XSD; no altera los importes ni la factura original. Textos mayores de1000 se bloquean antes de reservar número.

Se preparó y envió E310000000001 con un intento. DGII devolvió código1, estado Aceptado y secuenciaUtilizada=true el04/11/2026 a las13:44:16, hora dominicana. El expediente9 conserva TrackId, XML firmado y respuesta oficial. No se reenvió al corregir la impresión.

La revisión del PDF detectó QR vacío por falta del backend gráfico de reportlab en el servidor. Ahora se genera PNG con qrcode y se incrusta en el reporte; no depende de una petición HTTP al controlador de código de barras. PDF final revisado visualmente, e-NCF y detalle completos. Se conserva la plantilla corporativa previa.

Validación final:20 pruebas sin errores en PostgreSQL aislado (incluye descripción larga, límite previo a reserva, integridad firmada y PNG incrustado). Release productivo /opt/uno360x-outsolutech-ecf/releases/20261104T174734Z, respaldo posterior a aceptación20261104T174719Z, reinicio controlado y HTTP200. No se modificaron credenciales ni el certificado existente.

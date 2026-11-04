# Emision E31/E45 desde Odoo de OUTSOLUTECH

Modulo independiente `native_addons/outsolutech_ecf_production`, version
18.2.1.0.0, exclusivo de la instancia nativa `Outsolutech_prueba` y del RNC
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

# OUTSOLUTECH: receptor productivo y certificacion DGII

El 4 de noviembre de 2026 el portal DGII de OUTSOLUTECH, RNC 132364805,
alcanzo el **paso 15: Finalizado** y confirmo que completo exitosamente el
proceso de certificacion como Facturador Electronico.

## Resultado del tramite

- Recepcion e-CF y acuses firmados: prueba del paso 9 superada.
- Aprobaciones comerciales: paso 11 superado.
- Paso 12: servicios productivos registrados con base
  `https://erp.uno360x.com/produccion`.
- Paso 13: declaracion generada por DGII, firmada y enviada tras confirmacion
  expresa del representante en el chat. Firma RSA/SHA-256 verificada, texto
  legal conservado y huella del archivo original comprobada.
- Paso 14: verificacion de estatus completada por DGII.
- Paso 15: finalizacion confirmada visualmente en el portal.

Los XML de la declaracion y las capturas se entregaron fuera del repositorio.
No se almacenan contrasenas, claves privadas ni datos de facturas en Git.

## Servicios publicados

Recepcion: `https://erp.uno360x.com/produccion/fe/recepcion/api/ecf`.

Aprobacion comercial:
`https://erp.uno360x.com/produccion/fe/aprobacioncomercial/api/ecf`.

Autenticacion opcional: no anunciada. Cada documento se valida mediante
firma XML, cadena PKIX, vigencia, CRL firmadas y destinatario. No se confunde
acuse de recibo con aceptacion comercial ni se contabilizan automaticamente
documentos recibidos.

Servicio `uno360x-dgii-production`, loopback 18187; estado privado en
`/var/lib/uno360x-dgii-production`, confianza en
`/etc/uno360x-dgii-production/trust`. Version desplegada:
`/opt/uno360x-dgii-production/releases/20261104T142709Z`.

Firma con el certificado ya existente de OUTSOLUTECH mediante LoadCredential;
vigencia hasta 2028-10-28. Huella publica SHA-256:
`5187cb95c492e1d726cf3a69e0c597e1c88a898841a0e49d8cc3805fed660944`.
El ZIP Viafirma TEST se usa exclusivamente en certificacion; queda prohibido
en la confianza de produccion. Las cadenas productivas actuales son Digifirma
y Viafirma; origen y huellas constan en `fiscal/trust/provenance.json`.
Incorporar otra autoridad requiere obtener y verificar su cadena y revocacion
oficiales antes de aceptar sus documentos, nunca confiar en AIA entrante.

## HTTPS, operacion y aislamiento

Cloudflare conservaba SSL Flexible global. Se creo una unica Page Rule
`erp.uno360x.com/produccion/*`, SSL Strict, activa. El resto de hosts y rutas
no cambia. Las rutas fiscales emplean HTTPS tanto hasta Cloudflare como hasta
la VM, con certificado Let's Encrypt valido. HTTP redirige a HTTPS.

Se agrego un snippet Nginx exclusivo y se hizo reload, sin reiniciar Odoo.
El servicio nativo con base `Outsolutech_prueba` mantuvo PID 2195 y cero
reinicios. El archivo de configuracion y las credenciales operativas no se
modificaron. No se actualizaron paquetes Ubuntu ni se altero el SaaS master.

El receptor tiene usuario dinamico, 256 MiB de RAM, cuota CPU 30%, red solo
loopback, tres peticiones simultaneas y XML hasta 5 MB. Estado SQLite con
persistencia FULL, XML sincronizado antes del acuse, reintentos idempotentes
y rechazo de contenido diferente con el mismo emisor/eNCF. No borra originales.
Con menos de 1 GiB libre o mas de 10 GiB de buzon se rechaza para revision;
estos son limites del receptor de OUTSOLUTECH, no cuotas del SaaS.

CRL: actualizacion automatica cada hora desde URLs fijas publicadas por los
emisores; firmas y fechas se verifican antes de reemplazar el cache. Una
indisponibilidad puede utilizar el cache aun vigente; listas vencidas o no
confiables no permiten aceptar documentos. La CRL legacy AVANSI publicada con
SHA-1 se verifica explicitamente contra su clave CA conocida, sin cambiar la
firma SHA-256 de XML ni desactivar validaciones.

Disponibilidad: comprobacion systemd cada tres minutos y journal de fallos.
Respaldos: diarios, 03:40 America/Santo_Domingo mas hasta diez minutos de
dispersion, treinta copias locales bajo permisos root. Cada copia contiene
SQLite consistente y XML, y ejecuta restauracion temporal con comprobacion
de integridad y huellas. No incluye claves privadas. Se verifico una copia
inicial. Copia externa y alertas fuera de la VM siguen siendo trabajo operativo
adicional; las copias locales no protegen de perdida completa de la VM.

## Validacion y reversion

28 pruebas aprobadas en el Python de la VM: 14 de certificacion y 14 de
produccion, incluyendo revocacion de emisor y CA, CRL ausente/vencida/forjada,
destinatario distinto, alteracion, aislamiento entre ambientes, persistencia,
reintentos, restauracion y firma de declaracion con identidad ficticia.
El certificado real se verifico contra su cadena productiva y revocacion.
HTTPS publico: GET 405 y XML invalido POST 400 en recepcion y aprobacion,
incluidas rutas en mayusculas. Ninguna factura real se emitio para estas pruebas.

Reversion: cambiar atomicamente el enlace `source` a la version anterior y
reiniciar solo `uno360x-dgii-production`; mantener el estado actual, no restaurar
una copia antigua sobre documentos posteriores. Para retirar las rutas,
restaurar configuraciones Nginx guardadas en
`/var/lib/uno360x-dgii-install/production-20261104T141859Z`, validar con
`nginx -t` y recargar. La Page Rule fiscal puede desactivarse despues de retirar
las rutas si es necesario. Nunca volver a introducir CA de pruebas en produccion.

## Alcance pendiente de emision

La finalizacion del portal no cambia las secuencias ni convierte el modulo
Odoo de precertificacion en emisor productivo. Los modelos nativos existentes
siguen limitados a `testecf`; no se enviaron e-CF reales ni se cambiaron facturas.
Antes de emitir desde Odoo corresponde verificar en OFV las secuencias e-NCF
autorizadas y habilitar un flujo de emision productiva separado con su control
de duplicados, conciliacion y representacion impresa productiva. No anunciar
la emision comercial como activada solo por completar la certificacion.

## Referencias oficiales

- [Proceso de certificacion DGII](https://dgii.gov.do/cicloContribuyente/facturacion/comprobantesFiscalesElectronicosE-CF/Documentacin%20sobre%20eCF/Documentaciones%20Proceso%20de%20Certificaci%C3%B3n%20FE/Proceso%20de%20Certificacion%20para%20ser%20Emisor%20Electronico.pdf).
- [Servicios de emisores DGII](https://dgii.gov.do/cicloContribuyente/facturacion/comprobantesFiscalesElectronicosE-CF/Documentacin%20sobre%20eCF/Informe%20y%20Descripci%C3%B3n%20T%C3%A9cnica/Descripcion%20Tecnica%20Emisores%20Electronicos.pdf).
- [Cadenas Digifirma](https://digi.camarasantodomingo.do/informacion-adicional/certificados-raiz/).
- [Cadenas Viafirma](https://cps.viafirma.do/).

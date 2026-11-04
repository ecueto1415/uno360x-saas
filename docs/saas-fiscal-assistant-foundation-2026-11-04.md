# Base del asistente fiscal SaaS

Implementado en laboratorio; sin endpoints publicos nuevos ni activacion de
emision comercial. No modifica el Odoo operativo de OUTSOLUTECH.

`control.fiscal_onboarding.FiscalOnboarding` devuelve una lista de pasos por
instancia y empresa: datos del contribuyente, cadena/revocacion del certificado,
delegacion, pruebas, servicios HTTPS, declaracion jurada, certificacion y
secuencias. Cada resultado procede de un adaptador backend de confianza,
con origen, alcance, referencia y caducidad. No acepta un formulario del cliente
como aprobacion DGII. Cambiar RNC o version de certificado invalida resultados;
un fallo al repetir una comprobacion invalida una aprobacion anterior.

`FiscalVault` reconoce el caso de certificado personal del representante
mediante `VerifiedDelegation`: requiere coincidencia de empresa, instancia,
RNC, huella, identificador del titular, referencia y vigencia. El adaptador
externo que verifica la delegacion debe inyectarse desde backend; un diccionario
del navegador no sirve. Se vuelve a comprobar antes de acceder al material
desde el worker. La custodia AES-GCM y las claves siguen separadas por alcance;
la carga mantiene estado pendiente y nunca habilita envios por si sola.

Se corrigio la verificacion de SignedInfo con namespace XMLDSig predeterminado
en el nucleo SaaS, conservando C14N inclusivo, RSA/SHA-256 y digest. Los e-CF
son XML firmados; el PDF es representacion impresa. El certificado se recibe
como PKCS#12 (.p12/.pfx), no como XML.

Verificacion: 23 pruebas de custodia/delegacion/checklist aprobadas bajo el
usuario SaaS en la VM aislada; tres pruebas adicionales locales del nucleo XML
E31/E45, integridad y namespace. Ningun certificado real de OUTSOLUTECH se
uso para estas pruebas y no hubo transmisiones fiscales.

Pendiente: integrar adaptadores reales DGII/PKI, custodia duradera comercial,
pantalla aprobada del asistente, rangos y outbox productivo por empresa,
otros tipos XML, recuperacion y validacion completa en cada cliente. La firma
de declaraciones legales y acceso con clave/token siguen requiriendo la
intervencion correspondiente del titular. La certificacion de OUTSOLUTECH
no se propaga como autorizacion a las empresas del SaaS ni como certificacion
del proveedor. `emission_enabled` permanece falso y `policy.transmit` bloqueado.

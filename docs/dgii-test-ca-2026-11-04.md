# CA de pruebas confirmada por Viafirma

El ZIP recibido en el caso #51937 contiene la CA con SKI 33cd2bc1f3c3da701c6a3a256233e4ae080ab288. Verifica el certificado del envío del portal DGII E310000000006; la CA pública antigua usa otra clave. El comprobante guardado del simulador E310000000009 presenta un certificado vencido el 12 de abril de 2024 y continúa rechazándose.

Se instala únicamente la CA confirmada de 2024 dentro del receptor aislado de certificación. Los otros certificados públicos se conservan como referencia, sin instalarlos en la confianza activa. OpenSSL PARTIAL_CHAIN permite que una CA intermedia instalada y confirmada sea ancla, sin depender de su raíz no publicada. Las fechas, firmas, restricciones y uso digital del emisor se validan. Se exige BasicConstraints CA=true y KeyUsage keyCertSign para cada ancla; un certificado de usuario no es una CA válida. No se confía en certificados extraídos de callbacks ni se cambia la confianza del sistema o del Odoo operativo.

Referencia técnica: https://docs.openssl.org/3.0/man3/X509_VERIFY_PARAM_set_flags/ (X509_V_FLAG_PARTIAL_CHAIN). Fuentes y huellas públicas en certification/trust/provenance.json.

Despliegue independiente: `/opt/uno360x-dgii-certification/releases/20261104T135451Z`. Catorce pruebas automatizadas aprobadas. Reprocesamiento del XML real E310000000006: HTTP 200, ARECF firmado válido, Estado=0. Se reinició únicamente el receptor fiscal; el PID del Odoo operativo permaneció sin cambios. La aceptación final depende del resultado del portal DGII.

Resultado del portal, 2026-11-04: pruebas de recepcion e-CF (paso 9) y aprobaciones comerciales (paso 11) superadas; avance automatico al paso 12, URL Servicios Produccion. Los campos productivos quedaron sin modificar: el receptor instalado es exclusivo de certificacion y no debe publicarse como receptor productivo.

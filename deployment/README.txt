PREPARACIÓN DE UN PILOTO SEPARADO - 01/11/2026

Esta carpeta NO despliega los scripts de desarrollo como servicios públicos.
El gateway actual es de loopback/WSL; debe adaptarse y validarse para el host
nuevo, con cuentas de servicio, orígenes por empresa y TLS. No copiar sin más
los scripts root del laboratorio a una máquina de Internet.

pilot.example.json es una plantilla sin servidor, dominios ni credenciales.
Completar una copia privada fuera del repositorio cuando se definan:
- Servidor nuevo y proveedor; IP distinta de 140.82.47.80 (OUTSOLUTECH).
- Presupuesto mensual máximo para servidor, respaldos y otros servicios.
- Origen de acceso central y dominio para empresas bajo UNO360X.
- Archivo privado de un correo SaaS nuevo; nunca pegar claves en JSON público.
- Destino externo de respaldo y procedimiento independiente para recuperar claves.

Comprobación sin red, sin contratación y sin modificaciones externas:
  python deployment/preflight.py --config RUTA_CONFIG_PRIVADA.json
Salida 0 significa únicamente que la declaración tiene los campos esperados.
Salida 2 significa que faltan datos o que un valor fue rechazado.
deployment_allowed permanece false: este comando NO verifica propiedad de IP,
DNS, HTTPS, capacidad o entrega de correo, ni concede autorización de lanzamiento.
También muestra los requisitos pendientes de product/readiness.json.

Orden posterior, cuando existan los datos del destino:
1. Inventario de solo lectura del host nuevo y verificación de su aislamiento.
2. Adaptación del runtime a servicios separados y secretos del nuevo entorno.
3. Ingreso HTTPS por empresa sin puertos directos a Odoo o PostgreSQL.
4. Correo de confirmación con remitente y credenciales nuevos; prueba de entrega.
5. Copia externa y restauración, observabilidad y pruebas del recorrido público.
6. Piloto limitado con funciones verificadas y condiciones explícitas.
Los pendientes funcionales, fiscales y comerciales del plan general siguen
vigentes; un piloto no equivale a certificar o lanzar todo el producto.

No se ha contratado una VM nueva, cambiado DNS o modificado producción.

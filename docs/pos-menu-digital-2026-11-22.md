# Menú digital público del POS

Implementación del diseño aprobado el 22 de noviembre de 2026. Versión común del servicio de Restaurante; no requiere instalar módulos ni reconstruir las reservas Odoo.

## Uso

Administrador: Restaurante → Menú → Ajustes del POS → Configurar menú digital.

1. Nombre y logo opcional del negocio; activar el menú; rotación de 8 a 60 segundos.
2. Seleccionar los productos a publicar y su disponibilidad.
3. Guardar configuración → Vista previa → Publicar menú.
4. Abrir en televisor o celular; descargar el QR SVG. El enlace no requiere una cuenta.

Los cambios de selección, logo, nombre y disponibilidad se publican explícitamente. Los precios, descripciones, impuestos y fotos de productos publicados se toman del catálogo actual sin volver a publicar. El visitante consulta actualizaciones cada 30 segundos. Los nuevos productos no aparecen hasta seleccionarlos. La disponibilidad es manual; al publicar un producto agotado también se bloquea agregarlo a una cuenta nueva del POS, sin modificar líneas ya pedidas.

TV: tres tarjetas por página, categorías y QR; rotación con pausa; animación suave que respeta reduced-motion. Diseño compacto sin desplazamiento a 1366×768 y vista amplia 1920×1080. Celular: búsqueda, categorías, disponibilidad y detalle con ITBIS/propina/total. Tablet soportada. Es solo consulta, sin pedidos ni pagos públicos. No cambia el transporte fiscal ni certificación de INCIVI.

## Aislamiento

- Tabla `menu_public` indexa token aleatorio de 128 bits a un scope de empresa/sucursal. No contiene contraseñas. El token es un enlace público, no un sustituto del control de acceso del POS.
- DTO público explícito: nombre/logo/intervalo, productos seleccionados y datos de venta visibles. Sin cuentas, usuarios, pedidos, recetas, costos, márgenes, pagos, inventario, credenciales ni configuración fiscal.
- El servidor valida rol Administrador, revisión optimista, productos existentes, tipos, logo raster y límites. Las claves de idempotencia existentes impiden repetir la publicación por doble clic. Hasta 120 productos publicados; logo hasta 120 KB.
- El índice sobrevive al reinicio. Desactivar y publicar revoca datos, QR y fotos. El HTML conserva un mensaje legible de indisponibilidad. Si falla la conexión, se advierte que la copia visible puede estar desactualizada.
- `/menu-pos/` es la única ruta pública añadida a Nginx, exclusivamente GET/HEAD. No envía cookies, Authorization ni pruebas de identidad al servicio. `/api/state` y `/api/command` conservan autenticación firmada. No hay redirección de rutas privadas desde `/menu-pos/`.
- Origen canónico de QR: `POS_PUBLIC_ORIGIN`, predeterminado de producción `https://piloto.uno360x.com`. No se toma del Host público cuando está configurado. Biblioteca QR local qrcode-generator 1.4.4, integridad npm verificada, licencia MIT en vendor. No carga bibliotecas, imágenes ni servicios QR de terceros.
- Fotografías solo de productos publicados; URL con hash para detectar cambios. Caché de fotos 5 minutos; catálogo público sin caché y consulta cada 30 segundos. Menú y estado de caja separados.

## Retirar mesas y zonas

Administrador: Mesas → Administrar mesas → Quitar mesa. Solicita confirmación y conserva historial. No se permite con una cuenta abierta. Mesas retiradas → Restaurar mesa → Guardar.

Mesas → Administrar zonas → Quitar zona. Solo zonas sin mesas activas ni cuentas abiertas, conservando al menos una zona. Zonas retiradas → Restaurar zona. Las zonas archivadas se conservan al guardar nuevos planos. No se destruyen pedidos ni IDs históricos.

## Validación

23 pruebas HTTP/modelo, incluyendo permisos, publicación explícita y reintentos, versiones, separación de empresas, proyección pública, imágenes ocultas inaccesibles, rechazo de SVG, reinicio del índice, precios actualizados sin republicar, agotados bloqueados, revocación y archivo/restauración de mesas y zonas con cuentas abiertas protegidas. Las consultas del menú no modifican pedidos, pagos, ingredientes ni eventos.

Pruebas visuales y táctiles en 390×844, 768×1024, desktop y TV 1920×1080/1366×768: formularios de administración, selección, vista previa, publicación, apertura anónima, búsqueda, detalle fiscal explicativo, rotación/pausa, actualización de precios, pérdida de conexión, revocación y controles por rol. QR decodificado desde imagen con zxing-cpp y comparado con la URL exacta, no solo validado visualmente. Regresión de apertura/mesas/comandas, división y cobro, invitados, instalación inicial, ajustes y reasignación.

Evidencia local fuera de Git: `outputs/Menu_Digital_Implementado`. Pruebas ejecutables en `pos-pilot/menu-public*.test.*`, `floor-archive-ui.test.cjs` y suites previas.

## Despliegue/reversión

`deployment/update_restaurant_public_menu.py` extiende el procedimiento de release aislada: respaldo consistente de SQLite, cambio de symlink, reinicio solo de Restaurante, copia de Nginx, `nginx -t` y recarga gradual. Comprueba que el PID de Odoo y listener fiscal 18198 no cambian. No reinicia gateway, contenedores ni servicios fiscales.

Ante fallo restaura configuración y código; nunca restaura automáticamente la base porque podría perder operaciones posteriores. Para revertir una publicación empresarial basta desactivar el menú y publicar. Un rollback de código conserva campos nuevos e índice; no elimina datos.

## Correcciones del recorrido detectadas por el usuario

- `Cancelar cuenta` en el pedido, solo Administrador, para cuentas sin pagos/documentos. Requiere motivo y confirmación; libera la mesa y conserva líneas y auditoría. Retira las comandas activas sin generar consumo o reverso de inventario. Si hubo preparación real, debe registrarse la merma. Los pagos parciales o completos bloquean esta acción: corresponde devolución.
- Cuentas canceladas visibles en Reportes y sin marca falsa de Pago registrado. Cocina/Barra dejan de mostrar las comandas canceladas.
- Dividir y cobrar → Por persona ahora guía la asignación de los productos de Cuenta general/Compartido. Antes fallaba con un aviso fuera del diálogo aunque las personas ya existieran. La asignación se guarda atómicamente e idempotentemente.
- Si faltan comandas, muestra Enviar comanda y continuar; luego abre la elección de una factura de mesa o separadas. No registra pagos automáticamente. Se probó el caso concreto: dos personas creadas, dos productos sin asignar y sin enviar, dos pagos de prueba por métodos distintos y dos documentos. La emisión fiscal del POS continúa simulada, sin enviar nada a DGII.

## Publicación verificada

Release `/srv/uno360x-saas/restaurant-releases/20261122-public-menu/source`.
Respaldo SQLite: `/var/backups/uno360x-restaurant/split-20261123-004525` (UTC).
Respaldo Nginx/código: `/var/backups/uno360x-restaurant/public-menu-20261123-004525` (UTC).

23 pruebas de modelo pasaron también con el runtime Node del servidor. La comprobación antes/después preservó el estado existente del POS. Odoo productivo y el receptor fiscal de INCIVI conservaron sus procesos; no se reinició el gateway.

En la sesión real de INCIVI se verificaron, sin guardar ni cobrar, Cancelar cuenta, su motivo/confirmación, el nuevo reparto de Mesa 02 con sus dos personas y productos sin asignar, y la configuración del menú en estado No publicado. No se publicaron productos de INCIVI.

Se creó un catálogo de demostración separado, sin empresa Odoo ni credenciales nuevas, sin pedidos ni pagos. Su acceso público HTTPS se verificó en el navegador, en TV 1366×768 y celular 390×844, incluyendo fotos, detalle de impuestos y QR. El QR capturado del sitio público se decodificó y coincide exactamente con su URL HTTPS. El identificador del catálogo está en `/var/lib/uno360x-saas/restaurant/menu-demo.json`, accesible solo para administración del servidor.

Demostración pública: https://piloto.uno360x.com/menu-pos/d2e793d9bb2b40f3bf928cfd25eba157/

Cloudflare rechaza el cliente HTTP Python saliente de la VM con 1010. La verificación pública se realizó en un navegador normal, sin cambiar ni deshabilitar las protecciones de Cloudflare. Las pruebas HTTP de permisos/revocación y la matriz visual se completaron además en el laboratorio.

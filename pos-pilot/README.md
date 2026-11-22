# UNO360X POS · Piloto para restaurantes y bares

Ejecutable de laboratorio para un local ficticio. Requiere Node.js 24 y no requiere instalar paquetes. Desde la raíz del repositorio:

```powershell
node pos-pilot/server.mjs
```

Abre http://127.0.0.1:4177. La base SQLite local se crea en `pos-pilot/var/pilot.sqlite`. Para una corrida limpia, asigna a `POS_DB` otra ruta antes de arrancar. El selector de roles sirve para probar los permisos de la operación. Las fotos del menú se extrajeron de la página 4 del PDF adjunto y se usan como datos de demostración.

## Validación manual

1. Con rol Cajero, abre caja con RD$2,000. En Mesas, cambia a Camarero y abre Mesa 08 para tres personas.
2. Añade hamburguesa, alitas y mojito. Indica una nota o un modificador y envía. Cocina recibe dos partidas y Barra recibe una. Usa el rol de cada estación para marcar listas. Puedes mantener las estaciones abiertas en pestañas distintas.
3. Añade otro mojito y vuelve a enviar. La segunda comanda contiene solo un mojito para Barra. Antes de esa segunda ronda el total es RD$1,497.60. Con el segundo mojito, RD$1,881.60.
4. Con rol Cajero, usa Dividir y cobrar. Cobra hamburguesa y alitas en efectivo (RD$1,113.60) y los dos mojitos con tarjeta (RD$768.00). Selecciona E32. Comprueba que Pago figura como Registrado y el comprobante como Simulado. Pulsa Reintentar comprobante.
5. En Inventario, el ron pasa de 2,500 a 2,410 ml. Con rol Barra, registra 20 ml de merma y un conteo de 2,385 ml. La diferencia frente a 2,390 ml esperados es −5 ml. En Menú, el mojito cuesta RD$38.75 por receta y deja margen bruto antes de impuestos de RD$261.25 al precio normal o RD$211.25 en happy hour.
6. En Reportes, cierra contando RD$3,110.00. El efectivo esperado es RD$3,113.60 y la diferencia es −RD$3.60. Abre otro turno y repite los tres productos para llevar. El total es RD$1,380.60 con propina cero. Prueba E31 con un RNC ficticio de nueve dígitos.
7. Con rol Supervisor, crea un producto o cambia sus precios, modificadores e imagen. Prueba anular o descontar una partida sin pagar y verifica el motivo y el rol en Autorizaciones.

```powershell
node --test pos-pilot/acceptance.test.mjs
```

La prueba HTTP usa una base en memoria. Verifica totales, comandas incrementales, permisos, pago dividido, doble solicitud de pago, reintento fiscal, consumo, merma, conteo y cierre.

## Integración con UNO360X

- **Cuenta y contratación.** La entrada prevista es un módulo adicional habilitado por una suscripción POS independiente de Base Empresarial (US$45). El repositorio ya tiene sesiones y membresías de negocio en `control/identity.py` y `control/access_broker.py`. El piloto puede leer la sesión del laboratorio y valida la membresía, la habilitación del módulo y el permiso de caja en el servidor. El selector de roles aparece en el modo de demostración.
- **Sucursales y usuarios.** El piloto usa Sucursal Centro y Caja 01. En modo conectado, la configuración del piloto asigna la sucursal del negocio y el permiso por cuenta. Los negocios y sucursales guardan datos separados y el registro de caja identifica al usuario de la sesión. Queda pendiente la gestión comercial de contratos y sucursales desde UNO360X.
- **Inventario.** Las recetas, mermas y conteos se prueban en SQLite. La integración mapeará ingredientes y unidades a productos y almacenes de la sucursal en UNO360X. El pago y los movimientos locales se registran en una sola transacción. La salida hacia inventario central deberá reutilizar el identificador del pago para evitar duplicados.
- **Fiscal.** El comprobante del piloto es simulado. El adaptador real usará los datos fiscales y secuencias del negocio, y el constructor y las validaciones de `addons/uno360x_ecf_core`. Debe conservar una referencia fiscal única por pedido, guardar el XML firmado y consultar el estado antes de reenviar. Pago y estado fiscal permanecen separados. Las tasas y reglas de la maqueta son datos de aceptación del piloto.

### Modo conectado al laboratorio

Inicia primero el servicio de identidad del repositorio y entra desde el mismo host de loopback que usará el POS. Usa una base de identidad del laboratorio. El piloto verifica la cookie existente de UNO360X y lee esa base en modo de solo lectura.

Configura `POS_IDENTITY_DB` con la ruta de esa base y `POS_ENTITLEMENTS` con la ruta de un JSON de habilitaciones de prueba. Usa los identificadores reales del laboratorio en lugar de los ejemplos:

```json
{
  "defaultTenant": "id-negocio",
  "tenants": {
    "id-negocio": {
      "enabled": true,
      "branch": "centro",
      "branchName": "Sucursal Centro",
      "users": { "id-cuenta": "caja" }
    }
  }
}
```

Reinicia el piloto con esas dos variables. Los propietarios y administradores habilitados tienen rol supervisor por defecto. La prueba automatizada verifica que un contrato deshabilitado deniega el acceso, que una cuenta comparte la sesión y que los turnos de otra sucursal quedan separados.

## Mapa de las 18 vistas del PDF

| Vistas | Estado |
| --- | --- |
| 02 Apertura de turno, 03 Mesas, 04 Caja y menú | Funcionales en Sucursal Centro. |
| 05 Personalización, 06 Para llevar y barra | Modificadores, notas y pedidos funcionales. |
| 07 Cocina, 08 Barra | Comandas por estación, actualización periódica y estado lista. |
| 09 División, 10 Cobro y facturación, 11 Comprobante | División por producto, tres métodos y estado fiscal simulado. Ticket de prueba imprimible. PDF fiscal pendiente. |
| 12 Devoluciones y nota de crédito | Devolución local por partidas, con autorización y ajuste de caja. E34 y abono externo pendientes. |
| 13 Cierre, 14 Menú y recetas, 15 Inventario y mermas, 16 Reportes | Cierre, receta, márgenes, merma, conteo y desglose funcionales. Horario automático de happy hour y reportes históricos pendientes. |
| 17 Usuarios y permisos, 18 Equipos y estaciones, 19 Contingencia | Roles y sesión compartida en laboratorio, más dos estaciones. Activación comercial y equipos físicos pendientes. Continuidad por red local probada en navegador, con bloqueo de solicitudes externas. |

Para continuidad, falta probar un servidor local de sucursal accesible desde caja, cocina y barra por la red interna, con cola persistente para sincronización y resolución de conflictos al volver internet. El piloto comparte estado cuando las pantallas alcanzan el mismo servidor local. No implementa trabajo independiente de una terminal desconectada ni sincronización con la nube.

## Inventario central y certificación

Para el conector de inventario prepara una base desechable de Odoo 18 cuyo nombre empiece por `uno360x_pos_lab`. Instala `uno360x_pos_pilot_stock`, crea los productos almacenables de ingredientes, una ubicación interna de origen y una ubicación de inventario de destino, ambas de la empresa. Usa un usuario técnico de inventario del laboratorio.

Establece `POS_ODOO_KEY` fuera del repositorio y apunta `POS_ODOO_CONFIG` a un JSON con el siguiente formato. Los identificadores son ilustrativos. `factor` convierte la cantidad local a la unidad de medida de Odoo.

```json
{
  "origin": "http://127.0.0.1:8069/",
  "database": "uno360x_pos_lab",
  "login": "pos-stock-lab",
  "branches": {
    "negocio-demostracion:sucursal-centro": {
      "company": 1,
      "source": 8,
      "destination": 14,
      "products": {
        "ron": {"id": 101,"factor": 0.001},
        "limon": {"id": 102,"factor": 0.001},
        "jarabe": {"id": 103,"factor": 0.001},
        "menta": {"id": 104,"factor": 1},
        "soda": {"id": 105,"factor": 0.001}
      }
    }
  }
}
```

Cobra un mojito y abre **Inventario → Sincronizar inventario de pruebas**. Revisa los movimientos terminados en Odoo. Repite el botón y comprueba que no aparecen movimientos nuevos. Un fallo conserva el consumo local y la misma referencia para el siguiente intento. Los conteos físicos quedan como comparación local. En modo conectado usa `id-negocio:centro` como clave de sucursal. Una venta local previa a esta versión sin referencia queda fuera de la sincronización.

La validación fiscal local usa el caso para llevar de RD$1,380.60 y comprueba firma y estructura de los XML E31 y E32 con un certificado ficticio. Ejecuta `python pos-pilot/fiscal_check.py` con `lxml`, `cryptography` y `tzdata` disponibles. E31 se dirige al servicio e-CF y ese E32 requiere un RFCE. El RFCE ya se deriva del E32 firmado, se firma y se valida localmente. El transporte de certificación está probado con respuestas simuladas. Todavía falta remitir los casos asignados y verificar la respuesta real. La representación fiscal de la propina para consumo local queda pendiente. Para una prueba real hacen falta el emisor autorizado en certificación, certificado de prueba y casos/e-NCF del set asignado por la DGII. El piloto continúa mostrando estado simulado.

### Envío de un caso asignado por DGII

Usa el XML E31 o E32 completo y firmado del set de certificación, el certificado autorizado que lo firmó y una carpeta persistente de bitácora. Configura `POS_CERT_PASSWORD` fuera del código. La herramienta llama exclusivamente a los servicios `certecf` y deriva el RFCE para un E32 inferior a RD$250,000. Si ya hay una entrada de bitácora para ese emisor y e-NCF, consulta el estado antes de intentar de nuevo. Una respuesta HTTP o un TrackId no prueban aceptación fiscal.

```powershell
python pos-pilot/dgii_certification.py E31-o-E32-firmado.xml --p12 certificado-certificacion.p12 --journal pos-pilot/var/dgii --submit-certification
```

Prueba de inventario en Odoo 18 y PostgreSQL 16 locales: se repitió la misma referencia de consumo de 45 unidades. El saldo pasó de 2,500 a 2,455 y la base conservó un único movimiento terminado. Prueba fiscal local: E31, E32 y RFCE firmados con certificado ficticio, selección de servicio, autenticación simulada y bloqueo del segundo envío.


## Tickets, devoluciones y operación por red local

- Desde una venta pagada, usa **Imprimir ticket**. En Reportes puedes abrir la venta e imprimir otra copia. En la impresora selecciona papel de 80 mm. El ticket es de prueba y no sustituye un documento fiscal.
- Con rol Supervisor y con el turno original todavía abierto, abre **Devolver partidas**, selecciona los artículos y escribe el motivo. El ajuste se registra con los métodos de pago originales. El arqueo muestra devoluciones por método y descuenta del efectivo esperado las devoluciones en efectivo. Los ingredientes preparados conservan su consumo. Una partida solo admite una devolución. En el piloto no se abona a tarjetas ni se transmite información a la DGII.
- Caja, Cocina y Barra pueden operar si el navegador conserva acceso al servidor de la sucursal. El POS sirve sus recursos localmente. Para probar en varias terminales del laboratorio, configura un proxy HTTPS privado al servicio de loopback, integra la sesión de UNO360X y establece `POS_ORIGIN` con el origen HTTPS exacto. Mantén la base de identidad y POS en la sucursal. La prueba de navegador bloqueó solicitudes externas y verificó que la comanda llegara a Cocina desde una segunda pestaña. No equivale a una prueba en varios equipos físicos.
- Si una terminal pierde contacto con Caja y no recibe respuesta, repite la misma acción con los mismos datos desde la misma pestaña. La pestaña conserva la referencia mientras permanece abierta. El trabajo con la terminal completamente desconectada, la recuperación tras cerrar una pestaña con una solicitud pendiente y la sincronización posterior con la nube siguen pendientes.
- Para habilitar el módulo en el laboratorio, usa la autorización independiente del negocio en `POS_ENTITLEMENTS`. La prueba automatizada verifica que una cuenta con sesión de UNO360X entra con su permiso, y que un negocio que tiene el módulo deshabilitado queda fuera. Facturación de la suscripción, alta comercial y despliegue en producción quedan pendientes.


## Interfaz aprobada y pantallas táctiles · 22 de noviembre de 2026

Se adaptó el piloto existente al primer diseño aprobado: menú lateral azul, productos con fotos a la izquierda, pedido a la derecha y Cobrar destacado. Se conservan los precios y funciones del piloto; el cambio no sustituye el motor de pagos, inventario ni la simulación fiscal. Se añadió la vista Pedidos para volver a las cuentas abiertas.

Pantallas amplias: catálogo y pedido en dos columnas. Tablet vertical y móvil: distribución apilada, navegación que se ajusta al ancho y acceso fijo Ver pedido con total. Botones de al menos 44 px y 48 px para puntero táctil, formularios de 16 px en touch, foco visible y respeto a movimiento reducido. No se requiere hover.

Pruebas: node --test pos-pilot/acceptance.test.mjs (5 casos); node --test pos-pilot/ui-acceptance.test.cjs (2 casos de navegador). La segunda requiere Playwright; POS_PLAYWRIGHT_PATH permite usar una instalación existente, POS_SCREENSHOTS define la carpeta de evidencias. Validado con Edge sin interfaz visible a 320, 390, 768, 1024 y 1440 px; emulación touch en teléfono y tablet vertical/horizontal, selección de modificadores y notas, pedido accesible, cobro, comandas incrementales, segunda ronda, inventario, cierre y para llevar. Sin desplazamiento horizontal ni errores de JavaScript detectados. La emulación no sustituye pruebas con impresoras o dispositivos físicos.

Piloto local separado disponible en http://127.0.0.1:4187/?mesa=8 con POS_DB=pos-pilot/var/diseno-aprobado-20261122.sqlite. Datos ficticios: fondo RD$2,000, Mesa 08 y tres productos, sin pagos emitidos. El enlace directo solo selecciona una mesa presente en el estado autorizado por el servidor. Para reiniciar usa POS_PORT=4187, POS_DB con esa ruta y node pos-pilot/server.mjs. Las variables de conexión a identidad/inventario no están configuradas en esta demostración.

No se publicó en producción ni se modificaron OUTSOLUTECH o INCIVI. Continúan pendientes la aceptación fiscal real del POS, la integración comercial final y la sincronización offline, según las limitaciones del piloto documentadas arriba.


Ajuste de facilidad de uso: móvil/tablet vertical muestran un botón Menú para evitar que las ocho opciones ocupen la pantalla; al seleccionar una sección, la navegación se recoge. Ver pedido y total permanecen accesibles en la barra inferior. Las tres pruebas touch completaron agregar/modificar, enviar y pagar (efectivo, tarjeta, transferencia según dispositivo) y verificaron un único consumo de receta por venta. La prueba detectó y corrigió que el botón fijo quedara deshabilitado tras guardar un producto; forma parte del recorrido de regresión.

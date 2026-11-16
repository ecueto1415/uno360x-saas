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
| 09 División, 10 Cobro y facturación, 11 Comprobante | División por producto, tres métodos y estado fiscal simulado. PDF fiscal pendiente. |
| 12 Devoluciones y nota de crédito | Próxima etapa. El piloto permite anular partidas sin pagar con autorización. |
| 13 Cierre, 14 Menú y recetas, 15 Inventario y mermas, 16 Reportes | Cierre, receta, márgenes, merma, conteo y desglose funcionales. Horario automático de happy hour y reportes históricos pendientes. |
| 17 Usuarios y permisos, 18 Equipos y estaciones, 19 Contingencia | Roles y sesión compartida en laboratorio, más dos estaciones. Activación comercial, equipos, impresoras y continuidad sin internet pendientes. |

Para continuidad, falta probar un servidor local de sucursal accesible desde caja, cocina y barra por la red interna, con cola persistente para sincronización y resolución de conflictos al volver internet. El piloto comparte estado cuando las pantallas alcanzan el mismo servidor local. No implementa trabajo independiente de una terminal desconectada ni sincronización con la nube.

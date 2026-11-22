# POS: productos, división de cuenta y mesas

## Recorrido

Mesas empieza con cinco mesas por negocio. Supervisor ve **Administrar mesas**:
agregar número/nombre, renombrar y activar/desactivar. El servidor rechaza cambios
sin permiso y desactivar una mesa con una cuenta abierta. Se conserva cualquier
mesa antigua con pedido abierto aunque no forme parte de las cinco iniciales.
La configuración es independiente por empresa en el estado del POS.

En la cuenta, cada tarjeta incluye **+ Agregar al pedido**. Una guía explica
tocar el producto, elegir opciones y pulsar **Añadir a la cuenta**. El aviso
confirma qué se agregó y recuerda enviar la comanda. Crear productos del catálogo
sigue en **Menú → + Nuevo producto**, restringido por el servidor a supervisor.

**Dividir y cobrar** ofrece **Por productos** y **En partes iguales**.
En celular/tablet hay además **Dividir cuenta** fijo abajo, junto al saldo pendiente.
El cajero indica de 2 a 30 personas, calcula y selecciona la parte que cobra.
Cada parte admite efectivo, tarjeta o transferencia. La primera confirmación fija
la cantidad de personas y el importe de cada parte. Se conservan una cuenta y un
comprobante para la mesa; no son facturas fiscales distintas por comensal.

Los importes se distribuyen en centavos enteros, incluyendo ITBIS y propina aplicable.
Ejemplo: RD$1,497.60 / 7 = dos partes de RD$213.95 y cinco de RD$213.94.
Las partes pagadas aparecen identificadas y no vuelven a ofrecerse en el selector.
No se mezcla con cobros previos por productos ni se modifica el pedido después del
primer pago. El stock del pedido se consume una vez al primer pago de partes iguales;
los siguientes pagos no vuelven a consumirlo. El comprobante simulado se crea solo
al terminar. Una devolución de una cuenta dividida en partes iguales requiere todas
sus partidas y conserva la distribución por métodos de pago originales.

## Seguridad y pruebas

- Transacción SQLite y claves de idempotencia existentes, más exclusión de partes
  cobradas: doble clic con la misma clave o reintento con otra no duplica cobros.
- Siete pruebas HTTP: recorrido previo, permisos y aislamiento, inventario,
  devoluciones, mesas y división exacta de siete personas.
- Prueba táctil adicional: tablet 768x1024 y celular 390x844; cinco mesas iniciales,
  alta de Terraza 06, tres productos, división en siete partes, efectivo/tarjeta,
  inventario una vez y cierre con diferencia cero.
- Regresión de navegador: asignación/reasignación por permisos, modificadores,
  división por productos, segunda ronda, Cocina/Barra y pedidos para llevar.

## Publicación

Versión común del servicio aislado `uno360x-restaurant.service`, puerto 18248.
No requiere actualizar bases Odoo, reservas, gateway ni servicios fiscales.
`deployment/update_restaurant_split.py` toma copia SQLite consistente, cambia el
enlace de versión y reinicia solo Restaurante. Verifica PID OUTSOLUTECH y receptor
fiscal INCIVI sin cambios. No restaura datos automáticamente. Una reversión posterior
a pagos reales en partes iguales requiere revisar la compatibilidad del estado;
no se debe volver al código anterior ignorando cobros existentes.

El piloto conserva pagos y fiscal simulados; no se envían documentos a DGII.
Evidencias: `outputs/POS_Dividir_Mesas_20261122` en el directorio padre del checkout.

Publicado en `20261122-split-tables/source`. Siete pruebas HTTP aprobadas también
con el runtime del servidor; cinco pruebas de navegador aprobadas (la adicional
recorre tablet y celular). Hashes de los cuatro archivos servidos coinciden con
los probados. Acceso sin identidad a API devuelve 403. El contenido de todos los
estados de empresas permaneció idéntico a la copia previa al despliegue.
OUTSOLUTECH conservó PID 3072027 y el receptor fiscal INCIVI PID 1265678.
Copia previa: `/var/backups/uno360x-restaurant/split-20261122-152407`.

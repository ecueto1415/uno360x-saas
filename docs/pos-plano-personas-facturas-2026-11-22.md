# POS: plano, personas y facturación por mesa o persona

Fecha: 2026-11-22. Rama: `dev/pos-primer-diseno-20261122`.

## Alcance

Una sola versión del servicio aislado de Restaurante para todas las empresas autorizadas del SaaS. Conserva el menú, los colores y los componentes actuales. No instala módulos, modifica bases Odoo, cambia certificados ni reinicia OUTSOLUTECH o el receptor fiscal de INCIVI.

- Mesas → plano por zonas, nombre, lugares, forma y posición. Seleccionar una mesa muestra responsable, tiempo, estado y pendiente permitido. Administrador edita; Caja consulta. Flechas para pantallas táctiles y arrastre con mouse. Guardar comprueba versión para impedir sobrescribir una edición concurrente; Cancelar no escribe.
- Dentro del pedido: `+ Crear persona`, nombre opcional (Persona N si se deja vacío), edición y asignación de productos. La cantidad de comensales no genera personas automáticamente. Los nombres son alias de ese pedido, no contactos ni usuarios.
- Cuenta general, personas y Compartido son filtros y asignaciones; el total de la mesa permanece visible. Para facturas separadas se exige asignar todas las líneas a personas antes del primer pago.
- Dividir y cobrar → Por persona permite elegir Una factura para la mesa o Facturas separadas por persona. La elección queda fija tras el primer pago. Se mantienen división por productos y partes iguales para una factura de mesa.
- Un pago por persona liquida sus productos completos; E31 separado pide RNC y razón social. Puede combinarse efectivo, tarjeta y transferencia entre personas. Cada documento conserva líneas, comprador, total y pagos propios. Imprimir no cobra ni consume inventario.
- Los comprobantes de este POS siguen siendo **simulados, sin e-NCF y sin envío a DGII**. No se cambia la facturación electrónica normal de INCIVI. La certificación/transporte fiscal del POS continúa pendiente de su etapa específica.

## Permisos y aislamiento

La identidad, empresa, sucursal y rol base proceden del acceso firmado existente. Los encabezados de rol del navegador no sustituyen esa identidad.

Administrador: plano y roles del equipo. Caja: todos los importes y cobro. Camarero: cuentas e importes de sus mesas; puede ver el responsable/estado de otras mesas sin líneas ni importes. Cocina y Barra: sus comandas sin precios, pagos, costos o historial de operaciones. La proyección se aplica a respuestas del servidor, no solo a CSS.

Ajustes del POS → Equipo del POS permite al administrador limitar usuarios POS ya habilitados a Caja, Camarero, Cocina o Barra. No crea usuarios ni permite conceder Administrador. Los responsables administrativos verificados conservan esa función. La configuración y el estado quedan separados por empresa/sucursal.

Las operaciones mantienen claves de idempotencia, comprobación de autor y contenido, transacción SQLite y validación de líneas pagadas. Reintentar no vuelve a cobrar, crear documento ni consumir ingredientes. No hay migración destructiva: campos nuevos opcionales, datos anteriores conservados.

## Validación

- 19 pruebas HTTP/modelo: persistencia/versiones del plano, permisos, roles restringidos e intentos de suplantación por encabezados, empresas separadas, personas manuales, nombres duplicados, líneas compartidas pendientes, modalidad fija, doble clic, reintento fiscal y consumo único.
- Tablet 768×1024 y celular 390×844: flechas, guardar/cancelar plano, crear y renombrar Carlos/Ana, asignar productos, comandas, cuentas unificadas y separadas, efectivo/tarjeta, impresión por documento, cierre e inexistencia de controles administrativos para Camarero. Sin desplazamiento horizontal ni errores JavaScript.
- Resultado: subtotal RD$1,170.00; ITBIS RD$210.60; propina RD$117.00; total RD$1,497.60. Carlos RD$960.00 y Ana RD$537.60. Una factura de mesa o dos documentos separados; dos pagos; un solo consumo de ron de 45 ml; caja sin diferencia.
- Regresión visual/táctil: recorridos de Cocina y Barra, ronda adicional, productos/modificadores, división igual entre 7 personas, para llevar sin propina, alta inicial de los cuatro tipos de negocio, ajustes y reasignación de responsable. Desktop incluye arrastre, guardado y recarga del plano.
- Evidencia local: `outputs/POS_Plano_Personas_Implementado` (fuera del repositorio), pruebas en `pos-pilot/*test*`.

## Publicación y reversión

El paquete modifica únicamente el servicio `uno360x-restaurant.service`, en `127.0.0.1:18248`, detrás de la ruta SaaS existente `/uno360x-restaurante/`. Los mismos archivos sirven a clientes actuales y nuevas cuentas; no requiere reconstruir reservas Odoo ni actualizar cada base individual.

Publicar una release nueva en `/srv/uno360x-saas/restaurant-releases/`, ejecutar las pruebas de modelo en ella y usar `deployment/update_restaurant_split.py`. Ese procedimiento respalda SQLite consistentemente, cambia el enlace `restaurant-current`, reinicia solo Restaurante y verifica que no cambien el PID de Odoo productivo ni el receptor fiscal 18198. Comprobar también hashes servidos y estado empresarial conservado.

Reversión de código: apuntar `restaurant-current` a la release guardada en el respaldo y reiniciar solo Restaurante. No restaurar automáticamente la base de datos: hacerlo perdería operaciones posteriores; debe evaluarse antes de cualquier restauración. Los campos añadidos permanecen compatibles con la lectura anterior.

## Uso

1. UNO360X → Punto de venta → Restaurante → Mesas.
2. Administrador: Editar plano, seleccionar mesa, ubicar/configurar y Guardar plano.
3. Seleccionar mesa → Abrir pedido → indicar comensales y responsable.
4. Crear persona por nombre cuando haga falta. Elegir a quién agregar productos y enviarlos a Cocina/Barra.
5. Dividir y cobrar → Por persona → escoger factura de mesa o separadas antes de registrar el primer pago.
6. Cobrar las personas pendientes; consultar e imprimir cada documento de prueba.

## Publicación verificada

Release activa: `/srv/uno360x-saas/restaurant-releases/20261122-floor-guests/source`.
Respaldo: `/var/backups/uno360x-restaurant/split-20261122-172512`.
Las 19 pruebas de modelo pasaron también con el Node del servidor. Los tres archivos servidos coinciden con la release. Se verificó identidad exacta del estado empresarial antes/después y continuidad de los procesos productivos protegidos.

INCIVI: sesión existente, plano en tablet 768×1024, Mesa 08 existente y creación de persona en celular 390×844. Se abrió y canceló el formulario sin guardar personas, cobrar ni emitir. Se restableció el tamaño de la ventana. Evidencias `incivi-plano-tablet-publicado.jpg` e `incivi-crear-persona-celular-publicado.jpg`.

También pasó la prueba desktop de arrastre, guardar y recargar. En pantallas táctiles se usan las flechas para ubicar mesas; se evitó capturar gestos de desplazamiento del usuario.

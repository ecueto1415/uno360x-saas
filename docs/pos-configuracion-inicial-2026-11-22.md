# Configuración inicial del POS

Implementa el PDF aprobado `UNO360X_POS_Flujo_Inicial_Diseno_Actual_v2.pdf`.
Se conserva el HTML del shell, su navegación y la hoja de estilos del POS.
No se agregan logos, menús o diseños alternativos. La configuración se presenta
en paneles existentes dentro del contenido.

## Flujo y persistencia

1. **Elige tu negocio**: Restaurante y bar, Cafetería y panadería, Tienda y comercio
   o Venta rápida. Guarda el tipo y el siguiente paso por empresa/sucursal.
2. **Configura tus mesas**: cinco iniciales, cantidad editable, nombres, alta y
   desactivación. Cafetería puede operar con o sin mesas. Tienda y Venta rápida
   saltan el salón y lo desactivan. Nunca se desactiva una mesa con cuenta abierta.
   Se conservan nombres y mesas desactivadas individualmente dentro de la cantidad.
3. **Agrega tus productos**: reutiliza el diálogo real Nuevo producto del Menú.
   Nombre, categoría, precio, ITBIS, estación, modificadores, imagen/foto y happy hour.
   Se admite **Sin comanda** para productos de venta directa; estos no esperan
   preparación de Cocina/Barra. Ejemplos opcionales según negocio, con carga única.
   Finalizar guarda y vuelve a Caja; no abre turno, cobra ni emite un comprobante.

Los POS nuevos empiezan sin productos. Al recargar se recupera el paso guardado.
POS existentes sin el campo `setup` siguen operativos y no se reinicializan.
El supervisor puede entrar por **Menú → Configurar mi POS**, conservando catálogo,
pedidos y pagos. Reconfigurar una empresa ya lista no bloquea a otros cajeros.
Un POS nuevo pendiente sí requiere al supervisor antes de permitir abrir un turno.

El tipo de negocio controla este asistente, las mesas y los ejemplos, no una
migración al POS nativo anterior ni un cambio del plan/suscripción. Permanecen
el mismo POS y su navegación; la facturación del piloto sigue siendo simulada.

## Autorización y consistencia

Todos los comandos `setup-*` exigen supervisor verificado por el gateway. Las
mutaciones siguen en la transacción por scope y usan las claves de idempotencia.
Se prueban rechazo de roles insuficientes, valores inválidos, carga repetida de
ejemplos, protección de mesas ocupadas y separación entre empresas.

`makeDemoServer` es una fábrica exclusiva de fixtures de pruebas para los escenarios
anteriores con productos precargados. No está conectada a ninguna ruta ni variable
de despliegue. El servicio normal utiliza `makeServer` con la configuración inicial.

## Verificación

- Seis pruebas nuevas HTTP/dominio, incluyendo cuatro tipos de negocio, reanudación,
  permisos, aislamiento y conservación de un estado previo.
- Ocho recorridos nuevos de navegador: cuatro tipos en tablet 768x1024 y celular
  390x844. Alta y edición, recarga en paso 3, finalización sin venta y reapertura
  posterior. Navegación y logo iguales; sin desbordamiento horizontal ni errores JS.
- Siete pruebas HTTP anteriores y cinco pruebas de navegador de regresión: comida
  a Cocina, mojitos a Barra, segunda ronda incremental, cobros por productos y partes
  iguales, descuentos, inventario una vez y cierre sin diferencia.
- Evidencias locales en `outputs/POS_Configuracion_Implementada` (padre del checkout).

## Publicación aislada

Solo se actualizan app.mjs, domain.mjs y server.mjs del servicio Restaurante.
style.css e index.html no cambian. No se actualizan bases Odoo, reservas, permisos
de Odoo, gateways, certificados ni servicios de facturación. La versión común aplica
a clientes actuales y futuros que accedan a Restaurante.
Se toma copia consistente de SQLite y se reinicia únicamente
`uno360x-restaurant.service`, comprobando que OUTSOLUTECH y el receptor INCIVI
conserven sus procesos. No hay emisión de XML ni conexión nueva a DGII.

Publicado en `/srv/uno360x-saas/restaurant-releases/20261122-initial-setup/source`.
Las 13 pruebas HTTP pasaron también con el runtime del servidor. Copia previa:
`/var/backups/uno360x-restaurant/split-20261122-155910`.
Verificado en navegador autenticado de INCIVI: Menú > Configurar mi POS abre
el primer paso. Se dejó abierto sin cambiar el tipo de negocio ni cargar productos.
Solo se inicializó metadato de configuración del POS existente; se conservan
productos, mesas, pedidos, pagos, inventario, eventos y turno previos.
OUTSOLUTECH y receptor fiscal INCIVI conservaron sus procesos. Gateway sin reinicio.
Captura: `incivi-configuracion-publicada.png` en la carpeta de evidencias.

# Asignación de mesas en el POS del SaaS

Publicado el 22 de noviembre de 2026 en la versión común del gateway del SaaS.

## Comportamiento

- Cada pedido conserva el identificador y nombre del responsable que atiende.
- El responsable aparece en Mesas, Pedidos, la cuenta y las estaciones.
- Al abrir una mesa, caja o supervisor selecciona un responsable habilitado.
- El camarero de laboratorio abre a su propio nombre y no puede asignar a otro.
- Solo supervisor puede reasignar una mesa abierta del turno actual. El motivo
  es obligatorio y el cambio registra anterior, nuevo, autor, nombre y fecha.
- Reportes muestra esos cambios. Repetir la misma solicitud no duplica el registro.
- Las mesas antiguas sin responsable aparecen como Sin asignar hasta reasignarlas.

## Acceso y aislamiento

Ruta: Comercial > Punto de venta > Cajas (`/uno360x-pos`) > Restaurante.
Acceso directo autenticado: `https://piloto.uno360x.com/uno360x-restaurante/`.

No se utilizan cabeceras de rol ni selectores enviados por el navegador como
autorización. El gateway valida la membresía central y comprueba los grupos
de Odoo con su sesión existente. Gerente de Punto de venta equivale a supervisor;
Usuario de Punto de venta equivale a caja. La lista de responsables incluye
usuarios internos activos de la misma empresa con acceso a POS. La lista se
guarda en memoria 30 segundos; el acceso y permiso del actor se validan siempre.
La configuración de roles específicos para cocina/barra/camarero en el SaaS
no se amplía en esta entrega; sus flujos están probados en el laboratorio.

El gateway firma método, ruta, empresa, usuario, rol y resumen del cuerpo con
HMAC de duración breve. El servicio escucha solo en loopback. Cada empresa
tiene un estado separado por tenant y compañía. La clave no está en Git.

## Instalación

- Servicio independiente: `uno360x-restaurant.service`.
- Puerto reservado y comprobado: `127.0.0.1:18248`.
- Base exclusiva del piloto: `/var/lib/uno360x-saas/restaurant/pilot.sqlite`.
- Código común: `/srv/uno360x-saas/restaurant-current`.
- Runtime privado verificado con SHASUMS de nodejs.org: Node v24.11.1.
- Límite de memoria 384 MiB y CPU 50 %. Memoria observada al verificar: 19 MiB.
- Control de publicación: `deployment/deploy_restaurant_pilot.py`.
- No hay actualización de módulos ni escritura de datos en Odoo para esta función.
- La misma ruta y servicio se aplican a empresas existentes y futuras con
  permisos POS. No se reconstruyen reservas ni se cambia ningún plan comercial.

El primer preflight detectó que 18198 estaba ocupado por la recepción fiscal
de INCIVI. Se abandonó ese puerto sin detener su proceso y se usó 18248.
Se corrigió además el arranque desde symlink y el uso de SQLite entre hilos:
las consultas de permisos usan una identidad nueva por solicitud y el opener
autenticado de Odoo, nunca la conexión SQLite del hilo del login.

El despliegue reinició solo el gateway del SaaS y el servicio nuevo del POS.
Los accesos del gateway se reanudaron desde la sesión central. OUTSOLUTECH no
se reinició. Los procesos de recepción fiscal y sus rutas Nginx no se modificaron.

## Validación

- Seis pruebas HTTP/dominio, localmente y en el runtime del servidor: aprobadas.
- Dos pruebas Python de autorización del gateway: aprobadas.
- Cuatro pruebas de navegador con Edge: aprobadas. Incluyen teléfono 390x844,
  tablet 768x1024 y 1024x768; diseño hasta 1440 px y mínimo 320 px.
- Prueba con identidad confiable de supervisor, cajero y camarero: el control
  de reasignación solo aparece para supervisor. El servidor rechaza roles
  insuficientes, responsables externos, motivo vacío y cuerpo manipulado.
- Mesa 08: primera y segunda ronda, comida a Cocina, mojitos a Barra,
  efectivo y tarjeta, ingrediente descontado una vez, cierre sin diferencia.
- Reasignación con solicitud repetida: una auditoría, sin duplicados.
- Navegador del SaaS con sesión de INCIVI: apertura de turno ficticio con
  fondo cero, Mesa 08 a gladis, cambio a Administrator y regreso a gladis.
  Verificados nombre y auditoría en viewport de celular y tablet.
- En el estado separado del POS: una mesa vacía, cero pagos, cero eventos de
  inventario y cero comprobantes. Se conservó para revisión visual.
- OUTSOLUTECH conservó su PID; hashes del código fiscal común sin cambios;
  receptor fiscal de INCIVI conservó PID 1265678 y devolvió el 405 esperado
  al GET de solo lectura (requiere POST XML). No se envió ningún XML.

Evidencias locales: `outputs/POS_Primer_Diseno_20261122/`, en el directorio
padre del checkout. `saas-tablet-mesas.jpg`, `saas-tablet-historial.jpg` y
`saas-telefono-reasignar.jpg` corresponden al SaaS desplegado.

## Reversión y alcance

Respaldo previo: `/var/backups/uno360x-restaurant/20261122-144457/`.
Para retirar esta versión, restaurar el gateway guardado, reiniciar solo
`uno360x-saas-pilot.service` y detener `uno360x-restaurant.service`. Conservar
la base del piloto; no eliminar datos. El instalador hace esa reversión si
falla su comprobación de arranque. Una publicación futura del gateway debe
conservar el hook de restaurant o ejecutar de nuevo el instalador.

El restaurante sigue siendo un piloto explícito, con pagos y fiscalidad
simulados. No está conectado al certificado, secuencias ni inventario productivo
de INCIVI. Su facturación electrónica normal queda completamente aparte.
La validación de hardware físico, continuidad offline y contratación comercial
del complemento no se declaran terminadas en esta entrega.

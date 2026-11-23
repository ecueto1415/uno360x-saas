# Agregar una o varias mesas — 23/11/2026

Agregar mesa reúne creación individual y por cantidad, con zona activa. Una mesa admite nombre personalizado; varias usan nombres numerados desde el primer número sugerido. El número inicial es independiente de la cantidad. Conserva mesas, pedidos y posiciones anteriores. Valida rol administrador, límites 1–200, colisiones y zonas antes de modificar datos; la clave idempotente del servicio protege reintentos. Al terminar muestra la zona elegida y aviso de éxito.

Pruebas: nueve casos de modelo/servidor aprobados, incluyendo permisos, colisiones sin modificación parcial, zonas inválidas y preservación de mesas. Prueba UI en Chrome a 1440, 768 y 390 px: crear tres en Terraza y una VIP, confirmar persistencia y ausencia de desbordamiento horizontal. Capturas de QA en outputs/POS_18_Mesas/agregar-mesas-*.png. No se agregaron mesas ficticias en INCIVI.

Publicado en servicio compartido Restaurante: /srv/uno360x-saas/restaurant-releases/20261123-tables-add/source. Respaldo SQLite: /var/backups/uno360x-restaurant/split-20261123-141618. Salud del servicio verificada; PID de OUTSOLUTECH y listener fiscal de INCIVI sin cambios. No se modifican Odoo ni reservas individuales.

# Capacidad y distribución del plano de mesas

Fecha: 2026-11-22. Cambio común del POS SaaS; no modifica OUTSOLUTECH ni la facturación electrónica de INCIVI.

## Problema observado

Agregar mesa recibe el número de una sola mesa. El caso reportado tenía 7 registros activos, incluido el número 17 con nombre Mesa 09, no 18 mesas. El contador de configuración reflejaba el número mayor. Además, las posiciones automáticas nuevas se calculaban sin considerar las posiciones manuales guardadas, provocando superposición.

## Comportamiento corregido

- Mesas → Configurar cantidad → indicar 18 → Guardar completa los registros faltantes de 01 a 18. Agregar mesa sigue creando una sola mesa. La explicación distingue ambos recorridos.
- Los nombres manuales, números, cuentas y posiciones guardadas se conservan. Las mesas archivadas no se restauran automáticamente. Cada tarjeta muestra también su número para distinguir nombres personalizados.
- Al cambiar el número de una nueva mesa, su nombre sugerido se actualiza si aún no fue personalizado.
- Se asignan espacios libres únicamente a mesas sin coordenadas, teniendo en cuenta las posiciones existentes y las dimensiones de tablet/desktop/celular. El plano puede crecer verticalmente para conservar la ubicación relativa de las mesas manuales.
- Las filas del plano por zona se guardan para mantener la distribución al volver a entrar o guardar. La versión del plano cambia también al configurar cantidad o agregar mesas.
- El plano indica total activo, mesas de la zona y libres. Permite desplazarse por dentro del plano y conserva ese desplazamiento tras las actualizaciones periódicas.
- No se modifica el estado de pedidos, pagos o comprobantes.

## Regreso desde Menú digital

Se reemplaza Volver a Ajustes por Volver al menú. Regresa directamente al listado de productos. Si hay cambios locales sin guardar, ofrece Seguir editando o Volver sin guardar. La salida no altera la configuración del servidor.

## Validación

25 pruebas de modelo aprobadas. Caso reproducido con posiciones reales equivalentes al plano editado: ampliar hasta 18 conserva posiciones y nombres existentes, asigna ubicaciones sin intersección tanto en coordenadas de desktop como de celular, conserva las filas tras guardar y permite abrir Mesa 18.

E2E de capacidad en 1440×1000, 768×1024 y 390×844: configurar 18 desde pantalla; comprobar 18 tarjetas y ausencia de solapamientos; desplazarse y esperar actualización; abrir Mesa 18; probar sugerencia de nombre y conservar nombre personalizado. Pruebas de invitados/cobro, plano/arrastre, permisos, ajustes, archivo/restauración, reasignación y menú público siguen aprobadas. Menú digital regresa al listado y protege cambios pendientes sin guardar.

Capturas locales: outputs/POS_18_Mesas. Prueba ejecutable: pos-pilot/floor-capacity-ui.test.cjs. Las capturas de QA no contienen movimientos reales.

## Publicación

Nueva release del servicio aislado de Restaurante. Respaldo de SQLite antes del reinicio; comprobación de que el proceso de Odoo productivo y el receptor fiscal de INCIVI permanecen iguales. No se reconstruyen reservas ni se actualizan bases Odoo individuales.

La geometría agrega floor.zoneRows y coordenadas en las tablas del POS. Una reversión de código debe conservar el lector de filas para no volver a producir solapamientos; no se debe restaurar automáticamente la base y perder operaciones posteriores.

Release: /srv/uno360x-saas/restaurant-releases/20261122-floor-capacity/source. Respaldo: /var/backups/uno360x-restaurant/split-20261123-020239 (UTC). Verificación en INCIVI: 18 mesas activas, 18 en Salón y 17 libres; regreso desde Menú digital al listado de productos comprobado sin guardar cambios. Captura: outputs/POS_18_Mesas/incivi-18-mesas-publicado.jpg. No se emitieron comprobantes ni pagos en esta verificación.

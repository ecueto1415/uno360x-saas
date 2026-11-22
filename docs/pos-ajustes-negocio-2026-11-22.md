# POS: entrada directa y ajustes independientes

Un POS terminado o anterior sin asistente entra directamente a Caja. El selector
de negocio solo forma parte de la primera configuración, antes de completar el alta.
Se elimina el acceso que volvía a iniciar el asistente de un POS ya terminado.

## Acceso del administrador

**Menú > Ajustes del POS**, visible solo para supervisor (gerente POS verificado
por el gateway). Se reutilizan los paneles, botones, menú y hoja de estilos actuales.

- **Mesas**: activar el salón y cambiar cantidad. Nombres y alta individual en
  Mesas > Administrar mesas. Protege cuentas abiertas al reducir/desactivar mesas.
- **Productos**: acceso al Menú actual para crear o editar el catálogo.
- **Estaciones**: activar/desactivar Cocina y Barra independientemente del negocio.
  No permite desactivar una estación con productos asignados o comandas pendientes.
  Productos nuevos no pueden dirigirse a una estación desactivada.
- **Tipo de negocio**: opción secundaria. Selección > Revisar cambio > confirmación
  indicando origen, destino y conservación de datos > Confirmar cambio o Cancelar.

Cambiar el tipo solo modifica ese metadato: conserva mesas, productos, estaciones,
turnos, pedidos, cobros e inventario. No se reinicia el asistente ni se agregan
ejemplos. No hay un cambio automático de configuración por elegir otro negocio.

## Controles del servidor

`business-change`, `tables-config` y `stations-config` exigen supervisor.
El cambio de negocio requiere `confirmed: true` y el valor anterior vigente para
rechazar una pantalla desactualizada. Se auditan origen, destino, usuario y fecha.
La clave de idempotencia existente evita duplicar la auditoría al reintentar.
Los comandos `setup-*` se rechazan cuando ya se completó el alta, incluso si un
cliente antiguo intenta reutilizarlos. Cancelar la revisión no envía una mutación.

## Pruebas y entrega

- 14 pruebas HTTP/dominio: autorización, confirmación ausente, valor anterior
  desactualizado, reintentos, conservación de datos y bloqueo de atajos al asistente.
- Tablet 768x1024 y celular 390x844: acceso directo, cuatro ajustes separados,
  revisión/cancelación sin cambios, cambio confirmado, conservación de datos,
  recarga sin selector y ausencia de controles de ajustes para un cajero.
- Se repiten los ocho recorridos del alta inicial (cuatro negocios en cada pantalla).
- Evidencias: `outputs/POS_Ajustes_Negocio_20261122`, padre del checkout.

Publicación en el servicio aislado Restaurante, sin actualizar bases Odoo ni
reiniciar el gateway. No cambia style.css, index.html o los permisos asignados.
La versión común se aplica a empresas actuales y futuras del SaaS. OUTSOLUTECH y
el receptor fiscal INCIVI no se modifican ni reinician. No se emiten comprobantes.

Publicado en `20261122-business-settings/source`. Las 14 pruebas HTTP también
pasaron con el runtime del servidor. Backup:
`/var/backups/uno360x-restaurant/split-20261122-161755`.
Verificado en navegador autenticado de INCIVI: al recargar abre Caja directamente;
Menú > Ajustes del POS muestra Mesas, Productos, Estaciones y Tipo de negocio.
La revisión fue solo lectura; todos los estados de empresas siguen idénticos al
backup anterior al despliegue. Hashes servidos coinciden con los archivos probados.

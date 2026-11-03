# Una versión común para todas las empresas SaaS

Cada empresa conserva su base, archivos, usuarios y credenciales. Lo común es el código versionado de UNO360X y el procedimiento de actualización, nunca una copia de los datos de OUTSOLUTECH.

## Publicación de una versión revisada

El coordinador `deployment/publish_release.py`, ejecutado desde un candidato inmutable bajo `/srv/uno360x-saas/releases/*/source`, permite publicar una vez para toda la flota. Primero se validan las pruebas de la versión. Sin `--apply`, el comando solo muestra el plan.

```
sudo python3 /srv/uno360x-saas/releases/VERSION/source/deployment/publish_release.py --release VERSION --apply
```

1. Detecta automáticamente todas las empresas SaaS listas y vigentes; no necesita una lista de clientes escrita a mano. OUTSOLUTECH nativo queda fuera del control y de los destinos de este mecanismo.
2. Pausa el trabajador de altas. Las solicitudes nuevas pueden permanecer en cola y las empresas existentes siguen usando el acceso común durante la preparación de la versión.
3. Actualiza secuencialmente cada empresa, con copia de control, base SQL, archivos y estado previo. Una empresa tiene una pausa breve mientras se actualizan sus vistas. Las demás aplicaciones no se reinician.
4. Conserva el contenedor anterior detenido y registra el resultado por empresa. La actualización interrumpida puede retomarse con el mismo identificador de versión. No se cambia la fecha de la prueba ni el contenido de negocio por copiar otra empresa.
5. Solo después de validar todos los destinos se pausa brevemente el gateway, se publica la metadata de todas las empresas en una transacción y se cambian los enlaces de código común. Se inicia el gateway y el trabajador con la misma versión.
6. Las altas nuevas usan el maestro publicado. Las solicitudes todavía sin recursos se actualizan explícitamente al mismo producto, manteniendo su identificador y selección de módulos.

## Seguimiento y fallos

`/var/lib/uno360x-saas/fleet-rollouts/VERSION/state.json` contiene los destinos, los validados y la fase. Los resultados por empresa y las copias se guardan en directorios privados. `published-release.json` identifica el código común publicado y los enlaces anteriores. El trabajo se serializa con un bloqueo del coordinador; no se ejecutan dos publicaciones a la vez.

Si falla una empresa, el coordinador se detiene sin declarar la versión publicada y conserva las copias y el progreso. El trabajador permanece pausado para revisión. No hay un mecanismo que elimine bases ni una restauración automática que pueda perder transacciones realizadas después de una actualización. Volver a una versión anterior requiere comprobar la compatibilidad de la base; si hubo cambios de esquema o datos se necesita su migración de reversión o una restauración controlada.

Este publicador implementa la migración visual revisada de `uno360x_workspace` y `uno360x_payroll_hr`. Rechaza activar módulos comerciales nuevos o cambiar otros módulos sin un plan de migración explícito. Las futuras funciones se distribuyen por el mismo proceso común, añadiendo sus migraciones revisadas; no mediante modificaciones manuales en cada cliente.

La reconciliación del trabajador mantiene el estado listo durante la comprobación de una empresa ya operativa. Un fallo real sí suspende su estado de disponibilidad; reiniciar el trabajador por sí solo no debe mostrar otra creación al cliente.

## Diseño incluido en esta versión

Contactos y fichas, facturación, proyectos y tareas, directorio y ficha de empleados, presentación del CRM y estilos comunes de las pantallas internas. Los módulos visibles respetan la selección y los permisos de cada empresa. La implementación no copia el motor fiscal, las credenciales ni las personalizaciones de nómina exclusivas de OUTSOLUTECH.

Validación previa: 173 pruebas Python y dos suites Node aprobadas; 8 páginas y 147 accesos de menú comprobados con un propietario ficticio del paquete completo. También se comprobó la navegación móvil y la ficha de empleados sin guardar registros de negocio.

Resultado de publicación: versión `2026-11-03-ui-v1` aplicada a las tres empresas SaaS activas. Comprobación posterior de 21 páginas con respuesta correcta, credenciales y fechas de prueba conservadas. Odoo nativo mantuvo su PID, configuración y privilegios.

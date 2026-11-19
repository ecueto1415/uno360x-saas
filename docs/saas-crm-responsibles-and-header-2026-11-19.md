# CRM: responsables, etapas y cabecera común

Cambios solicitados para todo el SaaS, incluidos INCIVI y los espacios nuevos desde reserva. No se modifica el Odoo nativo de OUTSOLUTECH.

## Comportamiento

- Las tarjetas del tablero muestran Responsable, nombre e inicial. La lista incorpora la columna Responsable; la ficha ya lo mostraba y ahora permite seleccionarlo al crear o editar.
- Una oportunidad nueva se asigna al usuario que la crea, salvo elección explícita de un administrador comercial autorizado. El selector del administrador admite usuarios internos activos con acceso comercial y compañía compatible, además de Sin asignar.
- Un vendedor no recibe el selector de reasignación y un POST manipulado no le permite elegir otro responsable o reasignar una oportunidad ajena a sí mismo. Se mantienen ACL y reglas de registros del usuario real.
- El tablero incluye el acceso directo + Nueva etapa. La gestión sigue restringida al administrador comercial y conserva el acceso a crear flujos independientes con sus propias etapas.
- Al añadir la primera etapa específica a un flujo que utilizaba etapas compartidas, se conserva la visibilidad de estas últimas. La preferencia técnica se limita a compañía y flujo.
- Se corrige el manejo de mensajes de validación: varias rutas usaban una variable local llamada `_`, que ocultaba la función de traducción y fallaba al mostrar errores como un nombre duplicado.
- Al cambiar el responsable, se mantiene expresamente `company_id`. La lógica nativa de CRM podía recalcularlo a vacío al elegir Sin asignar en un equipo compartido, haciendo desaparecer el registro de la vista de la empresa. El cambio ya no altera ese ámbito.

Los iconos nativos de conversaciones y actividades se ocultan únicamente en la cabecera de las pantallas con el shell UNO360X. Se verificaron los elementos reales `.o-mail-DiscussSystray-class` y el botón de reloj de `.o_menu_systray`; no se elimina la funcionalidad de actividades del CRM, mensajes de los registros, soporte UNO360X ni el nombre/engranaje del usuario.

## Validación

`deployment/validate_crm_controls.py` se ejecutó en un shell de INCIVI con transacción revertida. Comprueba asignación, protección frente a otro usuario, desasignar y reasignar conservando la compañía, creación y duplicidad de etapas y rechazo de su gestión por un vendedor. No persisten usuarios, equipos ni oportunidades de esa prueba.

En el navegador de INCIVI se creó la etapa ficticia QA seguimiento 20261119 dentro de Ventas: continuaron visibles Nuevo, Calificado, Propuesta y Ganado. Se creó QA CRM responsable 20261119, se verificó el nombre en tarjeta y ficha y se probó reasignar a gladis y dejar Sin asignar. Se comprobó después la columna de la lista. La oportunidad ficticia, la etapa ficticia y la preferencia técnica que creó esa prueba se retiraron; la oportunidad anterior del usuario se conservó.

También se revisaron lista y formulario Nueva etapa a 390 px, sin campos o botones fuera del ancho. El menú y el perfil se conservaron. En una vista nativa, ambos accesos de cabecera quedaron con ancho y alto cero, mientras el perfil y las actividades del área continuaron presentes. Las capturas del espacio de trabajo son `outputs/UNO360X_CRM_responsables_etapas.jpg`, `outputs/UNO360X_CRM_responsable_movil.jpg` y `outputs/UNO360X_cabecera_sin_iconos_odoo.jpg`.

## Publicación y reversión

El código común cambia el controlador CRM, sus cuatro plantillas, el estilo del tablero y el estilo de la cabecera nativa. No se cambian certificados, secuencias ni flujos de emisión. Las vistas se publican en las dos empresas actuales y se sincroniza la huella común, preservando la huella de recursos asignados y el aislamiento existente. Se reconstruyen las ocho combinaciones limpias y se repone el espacio de desarrollo según la política vigente de una reserva; no se restablece el objetivo antiguo de 50 espacios.

Los recursos incluyen revisión de caché y las plantillas fijan la revisión de la interfaz al instalarse o actualizarse, para evitar que una cuenta nueva recupere el CSS anterior del mismo navegador. El worker y el timer de reposición se restauran al estado anterior tras preparar la versión.

Respaldo de fuente y estados de servicios en `/var/backups/uno360x-crm-20261119`. Respaldo privado de las cuatro vistas por empresa en `/var/lib/uno360x-saas/crm-release-20261119`. Para revertir, restaurar fuente y vistas, volver a alinear las huellas de las empresas y regenerar/reponer reservas de esa versión. No restaurar toda una base ni borrar datos de clientes para revertir una interfaz.

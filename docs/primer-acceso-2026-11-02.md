# Primer acceso optimizado — 2 de noviembre de 2026

El primer login de una cuenta con empresa ya preparada conserva la validación central, de aislamiento y de sesión, pero evita iniciar un proceso completo de Odoo para reescribir un usuario que ya está correctamente configurado.

## Comprobación del usuario

Antes de omitir esa escritura, una consulta de solo lectura comprueba identidad, login, correo, estado activo e interno, empresa principal, lista exacta de empresas permitidas, grupos y todos sus grupos implícitos, ausencia de permisos del sistema, idioma y acción inicial. Respeta el nombre elegido por el cliente. La lista de grupos procede del rol central y del perfil instalado. Si falta una referencia, hay diferencia o falla la comprobación, se mantiene la sincronización ORM anterior. No se comparan ni se cambian contraseñas reales.

La comprobación utiliza una carga JSON codificada para evitar interpolar correos u otros textos del usuario en SQL. No guarda un resultado de autorización entre sesiones. Se verificó en la empresa ficticia y, sin escribir registros, en el propietario del tenant Base existente.

## Comprobaciones de infraestructura

Para una empresa lista, una única llamada de inspección obtiene los datos de sus tres contenedores. Se mantienen las verificaciones de propietario, imagen, red y puertos de cada recurso. El resultado solo se usa dentro de esa entrada; no se comparte como caché entre solicitudes. Los módulos instalados y la identidad, tareas, correo y permisos del rol PostgreSQL se verifican juntos en una consulta nueva. La disponibilidad HTTP se comprueba por el proxy propio ligado al tenant, evitando otro proceso de prueba. Los recursos ausentes o detenidos conservan el recorrido de creación/arranque y validación.

La respuesta de login incluye el correo verificado de esa misma cuenta junto al CSRF existente, para evitar pedir inmediatamente otra copia de la sesión. Solo se consulta el borrador de registro cuando la cuenta aún no tiene empresa. Se conserva la selección de módulos para las altas nuevas y la navegación Atrás al inicio.

## Medidas publicadas con empresa ficticia

Línea base y primera fase de la optimización:
{
  "before": {
    "secure_entry_seconds": 13.227,
    "summary_loaded_seconds": 13.76
  },
  "after_first_entry": {
    "secure_entry_seconds": 4.149,
    "summary_loaded_seconds": 4.553
  },
  "after_same_session_reentry": {
    "secure_entry_seconds": 0.324,
    "summary_loaded_seconds": 0.757
  }
}

Última comparación, antes y después de agrupar las comprobaciones de contenedores:
{
  "before": {
    "secure_entry_seconds": 3.386,
    "summary_loaded_seconds": 3.757
  },
  "after_first_entry": {
    "secure_entry_seconds": 1.412,
    "summary_loaded_seconds": 1.681
  },
  "after_same_session_reentry": {
    "secure_entry_seconds": 0.147,
    "summary_loaded_seconds": 0.538
  }
}

El recorrido publicado de apertura segura hasta el resumen pasó de la línea base de 13,760 s a 1,681 s. Una medición de navegador desde la solicitud de login con contraseña hasta DOMContentLoaded del resumen dio 2,893 s. La reentrada con sesión vigente hasta el resumen tomó 0,538 s en la prueba HTTP. No son garantías de tiempo: varían con la red, carga y volumen de datos. Un usuario nuevo, permisos modificados, una empresa que necesite reparación o un servidor que arranque pueden requerir el recorrido completo.

El aviso «Entrando a tu empresa» informa mientras se completan esas operaciones; no contiene una espera programada. Ocultarlo no elimina el trabajo de apertura. Los pasos de creación siguen ocultos para una empresa lista.

## Verificación y alcance

123 pruebas Python y las dos suites Node aprobadas sobre la VM. Se verificaron el rechazo de identidad ajena, deriva de grupos/correo, grupos faltantes, privilegios del sistema, recursos ajenos o publicados, y el respaldo de sincronización completa. Se probó un login nuevo y la llegada al resumen en el sitio HTTPS real. La cuenta ficticia se revoca y se detiene al finalizar.

Solo se recargó el piloto SaaS. No se migraron addons ni bases, ni se reinició el Odoo nativo de OUTSOLUTECH. Los límites de recursos, credenciales de correo/Jenifer/DGII y fechas de la prueba real permanecen iguales.

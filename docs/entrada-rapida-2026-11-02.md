# Entrada a una empresa existente — 2 de noviembre de 2026

Una empresa ya preparada no muestra los cuatro pasos de registro al entrar. Estos pasos siguen disponibles durante la creación y la preparación inicial.

El gateway puede reutilizar la sesión interna de la misma cuenta, misma sesión central, empresa, rol y preparación. Primero localiza la empresa a partir del handoff ligado a la sesión; nunca elige una base por un parámetro del navegador. Comprueba que el snapshot no haya cambiado y consulta la sesión interna para verificar su usuario. Consume un handoff nuevo de un solo uso y vuelve a validar cuenta, membresía, prueba y release. Las solicitudes posteriores conservan la comprobación de autorización antes y después de responder.

Si la sesión interna no sirve, cambia el rol o la versión, o se inicia una sesión central nueva, se utiliza el acceso completo con validación y sincronización. Los bloqueos del opener se comparten al reutilizarlo para evitar carreras con solicitudes anteriores. No se guardan contraseñas ni cookies internas en el navegador.

## Medición publicada con empresa ficticia

{
  "before": {
    "secure_entry_seconds": 10.224,
    "summary_loaded_seconds": 10.468
  },
  "after_first_entry": {
    "secure_entry_seconds": 10.608,
    "summary_loaded_seconds": 11.011
  },
  "after_same_session_reentry": {
    "secure_entry_seconds": 0.168,
    "summary_loaded_seconds": 0.596
  }
}

La comparación muestra una reentrada hasta el resumen de 0,596 segundos frente a 10,468 segundos del recorrido completo medido. El primer acceso después del reinicio tomó 11,011 segundos: esta mejora acelera la reentrada con sesión vigente, no elimina el trabajo inicial ni acelera la creación de una base. En el navegador, desde pulsar «Iniciar sesión» hasta llegar al resumen, se observaron 2,124 segundos. Son observaciones de esta prueba, no una garantía para toda carga o conexión.

Validación: 118 pruebas Python y las dos suites Node aprobadas en la VM; escenarios de ticket reutilizado, rol cambiado, sesión distinta, backend vencido, release anterior y la misma cuenta entrando a dos empresas. Comprobación visual publicada del acceso sin pasos de creación, llegada al resumen, Atrás al inicio y reentrada.

Solo se reinició el piloto SaaS para cargar el código Python. No se migraron addons ni bases, ni se reinició el Odoo nativo de OUTSOLUTECH. La empresa ficticia se desactiva y sus sesiones se revocan al finalizar.

Actualización posterior: el primer login también se optimizó. Véase primer-acceso-2026-11-02.md para la implementación y las mediciones actuales.

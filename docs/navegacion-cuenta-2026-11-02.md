# Navegación de acceso — 2 de noviembre de 2026

El menú público y el portal de cuenta conservan siempre «Iniciar sesión». Ese enlace no cierra sesiones: el portal reconoce la cuenta y abre directamente su empresa, o muestra el formulario cuando no hay sesión. «Cerrar sesión» se conserva dentro del espacio de trabajo.

Antes de enviar la entrada segura por POST, la página intermediaria se sustituye en el historial por una vuelta al inicio. Al volver desde la primera pantalla del espacio, tanto la restauración de página como el historial de la SPA llevan a https://uno360x.com/, sin relanzar el espacio ni quedarse en «Entrando a tu empresa». La navegación interna normal entre módulos conserva su historial. Las respuestas de apertura que llegan después de cambiar de pantalla se descartan.

Crear cuenta con una sesión existente muestra «Esta cuenta ya existe», permite entrar a la empresa o usar otro correo. El mismo aviso se utiliza cuando el servidor reconoce un correo ya registrado. Se conservan el control de una prueba por cuenta y la prohibición de recrear la empresa existente.

Validación: 114 pruebas Python y las suites Node del JavaScript real en la VM. Comprobación publicada con cuenta ficticia: login → resumen → Atrás → inicio → Iniciar sesión → resumen sin nuevas credenciales; creación de cuenta existente sin crear otra empresa. No se modificó el Odoo nativo ni las credenciales reales. La cuenta ficticia se desactiva al terminar la comprobación.

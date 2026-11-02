# Mensajes del login — 2 de noviembre de 2026

El rechazo de credenciales muestra «Contraseña incorrecta.» dentro del formulario, debajo de la contraseña. El mensaje es texto sin franja roja; utiliza role=alert y la referencia aria-describedby del campo. Los demás fallos, como red o límite de intentos, conservan su explicación y no se presentan como una contraseña incorrecta.

El aviso global no se utiliza en el formulario de login. Se oculta la lista vacía de pasos de registro, que antes reservaba altura aunque no tuviera contenido. En la comprobación publicada, esa lista mide cero píxeles y el login comienza 42 píxeles después del menú. Los pasos con contenido del alta nueva conservan su diseño.

Validación: 123 pruebas Python y las suites Node aprobadas en la VM, incluida la comprobación del mensaje de credenciales, su ubicación y el tratamiento separado del límite de intentos. Se envió un login inválido con un correo ficticio sin crear cuenta ni iniciar sesión. Se comprobó el resultado visual en la web publicada y la ausencia de desbordamiento en móvil; se retiró la emulación al finalizar.

Solo cambiaron el JavaScript y CSS del portal SaaS y su prueba. No se modificaron datos de clientes, credenciales ni el Odoo nativo de OUTSOLUTECH. No fue necesario reiniciar servicios.

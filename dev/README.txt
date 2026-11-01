LABORATORIO LOCAL - WSL / PODMAN

Ejecutar start.py desde Linux WSL como root, con las imágenes oficiales de
Odoo 18 y PostgreSQL 16 previamente descargadas. No ejecutar en la VM operativa.
El script no instala Podman, modifica DNS ni usa servicios de OUTSOLUTECH.

Recursos exclusivos: uno360x-dev-*; datos en volúmenes Podman separados.
Configuración y claves de desarrollo: /var/lib/uno360x-saas-dev, fuera del repo.
Contenedores sin puertos publicados. Un relay TCP local expone Odoo únicamente
en 127.0.0.1:18069; permite acceso desde el host sin abrir salida a Internet.
Red interna sin salida; tareas cron desactivadas; instalación sin demostración.
El usuario operativo PostgreSQL no tiene privilegios para crear bases o roles.
Odoo upstream 18.0: sirve para validar el módulo, no prueba compatibilidad
completa con la instalación personalizada actual, identificada como 18.2.

Parar sin borrar datos:
  podman stop uno360x-dev-app uno360x-dev-db

El relay sin destino activo no permite acceso; su PID está en el directorio
de estado Linux. No usar este relay como proxy de un entorno comercial.

Reiniciar: volver a ejecutar start.py.
No existe borrado automático ni reinicio automático tras arrancar Windows.
No utilizar las credenciales predeterminadas del laboratorio con acceso público.
La creación de usuarios reales, correo, IA y emisión fiscal están fuera de alcance.

Dos clientes ficticios independientes:
  python3 dev/tenants.py
Ejecutar únicamente como root dentro del WSL existente. Reutiliza imágenes
fijadas en images.json. Recursos uno360x-lab-empresa-alfa-* y
uno360x-lab-empresa-beta-*, redes internas sin puertos publicados.
Datos y claves: /var/lib/uno360x-saas-dev/tenants (root-only).
Comprueba login HTTP interno, identidades, cron desactivado, roles limitados,
ausencia de rol/base del otro cliente, claves distintas y bloqueo de red cruzado.
Reejecutar reusa recursos; no borra datos. Una instalación fallida requiere
revisión explícita. No imprime secretos ni copia datos de producción.
Estas instancias no publican subdominios y no implementan autoservicio todavía.

Base estándar de negocio, solo después de crear los dos clientes:
  python3 dev/install_business_base.py
Instala/actualiza uno360x_business_base y ejecuta tres pruebas ORM por cliente.
Detiene exclusivamente su aplicación ficticia mientras actualiza. Mantiene
credenciales y datos locales; reinicia sin cron activo. No afecta al laboratorio
base ni a producción. Rechaza ejecutar fuera de WSL.
Verificación posterior de solo lectura:
  python3 dev/verify_business_base.py
  python3 dev/verify_tenants.py
Logs de pruebas en directorio Linux protegido de cada cliente.
El paquete aún no contiene el conector de emisión e-CF ni las personalizaciones
de OUTSOLUTECH. No usarlo como producto comercial terminado.

Catálogo completo de paquetes portátiles para QA:
  python3 dev/install_product.py
  python3 dev/verify_product.py
  python3 dev/check_product_runtime.py
La primera orden instala/actualiza los seis paquetes y corre 18 pruebas ORM
en cada empresa ficticia. verify_product.py consulta estado y logs sin cambios.
check_product_runtime.py autentica al administrador ficticio por API local,
comprueba recursos y genera un PDF real con registros temporales revertidos.
No imprime contraseñas; lee únicamente claves del laboratorio en memoria.
La generación de recursos puede escribir cachés de activos en el laboratorio.
No se ejecuta ninguna orden de este flujo en la VM operativa.

Identidad y acceso central de laboratorio:
  python3 -m control.identity_demo
El demo crea cuentas y dos reservas ficticias en una carpeta temporal. Buzón
en memoria, sin mensajes reales, contraseñas ni tokens impresos. No crea Odoo.
API opcional, desde WSL root:
  python3 dev/start_identity.py
Solo 127.0.0.1:18072. Estado en /var/lib/uno360x-saas-dev/control protegido.
Incluye la UI aprobada de prueba gratis; sin SMTP real ni gateway web Odoo.
Los enlaces se guardan en control/mailbox, bajo el estado privado Linux.
Los endpoints privados
requieren cookie de sesión y token CSRF. El servidor no se publica en Internet.

Punto 4: automatic_signup_demo.py, verify_automatic.py, run_preparation_worker.py,
http_signup_smoke.py y recovery_rehearsal.py. Solo WSL root, recursos nuevos
uno360x-auto-UUID, sin puertos publicados. La última orden detiene una app
ficticia para ensayar recuperación. No ejecutar en la VM operativa.

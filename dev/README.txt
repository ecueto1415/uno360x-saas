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

# Tiempo de preparación y capacidad — 2026-11-03

Medición de referencia a las 05:51, hora de República Dominicana: 44,580 segundos para preparar una empresa ficticia con los tres módulos opcionales y 46,337 segundos hasta su primera entrada autenticada. Se usó la plantilla verificada de la versión publicada. La medición excluye la espera de capacidad, completar formularios y confirmar el correo. Los recursos ficticios se retiraron al terminar.

Desglose: base nueva 7,502 s, restauración 16,115 s, identidad y administrador 11,344 s, validación y arranque 9,348 s, primera entrada 1,756 s. La identidad se configuraba en un shell de Odoo separado de la aplicación, duplicando la carga del registro.

La nueva ruta para una instancia vacía restaurada usa un proceso que configura su identidad y propietario y después sirve las solicitudes con el mismo registro. No introduce una API pública de configuración. El archivo inicial es privado por empresa y se monta solo para lectura, igual que su configuración. Una marca persistente impide volver a aplicar los valores iniciales al reiniciar. Las empresas ya creadas y las instalaciones sin plantilla conservan el proceso de reconciliación existente.

La preparación usa CPU temporal de 0,75 para arrancar PostgreSQL, 1 para restaurar y 1 para el primer arranque de Odoo. Al terminar se devuelve PostgreSQL a 0,25 y la aplicación a 0,5. El límite total del SaaS permanece en 150% de CPU y 3 GiB. No se cambia el servicio nativo ni sus credenciales.

Se corrigió una discrepancia persistente: `50-uno360x-limits.conf` seguía declarando 2 GiB y 100% de CPU, y recuperaba esos valores al recargar systemd pese a la ampliación aplicada con `set-property`. `deployment/pilot-user-slice.conf` registra la configuración coherente de esta VM. Se conservó una copia privada del archivo anterior. Esta referencia corresponde a esta VM; no define la capacidad comercial de otros servidores.

Las tres empresas activas ya reservan la capacidad admitida por la política actual. Una cuarta alta pública sigue esperando en cola; una prueba técnica aislada no equivale a admitir permanentemente otro cliente. Ampliar el servidor y asignar presupuesto al SaaS requiere considerar CPU, memoria, usuarios simultáneos, almacenamiento y margen operativo.


## Resultados de la optimización

Las dos primeras pruebas del paquete completo dieron 22,209 y 23,041 segundos hasta la primera entrada; Base Empresarial dio 22,966 segundos. Esas pruebas limitaban las aplicaciones pero no el coordinador igual que el trabajador real.

La verificación con el límite anterior del coordinador (20% de CPU) dio 34,838 segundos de preparación y 36,878 segundos hasta entrar. Para resolver esa espera, `worker-preparation-budget.conf` coloca el trabajador dentro de `user-996.slice` y le permite hasta 100% de CPU con peso 20. El presupuesto conjunto de aplicaciones, bases y trabajador sigue limitado a 150% y 3 GiB. La prioridad del coordinador no permite saltarse ese techo compartido.

Prueba con esa configuración conjunta, a las 06:18 hora dominicana: **25,060 segundos de preparación y 26,619 segundos hasta entrar**. Se usaron los mismos 192 MiB de memoria para el coordinador y los mismos límites por aplicación y base que el trabajador publicado. La medición anterior de 46,337 segundos y esta medición son pruebas técnicas; ninguna incluye la cola, el correo ni el tiempo que tarda el usuario en llenar los formularios.

También se comprobó un reinicio de una instancia ficticia después de cambiar el nombre de su empresa. El cambio y el hash de la credencial técnica se conservaron; los límites efectivos regresaron a 0,25 CPU para PostgreSQL y 0,5 para Odoo. Los recursos ficticios se eliminaron después de las pruebas.

La reconciliación de una identidad ya configurada ahora es de lectura cuando coincide la empresa, su acceso técnico y la política de cron. La inicialización no vuelve a imponer el perfil original sobre una empresa existente.

Publicación `2026-11-03-fast-runtime-v1` completada. Pasaron 179 pruebas Python y las dos suites Node; se verificaron después las 21 páginas de las tres empresas activas, sus credenciales y las fechas de prueba. No se reinició Odoo nativo ni se modificaron sus privilegios.

# PostgreSQL compartido y reservas SaaS

Versión 2026-11-03-reserve15-v1. PostgreSQL 16 compartido exclusivamente por el SaaS: cada empresa conserva base, usuario, contraseña, archivos y credenciales de acceso independientes. El PostgreSQL y Odoo nativos de OUTSOLUTECH permanecen separados.

## Reservas y reposición

Se mantienen 15 espacios limpios sin procesos Odoo activos. Al quedar 5, el temporizador inicia la reposición hasta volver a 15, contabilizando consumos concurrentes. El temporizador comprueba aproximadamente cada minuto. Las asignaciones son atómicas e idempotentes; un espacio consumido nunca vuelve al inventario disponible. La asignación puede aprovechar una reserva recién construida sin esperar al lote completo. Se preparan las ocho combinaciones de módulos; si falta una combinación concreta se construye desde su plantilla, por lo que el tiempo puede variar.

Distribución objetivo: Base 4, las tres opciones 4, RR. HH. 2, IA 1, Proyectos 1 y cada una de las tres combinaciones de dos opciones 1. Las plantillas proceden de bases sintéticas, sin datos empresariales. Las futuras publicaciones preparan plantillas compatibles antes de sustituir reservas de versiones anteriores.

## Evidencia y rendimiento

187 pruebas Python y dos suites Node aprobadas. Prueba real con el presupuesto del worker: 12,690 segundos de preparación y 15,055 segundos hasta consumir el acceso y abrir la primera página. No incluye formulario, confirmación del correo, espera en cola ni retrasos de sondeo. Es una medición de alta nueva, no de inicio de sesión habitual ni una garantía bajo carga.

Reposición automática real: 5 reservas a las 12:05:10 UTC; 15 a las 12:06:16 UTC: 66 segundos para construir las diez. Puede añadirse aproximadamente un minuto hasta detectar el umbral. Los cinco consumos ficticios fueron eliminados; inventario final: 15 listas. La reposición no requiere esperar al lote para asignar espacios disponibles.

Las tres empresas SaaS existentes se migraron conservando credenciales, archivos, fechas de prueba e identidad. Se comprobaron 21 páginas. Los contenedores PostgreSQL anteriores quedaron detenidos como respaldo de reversión. Odoo nativo conservó PID 2195, cero reinicios, configuración y 67 grupos del administrador.

## Operación y límites

Servicios: uno360x-shared-postgres.service, uno360x-reserve.service y uno360x-reserve.timer. Inventario privado: /var/lib/uno360x-saas/shared-postgres/inventory.sqlite3. Configuración: /etc/uno360x-saas/shared-postgres.json. Copias de migración: /var/lib/uno360x-saas/shared-postgres/migrations. La migración pausa únicamente la empresa seleccionada, valida copia y credenciales y revierte ante fallos; se ensayaron éxito y fallo con una empresa ficticia.

El servidor PostgreSQL no publica puertos. Redes privadas, SCRAM y HBA restringen cada rol a su propia base. Odoo necesita además CONNECT al postgres técnico vacío para notificaciones; los roles no pueden crear objetos allí ni leer datos de otras empresas. Se comprobaron rechazo de acceso cruzado y de escalada de privilegios.

El conjunto SaaS tiene límite persistente de 3584 MiB y 150 % CPU. PostgreSQL compartido tiene 512 MiB; el worker 192 MiB y 100 % CPU dentro del límite total. Las reservas apagadas no equivalen a capacidad para 15 empresas activas. La admisión sigue comprobando margen disponible. PostgreSQL compartido es un dominio común de fallo; alta disponibilidad, carga comercial, cuotas exigibles y respaldos externos continúan siendo asuntos separados. No se afirma que esta versión implemente el motor legal de nómina.

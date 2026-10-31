UNO360X SaaS - desarrollo aislado - consolidación 31/10/2026

Este directorio no está desplegado ni conectado a producción.
El registro local permite reservar clientes ficticios y resolver sus dominios.
No crea DNS, bases PostgreSQL, certificados HTTPS, facturas ni usuarios reales.
No contiene ni importa credenciales de OUTSOLUTECH.

Componentes:
- control/registry.py: registro SQLite, identificador inmutable, reserva única,
  resolución exacta de dominio y referencias de recursos independientes.
- addons/uno360x_tenant_config: módulo Odoo inicial con identidad por instancia
  y estado fiscal por empresa. No permite almacenar material de certificados.
- tests: aislamiento lógico y reservas; no requiere servicios externos.

Validación local: python -m unittest discover -s tests -v
El módulo Odoo está instalado en el laboratorio; esto no valida todas las
personalizaciones ni el funcionamiento de los módulos comerciales.
El control usa SQLite únicamente para el prototipo local; no es un panel público.
No exponerlo a Internet. El aprovisionador real con privilegios queda por implementar.

Hito 0.2 - simulación local (31/10/2026):
- control/provisioning.py: configuración reproducible desde un cliente registrado,
  versión de producto, módulos deseados y referencias de recursos independientes.
- SimulatedProvisioner: diario SQLite de cinco pasos simulados; reintentos sin
  duplicación, recuperación de fallos y rechazo de cambios de configuración.
- No se instalan módulos Odoo ni se habilita acceso. Estado simulated significa
  únicamente ensayo completado; no significa cliente aprovisionado.
- Prueba demostrativa con dos empresas ficticias y fallo recuperable:
    python -m control.demo
  Usa archivos temporales que se retiran al terminar. No requiere WSL ni VM.
- Validación: nueve pruebas unitarias (registro y simulación). Las pruebas ORM
  anteriores no se repitieron en este hito, que no modifica el módulo Odoo.

Hito 0.3 - dos clientes ficticios:
- dev/tenants.py crea Empresa Alfa y Empresa Beta dentro de WSL, con instancias,
  PostgreSQL, roles, credenciales, redes y volúmenes separados.
- Ese hito instaló solo Odoo base e identidad. El punto 2 incorpora ahora
  los seis paquetes descritos debajo mediante instalador independiente.
- dev/verify_tenants.py comprueba las instancias existentes en solo lectura:
    python3 dev/verify_tenants.py
  Ejecutar dentro del WSL de laboratorio como root. No crea ni reinicia recursos.
- Sin DNS ni puertos publicados; claves fuera del repositorio.

La página pública de planes se publicó mediante vistas Odoo. Las copias de
inicio y planes están en website_snapshots como referencia versionada;
no son un módulo instalable. No existe despliegue automático a VM.
No existen registro público, membresías, pago ni alta conectada a la web.
Ver docs/decisiones_acceso_2026-10-31.txt y el inventario de consolidación.

No copiar esta carpeta a la VM operativa ni usar datos de clientes reales.
El registro, membresías y autoservicio se construirán después sobre el
catálogo y los paquetes de laboratorio, con sus límites explícitos.

Punto 2 - Base estándar de laboratorio:
- addons/uno360x_business_base agrupa ventas, compras, inventario, contabilidad,
  contactos y localización dominicana upstream. Sin hooks ni datos operativos.
- product/business_base.json declara el alcance comercial y lo aún pendiente.
- dev/install_business_base.py instala/actualiza y prueba solo Alfa y Beta en
  WSL. Detiene únicamente la app del cliente ficticio durante la instalación;
  desactiva cron antes de reiniciarla. Nunca ejecutar en producción.
- dev/verify_business_base.py verifica instalación y resultados en solo lectura.
- Tres pruebas ORM de negocio por cliente: venta/factura/cobro,
  compra/recepción/factura y bloqueo fiscal. No certifican emisión DGII.
- docs/inventario_producto_2026-10-31.txt identifica personalizaciones que
  faltan por revisar y empaquetar. No hay paridad total con producción 18.2.
OUTSOLUTECH conserva acceso a todos sus módulos; no aplicarle límites SaaS.

Punto 2 - paquetes portátiles:
- product/catalog.json y control/catalog.py: base y tres opciones combinables,
  con versiones y huellas del contenido. Las ocho combinaciones se prueban.
- uno360x_quote_ui: diseño existente adaptado a la API de campos 18.0,
  renovación y versiones PDF. No modifica la vista operativa de OUTSOLUTECH.
- uno360x_ecf_core: preparación y comprobación local; transmisión bloqueada.
- uno360x_payroll_hr: RRHH estándar y aritmética de jornadas/cortes. No es
  aún un motor legal completo de nómina; completar en el punto 9.
- uno360x_jenifer_core: consultas deterministas con permisos. Sin correo,
  hooks de producción, claves ni conexión IA externa. Completar en punto 9.
- uno360x_projects_services: tareas, horas, costos de horas y dependencias
  estándar de gastos/compras; rentabilidad propia pendiente de punto 9.
- dev/install_product.py: instala/actualiza los seis paquetes para QA en Alfa
  y Beta. Exige al menos 18 pruebas y cero fallos. Solo WSL de laboratorio.
- dev/verify_product.py: lectura del estado, logs y ausencia de datos de prueba.
- dev/check_product_runtime.py: API local, formulario, recursos y PDF real.
Documentación de alcance: docs/producto_paquetes_y_limites.txt.
Inventario técnico sin código/valores: product/legacy_inventory.json.
Los paquetes preparados no equivalen a un producto comercial terminado.

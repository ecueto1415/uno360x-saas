UNO360X SaaS - desarrollo aislado v0.1

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
El módulo Odoo requiere instalación y pruebas en Odoo aislado antes de usarse.
El control usa SQLite únicamente para el prototipo local; no es un panel público.
No exponerlo a Internet. El aprovisionador con privilegios queda por implementar.

No copiar esta carpeta a la VM operativa ni usar datos de clientes reales.
Siguiente hito: Odoo aislado, migración reproducible de personalizaciones y
adaptador simulado de aprovisionamiento, antes de conectar infraestructura real.

# Revisión de incidencias 606 en copia de laboratorio

Se revisaron las 20 incidencias de cuatro facturas de noviembre. Operaciones exclusivamente en Outsolutech_prueba del PostgreSQL privado en puerto 18192; cada script verificó nombre y puerto. No se instalaron módulos ni corrigieron datos en producción. Sin envíos a DGII, movimientos de pago nuevos ni aprobación fiscal automática.

Correcciones respaldadas por la copia:

- Impuesto 43: compra, porcentaje 18%, país DO, grupo ITBIS y cuenta de reparto 11080101. Se registró su clasificación 606 como ITBIS facturado. Resuelve las cuatro incidencias de impuesto y recupera RD$8,070.27 ya contabilizados.
- Contacto 893: su nombre ya identificaba el RNC de ASELEC, coincidente con el contacto empresarial 886. Se verificó el dígito de control y se completó el RNC sin fusionar contactos ni cambiar el proveedor de las facturas. Resuelve dos incidencias.
- Línea 3153 de factura 1089: descripción explícita de servicio técnico, mantenimiento e instalación por RD$4,000. Se clasificó esa línea como servicio para 606, manteniendo RD$6,750 de bienes. No se cambió el producto global ni sus precios.

Se conservaron nombres, referencias, fechas, estados, importes y NCF de las cuatro facturas. No se marcaron como revisadas. Respaldo previo: /var/lib/uno360x-606-lab/correcciones-verificadas-20261119.json. Resultado: revision-corregida.json en la misma carpeta privada.

Quedan 14 incidencias: cuatro NCF, cuatro tipos de gasto, cuatro revisiones fiscales, un RNC de proveedor y un detalle de pago. Las referencias en notas corresponden a cotizaciones; no se utilizaron como comprobantes fiscales. No se asignó un tipo de gasto por defecto a partir del nombre de la cuenta contable.

El pago de la factura 1089 figura conciliado por RD$12,685 el 06/11/2026, asiento PBNK1/2026/00185, pago 610. El método registrado es genérico Manual Payment; falta evidencia para completar forma fiscal y posibles retenciones. La vista muestra Por confirmar en lugar de Compra a crédito mientras subsista esa incidencia. No se registra un nuevo pago ni se supone que las retenciones sean cero.

Contabilidad debe aportar los cuatro comprobantes originales con NCF y fechas, la clasificación/destino de las compras, tratamiento del ITBIS, razón social y RNC de Manuel Corripio y documentación del pago/retenciones de REFRIRO. Debe revisar expresamente los cuatro documentos. La descarga continúa bloqueada. El cotejo contable y prevalidador oficial siguen pendientes.

Se actualizó la vista local de consulta y el CSV de pendientes. Totales contables de la copia: base RD$44,834.79, ITBIS RD$8,070.27, total RD$52,905.06; retenciones y tratamiento fiscal aún por confirmar.

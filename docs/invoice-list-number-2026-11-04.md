# Número de comprobante en la lista SaaS — 04/11/2026

Se publica Comprobante como columna principal en las listas de facturas y Referencia interna como columna opcional oculta. El módulo uno360x_quote_ui18.0.1.2.1 aporta un campo calculado sin escritura fiscal ni modificación del número contable.

La emisión productiva del SaaS continúa sin habilitarse. El hook privado _ux_accepted_ecf_number devuelve False hasta que un adaptador fiscal validado lo implemente (también deberá extender la búsqueda). Por tanto, hoy el SaaS conserva como alternativa el número interno; no se inventan e-NCF, no se reutilizan el certificado ni las secuencias de OUTSOLUTECH y no se presenta una reserva como aceptación fiscal. Este cambio prepara la presentación común; no completa la integración tributaria pendiente.

Se clonó la versión SaaS publicada menu14-20261104T115527Z y solo se sustituyeron cuatro archivos de uno360x_quote_ui. No se publicó el resto de cambios fiscales aún no habilitados del repositorio. Candidato: /srv/uno360x-saas/releases/invoice-number-20261104T182121Z/source. Las 197 pruebas de control pasaron; se reconstruyeron ocho combinaciones de plantillas limpias y sus semillas SQL. El publicador común actualizó tres clientes y cambió master-current, worker-current y https-pilot-current a la nueva versión. Release2026-11-04-invoice-number publicado18:42:31UTC; su guard verificó que Odoo nativo permaneciera intacto durante esa publicación.

Comprobación posterior en los tres clientes: módulo18.0.1.2.1 instalado, columna principal presente, referencia interna opcional y cálculo alternativo correcto. Los cuatro archivos publicados coinciden por SHA256 con el repositorio. Las reservas nuevas se reponen mediante el mecanismo automático existente. La actualización nativa de OUTSOLUTECH se realizó separadamente después de finalizar el publicador SaaS.

Comprobación final de inventario:15 reservas ready de los fingerprints de esta versión.

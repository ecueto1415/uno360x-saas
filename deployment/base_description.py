"""Reversible CRM and free-trial copy on the existing Base Empresarial card."""
OLD='<ul><li>Contactos y cotizaciones</li><li>Ventas y punto de venta (POS)</li><li>Compras e inventario</li><li>Cobros, pagos y reportes</li></ul>'
NEW='<ul><li>CRM: contactos y oportunidades</li><li>Cotizaciones y ventas</li><li>Punto de venta (POS)</li><li>Compras e inventario</li><li>Cobros, pagos y reportes</li></ul><p class="p-muted"><strong>15 días gratis, sin tarjeta de crédito.</strong></p><a class="u-btn" href="/prueba-saas">Probar gratis por 15 días</a><p class="p-muted">Vista previa del recorrido con datos ficticios. Todavía no crea una cuenta real.</p>'
def update(original):
    assert original.count(OLD)==1, 'Unexpected plans card; do not replace blindly'
    changed=original.replace(OLD,NEW)
    assert changed.replace(NEW,OLD)==original
    return changed

"""Text-only, reversible update of the existing public Base Empresarial card."""
OLD='<ul><li>Ventas y compras</li><li>Inventario</li><li>Cobros, pagos y reportes</li></ul>'
NEW='<ul><li>Contactos y cotizaciones</li><li>Ventas y punto de venta (POS)</li><li>Compras e inventario</li><li>Cobros, pagos y reportes</li></ul>'
def update(original):
    assert original.count(OLD)==1, 'Unexpected plans card; do not replace blindly'
    changed=original.replace(OLD,NEW)
    assert changed.replace(NEW,OLD)==original
    return changed

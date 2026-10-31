"""Offline checks only: no network, sequence allocation, or Odoo writes."""
from .builder import build_invoice, validate_signed
from .crypto import load_identity, sign_xml


def check_invoice(data, *, identity=None):
    """Use a disposable sequence solely in memory; never return the sample XML.

    Without identity only invoice structure is checked. A successful result is
    not DGII acceptance. No private material is included in the result.
    """
    checks = []
    preliminary = None
    cert_ok = False
    try:
        if not isinstance(data, dict):
            raise ValueError('El caso debe contener un objeto de datos de factura.')
        preliminary = build_invoice(data, 'E' + str(data.get('document_type', '31')) + '0000000001')
        checks.append({'check': 'invoice', 'status': 'ok', 'message': 'Datos, importes y estructura preliminar correctos.'})
    except (ValueError, TypeError, KeyError, AttributeError):
        # Schema errors can echo invoice contents; keep the batch report minimal.
        checks.append({'check': 'invoice', 'status': 'error', 'message': 'Revise datos obligatorios, tipo, impuestos, descuentos y totales del caso.'})
    if identity is None:
        checks.append({'check': 'certificate', 'status': 'pending', 'message': 'Certificado y firma no comprobados.'})
    else:
        try:
            p12, password = identity
            load_identity(p12, password)
            cert_ok = True
            checks.append({'check': 'certificate', 'status': 'ok', 'message': 'Certificado vigente, uso de firma y clave comprobados localmente.'})
        except (ValueError, TypeError):
            checks.append({'check': 'certificate', 'status': 'error', 'message': 'No se pudo validar el certificado privado o su vigencia.'})
    if preliminary is not None and cert_ok:
        try:
            signed = sign_xml(preliminary, p12, password)
            validate_signed(signed)
            checks.append({'check': 'signature_schema', 'status': 'ok', 'message': 'Firma y esquema del XML temporal comprobados.'})
        except (ValueError, TypeError):
            checks.append({'check': 'signature_schema', 'status': 'error', 'message': 'No se pudo comprobar la firma o el esquema del XML temporal.'})
    else:
        checks.append({'check': 'signature_schema', 'status': 'pending', 'message': 'Requiere datos y certificado correctos.'})
    errors = any(row['status'] == 'error' for row in checks)
    ready = not errors and all(row['status'] == 'ok' for row in checks)
    return {'status': 'error' if errors else ('ready_local' if ready else 'partial'),
            'checks': checks, 'sent': False, 'sequence_reserved': False,
            'dgii_acceptance': False}

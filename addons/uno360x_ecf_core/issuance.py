from datetime import date
import re

from .builder import build_invoice, rnc, validate_signed
from .crypto import load_identity, sign_xml, verify_xml
from .dgii_client import Client
from cryptography.hazmat.primitives import hashes


def authorization_number(kind, number, start, end, expires, issued):
    """Format an authorized number; the caller must allocate it transactionally."""
    if not re.fullmatch(r'[0-9]{2}', kind):
        raise ValueError('Tipo de comprobante inválido.')
    if not (1 <= start <= number <= end <= 9_999_999_999):
        raise ValueError('No quedan secuencias autorizadas para este tipo.')
    if not isinstance(expires, date) or not isinstance(issued, date) or expires < issued:
        raise ValueError('El rango autorizado está vencido para esta factura.')
    return f'E{kind}{number:010d}'


def prepare_signed(payload, encf, company_rnc, fingerprint, p12, password):
    """The secret store supplies one identity already pinned to this company."""
    issuer = rnc(payload['seller']['rnc'], 'RNC emisor')
    if issuer != rnc(company_rnc, 'RNC de la empresa'):
        raise ValueError('El RNC del comprobante no coincide con la empresa.')
    _, certificate = load_identity(p12, password)
    if certificate.fingerprint(hashes.SHA256()).hex() != fingerprint:
        raise ValueError('El certificado no coincide con el autorizado para la empresa.')
    signed = sign_xml(build_invoice(payload, encf), p12, password)
    validate_signed(signed)
    verify_xml(signed, certificate)
    return signed


def connect(p12, password):
    client = Client(p12, password)
    client.authenticate()
    return client

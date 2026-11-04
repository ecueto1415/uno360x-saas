"""Explicit offline declaration signing; callers must obtain legal confirmation."""
import hashlib
from certification.xmlsig import parse, sign_xml, verify_xml, load_identity, DS


def sign_declaration(unsigned, p12, password, expected_sha256):
    if hashlib.sha256(unsigned).hexdigest() != expected_sha256:
        raise ValueError('La declaracion no corresponde al archivo revisado.')
    root = parse(unsigned)
    if root.tag != 'DeclaracionJurada' or len(root) != 1 or root[0].tag != 'DetalleGeneral' or len(root[0]) or not root[0].text:
        raise ValueError('Estructura de declaracion inesperada.')
    signed = sign_xml(unsigned, p12, password)
    key, certificate = load_identity(p12, password)
    verify_xml(signed, certificate)
    if parse(signed).findtext('DetalleGeneral') != root.findtext('DetalleGeneral'):
        raise ValueError('El texto legal debe conservarse integro.')
    return signed

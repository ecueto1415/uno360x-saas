"""Explicit production PKIX trust, current signed CRLs, no incoming AIA fetching."""
import base64
import pathlib
from datetime import datetime, timezone
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import rsa, ec, padding
from OpenSSL import crypto
from certification.xmlsig import parse, verify_xml, DS


def crl_signature_valid(crl, issuer):
    # cryptography's convenience CRL check excludes legacy SHA-1 CRLs. Verify
    # their declared algorithm explicitly against the pinned publisher key;
    # never disable signature verification or change XML RSA/SHA-256 signing.
    key = issuer.public_key()
    try:
        if isinstance(key, rsa.RSAPublicKey):
            key.verify(crl.signature, crl.tbs_certlist_bytes,
                       crl.signature_algorithm_parameters or padding.PKCS1v15(), crl.signature_hash_algorithm)
        elif isinstance(key, ec.EllipticCurvePublicKey):
            key.verify(crl.signature, crl.tbs_certlist_bytes, ec.ECDSA(crl.signature_hash_algorithm))
        else:
            return False
        return True
    except Exception:
        return False


def material(directory):
    directory = pathlib.Path(directory)
    certificates = [x509.load_pem_x509_certificate(p.read_bytes())
                    for p in sorted(directory.glob('*.pem'))]
    roots, intermediates = [], []
    for certificate in certificates:
        if 'TEST' in certificate.subject.rfc4514_string().upper():
            raise ValueError('CA de pruebas prohibida en produccion.')
        if not certificate.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
            raise ValueError('Se requiere una CA.')
        if not certificate.extensions.get_extension_for_class(x509.KeyUsage).value.key_cert_sign:
            raise ValueError('La CA no permite emitir certificados.')
        (roots if certificate.issuer == certificate.subject else intermediates).append(certificate)
    crls = [x509.load_der_x509_crl(p.read_bytes()) for p in sorted(directory.glob('*.crl'))]
    if not roots or not intermediates or not crls:
        raise ValueError('Cadena o revocacion de produccion incompleta.')
    return roots, intermediates, crls


def check_material(directory):
    roots, intermediates, crls = material(directory)
    now = datetime.now(timezone.utc)
    for certificate in roots + intermediates:
        if not certificate.not_valid_before_utc <= now < certificate.not_valid_after_utc:
            raise ValueError('CA fuera de vigencia.')
    for crl in crls:
        if not crl.next_update_utc or not crl.last_update_utc <= now < crl.next_update_utc:
            raise ValueError('Lista de revocacion vencida.')
        if not any(crl.issuer == ca.subject and crl_signature_valid(crl, ca)
                   for ca in roots + intermediates):
            raise ValueError('Firma CRL no confiable.')
    # Every configured issuing CA needs current revocation evidence, including
    # its own status under its root. No network is used in the request path.
    for ca in roots + intermediates:
        if not any(crl.issuer == ca.subject for crl in crls):
            raise ValueError('Falta CRL para una CA configurada.')
    return roots, intermediates, crls


def validate_certificate(certificate, directory, supplied=()):
    roots, intermediates, crls = check_material(directory)
    store = crypto.X509Store()
    for root in roots:
        store.add_cert(crypto.X509.from_cryptography(root))
    for crl in crls:
        store.add_crl(crl)
    store.set_flags(crypto.X509StoreFlags.CRL_CHECK | crypto.X509StoreFlags.CRL_CHECK_ALL)
    chain = crypto.X509StoreContext(store, crypto.X509.from_cryptography(certificate),
        [crypto.X509.from_cryptography(c) for c in intermediates + list(supplied)])
    chain.verify_certificate()
    if not certificate.extensions.get_extension_for_class(x509.KeyUsage).value.digital_signature:
        raise ValueError('Certificado sin permiso de firma.')
    try:
        is_ca = certificate.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    except x509.ExtensionNotFound:
        is_ca = False  # RFC 5280: absence cannot grant CA authority to a leaf.
    if is_ca:
        raise ValueError('El firmante debe ser un certificado de usuario.')
    return certificate


def trusted_sender(xml, directory):
    root = parse(xml)
    nodes = root.findall('./{%s}Signature/{%s}KeyInfo/{%s}X509Data/{%s}X509Certificate' % ((DS,)*4))
    if not 1 <= len(nodes) <= 8:
        raise ValueError('Cadena de firma invalida.')
    certificates = [x509.load_der_x509_certificate(base64.b64decode(n.text, validate=True)) for n in nodes]
    verify_xml(xml, certificates[0])
    return validate_certificate(certificates[0], directory, certificates[1:])

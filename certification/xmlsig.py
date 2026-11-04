"""Isolated certification XML signatures; never posts invoices to Odoo."""
import base64
import copy
import hashlib
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from lxml import etree
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.serialization import pkcs12

DS = 'http://www.w3.org/2000/09/xmldsig#'
C14N = 'http://www.w3.org/TR/2001/REC-xml-c14n-20010315'
RSA256 = 'http://www.w3.org/2001/04/xmldsig-more#rsa-sha256'
SHA256 = 'http://www.w3.org/2001/04/xmlenc#sha256'
DEMO = 'E310000000001'

def canonical(node):
    return etree.tostring(node, method='c14n', exclusive=False, with_comments=False)


def canonical_signed_info(node):
    # A standalone namespace-preserving round trip avoids libxml2 inserting
    # spurious xmlns="" declarations in default-namespace SignedInfo subtrees.
    # The declared inclusive C14N algorithm, reference digest and RSA/SHA256
    # verification are unchanged; no exclusive-C14N fallback is accepted.
    standalone = etree.fromstring(etree.tostring(node), etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False))
    return canonical(standalone)

def parse(xml):
    if len(xml) > 5_000_000:
        raise ValueError('XML demasiado grande.')
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, remove_blank_text=True)
    root = etree.fromstring(xml, parser)
    if root.getroottree().docinfo.doctype:
        raise ValueError('No se permiten DTD.')
    if root.tag not in ('ECF', 'SemillaModel', 'ARECF', 'ACECF', 'DeclaracionJurada'):
        raise ValueError('Tipo de documento XML no permitido.')
    return root

def load_identity(p12, password):
    try:
        key, cert, _ = pkcs12.load_key_and_certificates(p12, password)
    except Exception:
        raise ValueError('No se pudo abrir el certificado; revise la configuración privada.') from None
    if not isinstance(key, rsa.RSAPrivateKey) or cert is None or key.key_size < 2048:
        raise ValueError('Se requiere certificado RSA y clave privada de al menos 2048 bits.')
    now = datetime.now(timezone.utc)
    start = cert.not_valid_before_utc if hasattr(cert, "not_valid_before_utc") else cert.not_valid_before.replace(tzinfo=timezone.utc)
    end = cert.not_valid_after_utc if hasattr(cert, "not_valid_after_utc") else cert.not_valid_after.replace(tzinfo=timezone.utc)
    if not start <= now <= end:
        raise ValueError('El certificado no está vigente.')
    try:
        if not cert.extensions.get_extension_for_class(x509.KeyUsage).value.digital_signature:
            raise ValueError('El certificado no permite firma digital.')
    except x509.ExtensionNotFound:
        raise ValueError('El certificado no declara uso de firma digital.') from None
    if key.public_key().public_numbers() != cert.public_key().public_numbers():
        raise ValueError('La clave no corresponde al certificado.')
    return key, cert

def sign_xml(xml, p12, password):
    root = parse(xml)
    if root.xpath('//*[local-name()="Signature"]'):
        raise ValueError('El XML ya contiene una firma.')
    if root.find('FechaHoraFirma') is not None:
        raise ValueError('Regenerar el XML preliminar sin fecha de firma.')
    key, cert = load_identity(p12, password)
    if root.tag == 'ECF': etree.SubElement(root, 'FechaHoraFirma').text = datetime.now(ZoneInfo('America/Santo_Domingo')).strftime('%d-%m-%Y %H:%M:%S')
    digest = base64.b64encode(hashlib.sha256(canonical(root)).digest()).decode()
    sig = etree.SubElement(root, '{%s}Signature' % DS, nsmap={'ds': DS})
    def child(parent, name, **attrs):
        return etree.SubElement(parent, '{%s}%s' % (DS, name), **attrs)
    info = child(sig, 'SignedInfo')
    child(info, 'CanonicalizationMethod', Algorithm=C14N)
    child(info, 'SignatureMethod', Algorithm=RSA256)
    ref = child(info, 'Reference', URI='')
    transforms = child(ref, 'Transforms')
    child(transforms, 'Transform', Algorithm=DS + 'enveloped-signature')
    child(ref, 'DigestMethod', Algorithm=SHA256)
    child(ref, 'DigestValue').text = digest
    child(sig, 'SignatureValue').text = base64.b64encode(key.sign(canonical_signed_info(info), padding.PKCS1v15(), hashes.SHA256())).decode()
    data = child(child(sig, 'KeyInfo'), 'X509Data')
    child(data, 'X509Certificate').text = base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode()
    result = etree.tostring(root, encoding='UTF-8', xml_declaration=True, pretty_print=False)
    verify_xml(result, cert)
    return result

def verify_xml(xml, trusted_cert):
    root = parse(xml)
    signatures = root.findall('{%s}Signature' % DS)
    if len(signatures) != 1 or len(root.xpath('//*[local-name()="Signature"]')) != 1:
        raise ValueError('Se requiere una firma única al nivel raíz.')
    sig = signatures[0]
    ns = {'ds': DS}
    info = sig.find('ds:SignedInfo', ns)
    if info is None or len(info.findall('ds:Reference', ns)) != 1:
        raise ValueError('Referencia de firma inválida.')
    if (info.find('ds:CanonicalizationMethod', ns).get('Algorithm') != C14N
        or info.find('ds:SignatureMethod', ns).get('Algorithm') != RSA256):
        raise ValueError('Algoritmo inesperado.')
    ref = info.find('ds:Reference', ns)
    transforms = ref.findall('ds:Transforms/ds:Transform', ns)
    if ref.get('URI') != '' or len(transforms) != 1 or transforms[0].get('Algorithm') != DS + 'enveloped-signature' or ref.find('ds:DigestMethod', ns).get('Algorithm') != SHA256:
        raise ValueError('Referencia o transformación inesperada.')
    embedded = x509.load_der_x509_certificate(base64.b64decode(sig.findtext('ds:KeyInfo/ds:X509Data/ds:X509Certificate', namespaces=ns), validate=True))
    if embedded.fingerprint(hashes.SHA256()) != trusted_cert.fingerprint(hashes.SHA256()):
        raise ValueError('Certificado inesperado.')
    unsigned = copy.deepcopy(root)
    unsigned.remove(unsigned.find('{%s}Signature' % DS))
    if hashlib.sha256(canonical(unsigned)).digest() != base64.b64decode(ref.findtext('ds:DigestValue', namespaces=ns), validate=True):
        raise ValueError('El contenido XML cambió después de firmarse.')
    trusted_cert.public_key().verify(base64.b64decode(sig.findtext('ds:SignatureValue', namespaces=ns), validate=True), canonical_signed_info(info), padding.PKCS1v15(), hashes.SHA256())
    return True

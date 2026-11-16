"""POS certification transport. The only external hosts are DGII CerteCF."""
import argparse
from copy import deepcopy
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import sys
import urllib.request
import uuid

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from certification.xmlsig import DS, load_identity, parse, sign_xml, verify_xml

ECF = 'https://ecf.dgii.gov.do/certecf'
RFCE = 'https://fc.dgii.gov.do/certecf'
TOTAL_FIELDS = ('MontoGravadoTotal', 'MontoGravadoI1', 'MontoGravadoI2', 'MontoGravadoI3',
                'MontoExento', 'TotalITBIS', 'TotalITBIS1', 'TotalITBIS2', 'TotalITBIS3',
                'MontoImpuestoAdicional', 'ImpuestosAdicionales', 'MontoTotal',
                'MontoNoFacturable', 'MontoPeriodo')


def copy_fields(source, target, names):
    for name in names:
        node = source.find(name)
        if node is not None:
            target.append(deepcopy(node))


def create_rfce(signed_ecf, p12, password):
    invoice = parse(signed_ecf)
    _, cert = load_identity(p12, password)
    verify_xml(signed_ecf, cert)
    head = invoice.find('Encabezado')
    if head.findtext('IdDoc/TipoeCF') != '32' or not (
            Decimal('0') < Decimal(head.findtext('Totales/MontoTotal')) < Decimal('250000')):
        raise ValueError('RFCE exige E32 menor a RD$250,000.')
    result = etree.Element('RFCE')
    summary = etree.SubElement(result, 'Encabezado')
    copy_fields(head, summary, ('Version',))
    for tag, fields in (
        ('IdDoc', ('TipoeCF','eNCF','TipoIngresos','TipoPago','TablaFormasPago')),
        ('Emisor', ('RNCEmisor','RazonSocialEmisor','FechaEmision')),
        ('Comprador', ('RNCComprador','IdentificadorExtranjero','RazonSocialComprador')),
        ('Totales', TOTAL_FIELDS),
    ):
        src = head.find(tag)
        if src is None and tag != 'Comprador':
            raise ValueError('Falta ' + tag)
        dst = etree.SubElement(summary, tag)
        if src is not None:
            copy_fields(src,dst,fields)
    signature = invoice.findtext('.//{%s}SignatureValue' % DS)
    etree.SubElement(summary,'CodigoSeguridadeCF').text = signature[:6]
    signed = sign_xml(etree.tostring(result),p12,password)
    schema = etree.parse(str(ROOT/'certification/schemas/rfce32.xsd'))
    # XML Schema regex has no non-capturing group syntax. Preserve the original XSD.
    for facet in schema.findall('.//{http://www.w3.org/2001/XMLSchema}pattern'):
        pattern = facet.get('value')
        facet.set('value', pattern.replace('(?:', '('))
    etree.XMLSchema(schema).assertValid(parse(signed))
    verify_xml(signed, cert)
    return signed


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


def request(url, token=None, xml=None, filename=None):
    headers = {'Accept':'application/json, application/xml'}
    data = None
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if xml is not None:
        boundary = uuid.uuid4().hex
        headers['Content-Type'] = 'multipart/form-data; boundary=' + boundary
        data = (('--'+boundary+'\r\nContent-Disposition: form-data; name="xml"; filename="'+filename+
                 '"\r\nContent-Type: text/xml\r\n\r\n').encode() + xml + ('\r\n--'+boundary+'--\r\n').encode())
    with urllib.request.build_opener(NoRedirect()).open(
            urllib.request.Request(url,data,headers),timeout=30) as answer:
        return answer.read(1024*1024)


def submit(signed_ecf, p12, password, journal, send=request):
    root = parse(signed_ecf)
    _, cert = load_identity(p12,password)
    verify_xml(signed_ecf, cert)
    kind = root.findtext('Encabezado/IdDoc/TipoeCF')
    encf = root.findtext('Encabezado/IdDoc/eNCF')
    seller = root.findtext('Encabezado/Emisor/RNCEmisor')
    if kind not in ('31','32') or not re.fullmatch('E'+kind+r'[0-9]{10}',encf or '') or not re.fullmatch(r'[0-9]{9}',seller or ''):
        raise ValueError('Solo E31 o E32 con emisor y secuencia de certificación.')
    if seller in ('123456789','987654321'):
        raise ValueError('El emisor ficticio se limita a la prueba local.')
    is_summary = kind == '32' and Decimal(root.findtext('Encabezado/Totales/MontoTotal')) < Decimal('250000')
    payload = create_rfce(signed_ecf,p12,password) if is_summary else signed_ecf
    url = RFCE+'/recepcionfc/api/recepcion/ecf' if is_summary else ECF+'/recepcion/api/FacturasElectronicas'
    filename = seller+encf+'.xml'
    journal.mkdir(parents=True,exist_ok=True)
    record = journal/(seller+encf+'.json')
    if record.exists():
        raise ValueError('Ya existe un intento. Consulta su estado antes de reenviar.')
    seed = send(ECF+'/autenticacion/api/Autenticacion/Semilla')
    credentials = json.loads(send(ECF+'/autenticacion/api/Autenticacion/ValidarSemilla',
                                  xml=sign_xml(seed,p12,password),filename='semilla.xml'))
    token = credentials['token']
    with record.open('x',encoding='utf-8') as out:
        json.dump({'state':'envio_iniciado','endpoint':url},out)
        out.flush()
        os.fsync(out.fileno())
    # If the response is lost, keep the intent. An automated retry could duplicate issuance.
    response = json.loads(send(url,token=token,xml=payload,filename=filename))
    temporary = record.with_suffix('.next')
    temporary.write_text(json.dumps({'state':'respuesta_recibida','response':response}),encoding='utf-8')
    temporary.replace(record)
    return response


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('signed_ecf', type=Path)
    p.add_argument('--p12', required=True, type=Path)
    p.add_argument('--journal', required=True, type=Path)
    p.add_argument('--submit-certification', action='store_true', required=True)
    args = p.parse_args()
    print(json.dumps(submit(args.signed_ecf.read_bytes(),args.p12.read_bytes(),
                            os.environ['POS_CERT_PASSWORD'].encode(),args.journal),ensure_ascii=False))

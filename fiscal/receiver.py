"""OUTSOLUTECH production fiscal inbox. No automatic accounting or invoice emission.

Production trust and durable state are isolated from certification.
"""
import base64
import hashlib
import io
import json
import os
import pathlib
import re
import sqlite3
import threading
import shutil
from datetime import datetime
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from cryptography import x509
from OpenSSL import crypto
from lxml import etree
from certification.xmlsig import DS, parse, sign_xml, verify_xml, load_identity
from fiscal.trust import trusted_sender, validate_certificate, check_material

MAX_XML = 5_000_000
SCHEMAS = pathlib.Path(__file__).resolve().parents[1]/'certification/schemas'
RECEPTION = '/produccion/fe/recepcion/api/ecf'
APPROVAL = '/produccion/fe/aprobacioncomercial/api/ecf'


def compile_schema(path):
    # Preserve downloaded originals. Repair two published lexical defects in
    # memory only: a leading space in E31's named type and PCRE noncapturing
    # groups in ACECF, which XML Schema regex does not support. No constraints
    # or fields are removed and the accepted regular-expression language stays identical.
    tree = etree.fromstring(path.read_bytes().replace(b'(?:', b'('))
    for element in tree.findall('{http://www.w3.org/2001/XMLSchema}simpleType'):
        name = element.get('name','')
        if name == ' IndicadorServicioTodoIncluidoType':
            element.set('name',name.strip())
    return etree.XMLSchema(tree)


def upload(content_type, body):
    if len(body) > MAX_XML + 65536:
        raise ValueError('Archivo demasiado grande.')
    if content_type.split(';', 1)[0].strip().lower() in ('application/xml', 'text/xml'):
        data = body
    elif content_type.lower().startswith('multipart/form-data;'):
        if '\r' in content_type or '\n' in content_type or len(content_type) > 250:
            raise ValueError('Cabecera inválida.')
        message = BytesParser(policy=policy.default).parsebytes(
            ('Content-Type: '+content_type+'\r\nMIME-Version: 1.0\r\n\r\n').encode('ascii')+body)
        if not message.is_multipart() or message.defects:
            raise ValueError('Formulario inválido.')
        parts = list(message.iter_parts())
        if len(parts) != 1 or parts[0].get_param('name', header='content-disposition') != 'xml':
            raise ValueError('Se requiere un único archivo xml.')
        data = parts[0].get_payload(decode=True)
    else:
        raise ValueError('Envía un archivo XML.')
    if not data or len(data) > MAX_XML:
        raise ValueError('XML vacío o demasiado grande.')
    return data




class Inbox:
    def __init__(self, state, trust, rnc, p12, password):
        if not re.fullmatch(r'\d{9}|\d{11}', rnc):
            raise ValueError('RNC inválido.')
        self.state, self.trust, self.rnc = pathlib.Path(state), pathlib.Path(trust), rnc
        self.p12, self.password = p12, password
        _, own_certificate = load_identity(p12, password)
        validate_certificate(own_certificate, self.trust)
        self.state.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.schemas = {p.stem: compile_schema(p) for p in SCHEMAS.glob('*.xsd')}
        with self.database() as db:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('''CREATE TABLE IF NOT EXISTS messages(
              id INTEGER PRIMARY KEY, route TEXT NOT NULL, issuer TEXT NOT NULL,
              encf TEXT NOT NULL, sha256 TEXT NOT NULL, accepted INTEGER NOT NULL,
              reason INTEGER, received TEXT NOT NULL, response BLOB NOT NULL,
              UNIQUE(route,sha256))''')
            db.execute('''CREATE TABLE IF NOT EXISTS attempts(
              id INTEGER PRIMARY KEY, sha256 TEXT NOT NULL, route TEXT NOT NULL,
              accepted INTEGER NOT NULL, reason INTEGER, received TEXT NOT NULL)''')

    def database(self):
        return sqlite3.connect(self.state/'inbox.sqlite3', timeout=10)

    def ack(self, issuer, buyer, encf, reason):
        root = etree.Element('ARECF')
        detail = etree.SubElement(root, 'DetalleAcusedeRecibo')
        values = [('Version','1.0'), ('RNCEmisor',issuer), ('RNCComprador',buyer),
                  ('eNCF',encf), ('Estado','1' if reason else '0')]
        if reason:
            values.append(('CodigoMotivoNoRecibido',str(reason)))
        values.append(('FechaHoraAcuseRecibo',datetime.now(ZoneInfo('America/Santo_Domingo')).strftime('%d-%m-%Y %H:%M:%S')))
        for name, value in values:
            etree.SubElement(detail, name).text = value
        self.schemas['arecf'].assertValid(root)
        signed = sign_xml(etree.tostring(root), self.p12, self.password)
        self.schemas['arecf'].assertValid(parse(signed))
        return signed

    def receive(self, route, xml):
        if route not in (RECEPTION, APPROVAL):
            raise ValueError('Servicio no reconocido.')
        root = parse(xml)
        if route == RECEPTION and root.tag == 'ECF':
            issuer = root.findtext('Encabezado/Emisor/RNCEmisor','')
            buyer = root.findtext('Encabezado/Comprador/RNCComprador','')
            encf = root.findtext('Encabezado/IdDoc/eNCF','')
            kind = root.findtext('Encabezado/IdDoc/TipoeCF','')
            schema = self.schemas.get('ecf'+kind)
            destination = buyer
        elif route == APPROVAL and root.tag == 'ACECF':
            issuer = root.findtext('DetalleAprobacionComercial/RNCEmisor','')
            buyer = root.findtext('DetalleAprobacionComercial/RNCComprador','')
            encf = root.findtext('DetalleAprobacionComercial/eNCF','')
            schema, destination = self.schemas['acecf'], issuer
        else:
            raise ValueError('Documento no corresponde al servicio.')
        if not all(re.fullmatch(r'\d{9}|\d{11}', n) for n in (issuer, buyer)) or not re.fullmatch(r'E\d{12}', encf):
            raise ValueError('Identificación del documento inválida.')
        digest = hashlib.sha256(xml).hexdigest()
        with self.lock, self.database() as db:
            existing = db.execute('SELECT response,accepted FROM messages WHERE route=? AND sha256=?',(route,digest)).fetchone()
            if existing and existing[1]:
                return 200, bytes(existing[0])
            # Bound total storage; never consume the native database or erase evidence.
            if shutil.disk_usage(self.state).free < 1024**3 or sum(p.stat().st_size for p in self.state.iterdir() if p.is_file()) > 10*1024**3:
                raise RuntimeError('Almacenamiento fiscal pendiente de revision.')
            reason = 4 if destination != self.rnc else None
            if not reason and (schema is None or not schema.validate(root)):
                reason = 1
            if not reason:
                try:
                    trusted_sender(xml, self.trust)
                except Exception:
                    reason = 2
            if not reason and db.execute('SELECT 1 FROM messages WHERE route=? AND issuer=? AND encf=? AND accepted=1',(route,issuer,encf)).fetchone():
                reason = 3
            if route == RECEPTION:
                response, status = self.ack(issuer,buyer,encf,reason), 200
            else:
                status = 400 if reason else 200
                response = json.dumps({'mensaje':'Documento no aceptado' if reason else 'Aprobación comercial recibida','codigo':reason or 0}).encode()
            now = datetime.now(ZoneInfo('America/Santo_Domingo')).isoformat()
            tmp = self.state/(digest+'.next')
            with tmp.open('wb') as saved:
                saved.write(xml);saved.flush();os.fsync(saved.fileno())
            tmp.chmod(0o600);tmp.replace(self.state/(digest+'.xml'))
            directory=os.open(self.state,os.O_DIRECTORY)
            try:os.fsync(directory)
            finally:os.close(directory)
            db.execute('''INSERT INTO messages(route,issuer,encf,sha256,accepted,reason,received,response) VALUES(?,?,?,?,?,?,?,?)
                          ON CONFLICT(route,sha256) DO UPDATE SET accepted=excluded.accepted,reason=excluded.reason,
                          received=excluded.received,response=excluded.response''',
                       (route,issuer,encf,digest,int(not reason),reason,now,response))
            db.execute('INSERT INTO attempts(sha256,route,accepted,reason,received) VALUES(?,?,?,?,?)',
                       (digest,route,int(not reason),reason,now))
            return status, response


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16
    def __init__(self, address, inbox):
        self.inbox = inbox
        self.slots = threading.BoundedSemaphore(3)
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = 'UNO360X-Certificacion'
    def setup(self):
        super().setup();self.connection.settimeout(15)
    def log_message(self, *args):
        pass
    def reply(self, status, data, mime='application/json'):
        self.send_response(status)
        self.send_header('Content-Type',mime+'; charset=utf-8')
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Connection','close')
        self.end_headers();self.wfile.write(data)
    def do_GET(self):
        if self.path == '/health':
            try:
                check_material(self.server.inbox.trust)
                self.reply(200,b'{"service":"OUTSOLUTECH-fiscal-inbox","environment":"production"}')
            except Exception:
                self.reply(503,b'{"error":"Confianza fiscal pendiente de revision"}')
            return
        self.reply(405,b'{"error":"Utiliza POST con un archivo XML"}')
    def do_POST(self):
        route = urlsplit(self.path).path.rstrip('/').lower()
        if self.headers.get('Host') != 'erp.uno360x.com' or route not in (RECEPTION, APPROVAL) or urlsplit(self.path).query:
            self.reply(404,b'{"error":"Servicio no disponible"}');return
        if not self.server.slots.acquire(blocking=False):
            self.reply(503,b'{"error":"Reintenta en unos segundos"}');return
        try:
            length = self.headers.get('Content-Length','')
            if self.headers.get('Transfer-Encoding') or not length.isdecimal() or not 0 < int(length) <= MAX_XML+65536:
                self.reply(413,rb'{"error":"Tama\u00f1o de archivo no permitido"}');return
            body = self.rfile.read(int(length))
            if len(body) != int(length):
                raise ValueError('Carga incompleta.')
            xml = upload(self.headers.get('Content-Type',''),body)
            status, response = self.server.inbox.receive(route,xml)
            self.reply(status,response,'application/xml' if route == RECEPTION else 'application/json')
        except (ValueError,etree.LxmlError):
            self.reply(400,rb'{"error":"XML o formulario no v\u00e1lido"}')
        except Exception:
            self.reply(503,b'{"error":"Servicio temporalmente no disponible"}')
        finally:
            self.server.slots.release()


def main():
    os.umask(0o077)
    credentials = pathlib.Path(os.environ['CREDENTIALS_DIRECTORY'])
    inbox = Inbox('/var/lib/uno360x-dgii-production','/etc/uno360x-dgii-production/trust','132364805',
                  (credentials/'identity.p12').read_bytes(),(credentials/'password').read_bytes())
    Server(('127.0.0.1',18187),inbox).serve_forever()


if __name__ == '__main__':
    main()

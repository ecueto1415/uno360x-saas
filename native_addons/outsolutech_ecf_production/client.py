"""DGII authentication, reception and consultation; no invoice retries."""
import json
import re
import uuid
import ssl
import http.cookiejar
import time
import urllib.parse
import urllib.request
import urllib.error
from .crypto import sign_xml

HOST = 'https://ecf.dgii.gov.do'
ENVIRONMENTS = ('ecf',)
class DGIIError(ValueError):
    pass
class SubmissionUnknown(DGIIError):
    pass
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

class Client:
    def __init__(self, p12, password, environment='ecf', opener=None):
        if environment not in ENVIRONMENTS:
            raise DGIIError('El cliente productivo solo permite el ambiente ecf.')
        self.environment = environment
        self.p12, self.password = p12, password
        # DGII production resets HTTP requests after negotiating TLS 1.3 with
        # OpenSSL 3.3 on this VM. TLS 1.2 works with full CA/hostname validation.
        context=ssl.create_default_context()
        context.minimum_version=ssl.TLSVersion.TLSv1_2
        context.maximum_version=ssl.TLSVersion.TLSv1_2
        self._cookies=http.cookiejar.CookieJar()
        self.opener = opener or urllib.request.build_opener(NoRedirect(),urllib.request.HTTPCookieProcessor(self._cookies),urllib.request.HTTPSHandler(context=context))
        self.token = None
        self._last_request=0.0

    def request(self, path, *, payload=None, filename=None, query=None, is_submission=False):
        url = HOST + '/' + self.environment + '/' + path
        if query:
            url += '?' + urllib.parse.urlencode(query)
        headers = {'Accept': 'application/xml' if path.lower().endswith('/semilla') else 'application/json','User-Agent':'UNO360X/1.0'}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        if filename is not None and not re.fullmatch(r'[A-Za-z0-9_.-]+', filename):
            raise DGIIError('Nombre XML inválido.')
        body = None
        if payload is not None:
            boundary = '----OUTSECF' + uuid.uuid4().hex
            headers['Content-Type'] = 'multipart/form-data; boundary=' + boundary
            body = (('--'+boundary+'\r\nContent-Disposition: form-data; name="xml"; filename="'+filename+'"\r\nContent-Type: text/xml\r\n\r\n').encode() + payload + ('\r\n--'+boundary+'--\r\n').encode())
        req = urllib.request.Request(url, data=body, headers=headers)
        try:
            # Pace sequential calls and retry transport failures only for GET.
            # Never retry an invoice POST, even if its response was lost.
            for attempt in range(3 if body is None and not is_submission else 1):
                wait=1.0-(time.monotonic()-self._last_request)
                if wait>0:time.sleep(wait)
                self._last_request=time.monotonic()
                try:
                    with self.opener.open(req, timeout=35) as response:
                        raw = response.read(1_000_001)
                    break
                except urllib.error.HTTPError:
                    raise
                except (OSError,TimeoutError):
                    if attempt==2 or body is not None or is_submission:raise
            if len(raw) > 1_000_000:
                error = SubmissionUnknown if is_submission else DGIIError
                raise error('Respuesta DGII demasiado grande; conciliar si fue un envío.')
        except urllib.error.HTTPError as error:
            # DGII documents this read-only absence as HTTP 400, not 404.
            # Never generalize other errors or a failed POST into "not found".
            if not is_submission and path=='consultatrackids/api/trackids/consulta' and error.code==400:
                try:
                    absent=json.loads(error.read(4097))
                except (ValueError,UnicodeDecodeError):absent=None
                if absent=={'codigo':0,'estado':'TrackId no encontrado.'}:return b'[]'
            # Do not expose headers, credentials, signed seed or token in logs/UI.
            if is_submission:
                raise SubmissionUnknown('DGII devolvió HTTP %s durante el envío. Conciliar antes de reenviar.' % error.code) from None
            raise DGIIError('DGII devolvió HTTP %s. Revise habilitación, firma o disponibilidad.' % error.code) from None
        except (OSError, TimeoutError) as error:
            if is_submission:
                raise SubmissionUnknown('Resultado del envío desconocido por error de conexión. No reenviar automáticamente.') from None
            raise DGIIError('No se pudo conectar con DGII; no se envió una factura en esta operación.') from None
        return raw

    def authenticate(self):
        seed = self.request('autenticacion/api/autenticacion/semilla')
        from lxml import etree
        root = etree.fromstring(seed, etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False))
        if root.tag != 'SemillaModel' or len(root) != 2 or not root.findtext('valor') or not root.findtext('fecha'):
            raise DGIIError('Respuesta de semilla inesperada.')
        signed = sign_xml(seed, self.p12, self.password)
        try:
            data = json.loads(self.request('autenticacion/api/autenticacion/validarsemilla', payload=signed, filename='semilla.xml'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise DGIIError('DGII no devolvió una respuesta JSON de autenticación válida.') from None
        if not isinstance(data, dict) or not isinstance(data.get('token'), str) or not data['token']:
            raise DGIIError('DGII no entregó token de autenticación.')
        self.token = data['token']
        # Only expiry returned to UI. Token remains in memory for the operation.
        return data.get('expira', '')

    def submit(self, signed, issuer, encf):
        if not self.token:
            raise DGIIError('Autentique antes de enviar.')
        try:
            data = json.loads(self.request('recepcion/api/facturaselectronicas', payload=signed, filename=issuer+encf+'.xml', is_submission=True))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise SubmissionUnknown('Respuesta de recepción no interpretable; conciliar antes de reenviar.') from None
        if not isinstance(data, dict) or not data.get('trackId'):
            raise SubmissionUnknown('La recepción no entregó TrackId; conciliar el e-NCF antes de reenviar.')
        return {'trackId': str(data['trackId'])}

    def result(self, track):
        if not self.token:
            raise DGIIError('Autentique antes de consultar.')
        try:
            data = json.loads(self.request('consultaresultado/api/consultas/estado', query={'trackid': track}))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise DGIIError('La consulta no devolvió JSON válido.') from None
        if not isinstance(data, dict):
            raise DGIIError('Respuesta de consulta inesperada.')
        return data

    def tracks(self, issuer, encf):
        """Read-only reconciliation. Never submits or retries a fiscal document."""
        if not self.token:
            raise DGIIError('Autentique antes de consultar.')
        if not re.fullmatch(r'(?:[0-9]{9}|[0-9]{11})', issuer) or not re.fullmatch(r'E[0-9]{12}', encf):
            raise DGIIError('RNC/e-NCF inválido para conciliación.')
        try:
            data = json.loads(self.request('consultatrackids/api/trackids/consulta', query={'rncemisor': issuer, 'encf': encf}))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise DGIIError('La consulta de TrackIds no devolvió JSON válido.') from None
        if isinstance(data, dict): data = [data]
        if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
            raise DGIIError('Respuesta de TrackIds inesperada.')
        return data


def validate_result(result, issuer, encf, track=None):
    """Never accept a result belonging to another issuer, sequence or TrackId."""
    if not isinstance(result, dict):
        raise DGIIError('Respuesta DGII inesperada.')
    state = {'1':'accepted','2':'rejected','3':'sent','4':'conditional'}.get(str(result.get('codigo')))
    actual = result.get('eNCF', result.get('encf'))
    if result.get('rnc') and str(result['rnc']) != issuer:
        raise DGIIError('La consulta devolvió un RNC diferente.')
    if actual and actual != encf:
        raise DGIIError('La consulta devolvió otro e-NCF.')
    if track and result.get('trackId') and result['trackId'] != track:
        raise DGIIError('La consulta devolvió otro TrackId.')
    if state in ('accepted','conditional','rejected') and (str(result.get('rnc','')) != issuer or actual != encf):
        raise DGIIError('Falta la identidad del comprobante en el resultado final.')
    return state

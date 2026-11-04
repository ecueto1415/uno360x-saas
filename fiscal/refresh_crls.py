"""Refresh signed production revocation data from fixed publisher URLs only."""
import json
import os
import pathlib
import urllib.request
from datetime import datetime, timezone
from cryptography import x509
from fiscal.trust import check_material, crl_signature_valid

SOURCES = {
 'digifirma-root': ['http://crl1.camarasantodomingo.do/public/pki/crl/arl_ccpsd.crl', 'http://crl2.camarasantodomingo.do/public/pki/crl/arl_ccpsd.crl'],
 'digifirma-subca': ['http://crl1.camarasantodomingo.do/public/pki/crl/CCPSD.crl', 'http://crl2.camarasantodomingo.do/public/pki/crl/CCPSD.crl'],
 'viafirma-root-003': ['http://crl.viafirma.do/rootca.crl', 'http://crl2.viafirma.do/rootca.crl'],
 'viafirma-subca-007': ['http://crl.viafirma.do/viafirmasubca.crl', 'http://crl2.viafirma.do/viafirmasubca.crl'],
 'viafirma-root-005': ['http://crl.viafirma.do/viafirmaqtsproot.crl', 'http://crl2.viafirma.do/viafirmaqtsproot.crl'],
 'viafirma-subca-008': ['http://crl.viafirma.do/viafirmaqtspsubca008.crl', 'http://crl2.viafirma.do/viafirmaqtspsubca008.crl'],
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def refresh(directory):
    directory = pathlib.Path(directory)
    opener = urllib.request.build_opener(NoRedirect)
    failures = []
    for name, urls in SOURCES.items():
        issuer = x509.load_pem_x509_certificate((directory/(name+'.pem')).read_bytes())
        for url in urls:
            try:
                with opener.open(url, timeout=15) as response:
                    data = response.read(10_000_001)
                if len(data) > 10_000_000:
                    raise ValueError('CRL demasiado grande.')
                crl = x509.load_der_x509_crl(data)
                now = datetime.now(timezone.utc)
                if crl.issuer != issuer.subject or not crl_signature_valid(crl, issuer):
                    raise ValueError('Firma CRL invalida.')
                if not crl.next_update_utc or not crl.last_update_utc <= now < crl.next_update_utc:
                    raise ValueError('CRL vencida.')
                target = directory/(name+'.crl')
                temp = target.with_suffix('.next')
                temp.write_bytes(data);temp.chmod(0o644);temp.replace(target)
                break
            except Exception:
                continue
        else:
            failures.append(name)
    check_material(directory)  # Existing fresh, signed cache may bridge an outage.
    if failures:
        raise RuntimeError('No se pudieron renovar CRL: '+','.join(failures))
    return {'current_signed_crls': len(SOURCES)}


if __name__ == '__main__':
    print(json.dumps(refresh(os.environ.get('FISCAL_TRUST', '/etc/uno360x-dgii-production/trust'))))

"""Authenticated local API and real PDF checks. No production or external calls."""
import http.cookiejar
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import sqlite3
import urllib.parse
import urllib.request
from tenants import run,inspect

class Assets(HTMLParser):
    def __init__(self):super().__init__();self.paths=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        value=a.get('src') if tag=='script' else a.get('href') if tag=='link' else None
        if value and value.startswith('/web/assets/'):
            self.paths.append(value)

def main():
    if os.name!='posix' or os.geteuid()!=0 or 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower():
        raise SystemExit('Solo WSL root de laboratorio.')
    state=Path('/var/lib/uno360x-saas-dev/tenants')
    connection=sqlite3.connect((state/'registry.sqlite3').as_uri()+'?mode=ro',uri=True)
    try:rows=connection.execute('SELECT id,slug,hostname FROM tenants ORDER BY slug').fetchall()
    finally:connection.close()
    assert {slug for tid,slug,host in rows}=={'empresa-alfa','empresa-beta'}
    results=[]
    for tid,slug,hostname in rows:
        prefix='uno360x-lab-'+slug
        app=prefix+'-app';info=inspect(app)
        assert set(info['NetworkSettings']['Networks'])=={prefix+'-private'}
        ip=info['NetworkSettings']['Networks'][prefix+'-private']['IPAddress']
        base='http://'+ip+':8069'
        opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),urllib.request.ProxyHandler({}))
        def rpc(path,params):
            body=json.dumps({'jsonrpc':'2.0','method':'call','params':params,'id':1}).encode()
            with opener.open(urllib.request.Request(base+path,data=body,headers={'Content-Type':'application/json'}),timeout=60) as response:
                result=json.load(response)
            if 'error' in result:raise RuntimeError('Fallo RPC en laboratorio: '+path)
            return result['result']
        password=(state/tid/'admin-password').read_text()
        session=rpc('/web/session/authenticate',{'db':'tenant_'+tid[:16],'login':'admin@'+hostname,'password':password})
        assert session.get('uid')
        view=rpc('/web/dataset/call_kw/sale.order/get_view',{'model':'sale.order','method':'get_view','args':[],'kwargs':{'view_type':'form'}})
        assert 'ux_quote_form' in view['arch'] and 'ux_quote_tax_select' in view['arch']
        with opener.open(base+'/odoo',timeout=60) as response:html=response.read().decode()
        assets=Assets();assets.feed(html)
        assert assets.paths
        for path in set(assets.paths):
            with opener.open(base+path,timeout=90) as response:
                content=response.read()
                assert response.status==200 and content
                assert b'Error while compiling' not in content and b'Could not get content for' not in content
        # Actual native renderer, not the mocked version used by fast ORM tests.
        # All created business records and PDF attachments are rolled back.
        code="""from odoo import api
env=api.Environment(env.cr,env.uid,dict(env.context,tracking_disable=True,no_reset_password=True))
partner=env['res.partner'].create({'name':'CLIENTE FICTICIO PDF TEMPORAL'})
order=env['sale.order'].create({'partner_id':partner.id})
env['ir.config_parameter'].sudo().set_param('report.url','http://127.0.0.1:8069')
pdf,kind=env['ir.actions.report'].with_context(report_pdf_no_attachment=True)._render_qweb_pdf('sale.action_report_saleorder',res_ids=order.ids)
assert kind=='pdf' and pdf.startswith(b'%PDF-') and len(pdf)>1000
print('REAL_PDF_OK')
env.cr.rollback()
"""
        p=run('exec','-i',app,'odoo','shell','-c','/etc/odoo/odoo.conf','--no-http',input=code,check=False)
        if p.returncode or 'REAL_PDF_OK' not in p.stdout:
            # No private config or credential material is included in this code.
            raise RuntimeError('PDF real falló para '+slug+': '+p.stderr[-2000:])
        results.append({'company':slug,'login_api':True,'quote_form_compiled':True,
                        'asset_files_http_200':len(set(assets.paths)),'real_pdf':True})
    print(json.dumps({'local_only':True,'runtime':results},indent=2))

if __name__=='__main__':main()

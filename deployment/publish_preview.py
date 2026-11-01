"""Publish only the browser simulation as a new, unlisted Odoo website page.

Requires explicit host/database arguments. Never alters the homepage, login,
users, service configuration, existing views, business records or credentials.
"""
import argparse
import base64
import datetime
import hashlib
import json
import re
from pathlib import Path
import subprocess

from build_public_preview import build


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--host',required=True);parser.add_argument('--identity-file',required=True)
    parser.add_argument('--database',required=True);parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--update-own-preview',action='store_true')
    args=parser.parse_args()
    if args.database!='Outsolutech_prueba' or args.host!='linuxuser@140.82.47.80':
        raise SystemExit('Esta publicación está limitada al destino revisado y autorizado.')
    manifest=build(args.work)
    bundle={name:base64.b64encode((args.work/name).read_bytes()).decode() for name in manifest['files']}
    bundle['manifest']=manifest
    ssh=['ssh','-i',args.identity_file,'-o','BatchMode=yes','-o','ConnectTimeout=15',args.host]
    def run(command,data=None):
        result=subprocess.run(ssh+[command],input=data,capture_output=True)
        if result.returncode:
            (args.work/'publication_error.log').write_bytes(result.stderr)
            raise SystemExit('Falló una operación de publicación; no se ejecutarán pasos adicionales.')
        return result.stdout
    remote=run('sudo -n mktemp -d /tmp/uno360x-preview-XXXXXXXX').decode().strip()
    if not re.fullmatch('/tmp/uno360x-preview-[A-Za-z0-9]+',remote):raise SystemExit('Ruta temporal inesperada.')
    run("sudo -n sh -c 'umask 077; cat > "+remote+"/bundle.json'",json.dumps(bundle).encode())
    # Copy a read-only bundle for the existing service account; directory stays private.
    run('sudo -n chown odoo18:odoo18 '+remote+' '+remote+'/bundle.json')
    code=r'''
import base64,hashlib,json,pathlib
folder=pathlib.Path(REMOTE_FOLDER)
bundle=json.loads((folder/'bundle.json').read_text())
Page=env['website.page'];View=env['ir.ui.view'];Attachment=env['ir.attachment']
page=Page.search([('url','=','/prueba-saas')])
existing=View.search([('key','=','uno360x.signup_preview_public')])
if UPDATE_MODE:
 assert len(page)==1 and len(existing)==1 and page.view_id==existing, 'Solo actualizar la vista previa propia'
 (folder/'previous_arch.json').write_text(json.dumps({'view_id':existing.id,'arch_db':existing.arch_db}))
else:
 assert not page and not existing, 'No reemplazar una página o vista existente'
home=View.search([('key','=','uno360x.homepage_public')])
before={v.id:hashlib.sha256(v.arch_db.encode()).hexdigest() for v in home}
env.cr.execute('SELECT gid FROM res_groups_users_rel WHERE uid=2 ORDER BY gid')
groups=env.cr.fetchall()
site=env['website'].search([],limit=1);assert site
arch=base64.b64decode(bundle['preview.xml']).decode()
view=existing if UPDATE_MODE else View.create({'name':'UNO360X | Vista previa de registro','key':'uno360x.signup_preview_public',
                 'type':'qweb','website_id':site.id,'arch_db':arch})
assets=[]
for name,mimetype in [('preview.css','text/css'),('preview.js','text/javascript')]:
 raw=base64.b64decode(bundle[name]);assert hashlib.sha256(raw).hexdigest()==bundle['manifest']['files'][name]
 asset=Attachment.create({'name':'uno360x-'+name,'type':'binary','datas':bundle[name],
                          'mimetype':mimetype,'public':True,'res_model':'ir.ui.view','res_id':view.id})
 assets.append(asset.id)
 arch=arch.replace('__CSS_URL__' if name.endswith('.css') else '__JS_URL__','/web/content/%s/%s'%(asset.id,name))
view.arch_db=arch
values={'name':'Vista previa del registro UNO360X','url':'/prueba-saas','view_id':view.id,
        'website_id':site.id,'is_published':True}
if 'is_indexed' in Page._fields:values['is_indexed']=False
if not UPDATE_MODE:page=Page.create(values)
assert all(hashlib.sha256(View.browse(vid).arch_db.encode()).hexdigest()==value for vid,value in before.items())
env.cr.execute('SELECT gid FROM res_groups_users_rel WHERE uid=2 ORDER BY gid');assert env.cr.fetchall()==groups
result={'url':'https://uno360x.com/prueba-saas','page_id':page.id,'view_id':view.id,'attachment_ids':assets,
        'mode':'browser_only_simulation','homepage_unchanged':True,'administrator_groups_unchanged':True,
        'real_signup_enabled':False,'restart_required':False,'manifest':bundle['manifest']}
(folder/'publication.json').write_text(json.dumps(result,indent=2))
env.cr.commit()
env.registry.signal_changes()
print('UNO360X_PREVIEW_RESULT '+json.dumps(result))
'''.replace('REMOTE_FOLDER',repr(remote)).replace('UPDATE_MODE',repr(args.update_own_preview))
    output=run('sudo -n -u odoo18 /opt/odoo18/venv/bin/python3.12 /opt/odoo18/odoo-bin shell -c /etc/odoo18.conf -d '+args.database+' --no-http',code.encode())
    marker=b'UNO360X_PREVIEW_RESULT '
    lines=[line[len(marker):] for line in output.splitlines() if line.startswith(marker)]
    if len(lines)!=1:raise SystemExit('No se obtuvo confirmación; revisar el estado antes de repetir.')
    result=json.loads(lines[0]);(args.work/'publication.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()

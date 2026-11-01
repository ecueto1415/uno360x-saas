"""Add the approved homepage trial block; preserve every existing component."""
import argparse
import json
from pathlib import Path
import re
import subprocess


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--host',required=True);parser.add_argument('--identity-file',required=True)
    parser.add_argument('--database',required=True);parser.add_argument('--work',type=Path,required=True)
    args=parser.parse_args()
    if args.host!='linuxuser@140.82.47.80' or args.database!='Outsolutech_prueba':
        raise SystemExit('Destino distinto del revisado y autorizado.')
    args.work.mkdir(parents=True,exist_ok=True)
    ssh=['ssh','-i',args.identity_file,'-o','BatchMode=yes','-o','ConnectTimeout=15',args.host]
    def run(command,data=None):
        result=subprocess.run(ssh+[command],input=data,capture_output=True)
        if result.returncode:
            (args.work/'error.log').write_bytes(result.stderr)
            raise SystemExit('Falló la publicación. Revisar estado y copia antes de repetir.')
        return result.stdout
    remote=run('sudo -n mktemp -d /tmp/uno360x-home-XXXXXXXX').decode().strip()
    if not re.fullmatch('/tmp/uno360x-home-[A-Za-z0-9]+',remote):raise SystemExit('Ruta inesperada.')
    module=Path(__file__).with_name('home_trial.py').read_bytes()
    run("sudo -n sh -c 'umask 077; cat > "+remote+"/home_trial.py'",module)
    run('sudo -n chown odoo18:odoo18 '+remote+' '+remote+'/home_trial.py')
    code=r'''
import hashlib,importlib.util,json,pathlib
folder=pathlib.Path(REMOTE_FOLDER)
spec=importlib.util.spec_from_file_location('home_trial_change',folder/'home_trial.py')
change=importlib.util.module_from_spec(spec);spec.loader.exec_module(change)
View=env['ir.ui.view'];Page=env['website.page']
view=View.search([('key','=','uno360x.homepage_public')]);assert len(view)==1
preview=Page.search([('url','=','/prueba-saas')]);assert len(preview)==1 and preview.is_published
assert preview.view_id.key=='uno360x.signup_preview_public'
owner=env['res.users'].search([('login','=','ecueto@outsolutech.com')]);assert len(owner)==1 and owner.id==2 and owner.active
env.cr.execute('SELECT gid FROM res_groups_users_rel WHERE uid=2 ORDER BY gid');groups=env.cr.fetchall()
before={lang:view.with_context(lang=lang).arch_db for lang in ['en_US','es_ES']}
after={lang:change.add_trial(arch) for lang,arch in before.items()}
backup={'view_id':view.id,'key':view.key,'database':'Outsolutech_prueba','architectures':before,
        'sha256':{lang:hashlib.sha256(arch.encode()).hexdigest() for lang,arch in before.items()}}
(folder/'home_before.json').write_text(json.dumps(backup,ensure_ascii=False))
preview_hash=hashlib.sha256(preview.view_id.arch_db.encode()).hexdigest()
for lang,arch in after.items():view.with_context(lang=lang).write({'arch_db':arch})
for lang,arch in after.items():
 actual=view.with_context(lang=lang).arch_db
 assert actual==arch
 assert actual.replace(change.STYLE,'',1).replace(change.BANNER,'',1)==before[lang]
assert hashlib.sha256(preview.view_id.arch_db.encode()).hexdigest()==preview_hash
env.cr.execute('SELECT gid FROM res_groups_users_rel WHERE uid=2 ORDER BY gid');assert env.cr.fetchall()==groups
result={'home_view_id':view.id,'url':'https://uno360x.com/','trial_target':'https://uno360x.com/prueba-saas',
        'changed_languages':list(after),'change_scope':'approved_trial_block_only','existing_content_preserved':True,
        'administrator_group_count':len(groups),'administrator_groups_unchanged':True,'preview_unchanged':True,
        'restart_required':False,'real_signup_enabled':False,
        'after_sha256':{lang:hashlib.sha256(arch.encode()).hexdigest() for lang,arch in after.items()}}
env.cr.commit();env.registry.signal_changes()
(folder/'publication.json').write_text(json.dumps(result,indent=2))
print('UNO360X_HOME_RESULT '+json.dumps(result))
'''.replace('REMOTE_FOLDER',repr(remote))
    output=run('sudo -n -u odoo18 /opt/odoo18/venv/bin/python3.12 /opt/odoo18/odoo-bin shell -c /etc/odoo18.conf -d '+args.database+' --no-http',code.encode())
    marker=b'UNO360X_HOME_RESULT '
    lines=[line[len(marker):] for line in output.splitlines() if line.startswith(marker)]
    if len(lines)!=1:raise SystemExit('No se confirmó el resultado; revisar antes de repetir.')
    result=json.loads(lines[0])
    backup='/opt/uno360x-saas/backups/'+remote.rsplit('/',1)[1]
    run('sudo -n install -d -m 700 '+backup)
    run('sudo -n install -m 600 '+remote+'/home_before.json '+backup+'/home_before.json')
    result['protected_backup']=backup+'/home_before.json'
    (args.work/'publication.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()

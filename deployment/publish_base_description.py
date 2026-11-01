"""Publish only the approved text extension of Base Empresarial on existing plans."""
import base64,json,subprocess
from pathlib import Path
from base_description import OLD,NEW
HOST='linuxuser@140.82.47.80'
SSH=['ssh','-i',str(Path.home()/'.ssh/uno360x_codex'),'-o','BatchMode=yes',HOST]
def run(command,code=None):
 p=subprocess.run(SSH+[command],input=code,capture_output=True)
 if p.returncode:
  raise RuntimeError(p.stderr.decode(errors='replace')[-1800:])
 return p.stdout
folder=run('sudo -n mktemp -d /tmp/uno360x-base-description-XXXXXXXX').decode().strip()
assert folder.startswith('/tmp/uno360x-base-description-') and len(folder.split('/'))==3
backup='/opt/uno360x-saas/backups/'+folder.rsplit('/',1)[1]
run('sudo -n chown odoo18:odoo18 '+folder)
code=r'''
import pathlib,json,hashlib
v=env['ir.ui.view'].browse(3884)
assert v.key=='uno360x.plans_public'
p=env['website.page'].search([('url','=','/planes-y-precios')]);assert len(p)==1 and p.view_id==v
langs=['en_US','es_ES']
before={lang:v.with_context(lang=lang).arch_db for lang in langs}
assert all(s.count(OLD)==1 for s in before.values())
protected=env['ir.ui.view'].search([('key','in',['uno360x.homepage_public','uno360x.signup_preview_public'])])
hashes={f'{view.id}/{lang}':hashlib.sha256(view.with_context(lang=lang).arch_db.encode()).hexdigest() for view in protected for lang in langs}
env.cr.execute('SELECT gid FROM res_groups_users_rel WHERE uid=2 ORDER BY gid');groups=env.cr.fetchall()
pathlib.Path(FOLDER+'/before.json').write_text(json.dumps({'id':v.id,'key':v.key,'arches':before},ensure_ascii=False))
for lang,original in before.items():
 updated=original.replace(OLD,NEW);assert updated.replace(NEW,OLD)==original
 v.with_context(lang=lang).arch_db=updated
assert all(hashlib.sha256(view.with_context(lang=lang).arch_db.encode()).hexdigest()==hashes[f'{view.id}/{lang}'] for view in protected for lang in langs)
env.cr.execute('SELECT gid FROM res_groups_users_rel WHERE uid=2 ORDER BY gid');assert env.cr.fetchall()==groups
result={'url':'https://uno360x.com/planes-y-precios','backup':BACKUP+'/before.json','text_only':True,'fiscal_block_preserved':True,'home_unchanged':True,'admin_groups_unchanged':True}
env.cr.commit();env.registry.signal_changes()
print('DESCRIPTION_RESULT '+json.dumps(result))
'''.replace('FOLDER',repr(folder)).replace('BACKUP',repr(backup)).replace('OLD',repr(OLD)).replace('NEW',repr(NEW))
try:
 output=run('sudo -n -u odoo18 /opt/odoo18/venv/bin/python3.12 /opt/odoo18/odoo-bin shell -c /etc/odoo18.conf -d Outsolutech_prueba --no-http',code.encode())
finally:
 run('sudo -n cp -a '+folder+' '+backup+' && sudo -n chown -R root:root '+backup+' && sudo -n chmod 700 '+backup+' && sudo -n find '+backup+' -type f -exec chmod 600 {} +')
 run('sudo -n chown -R root:root '+folder+' && sudo -n chmod 700 '+folder+' && sudo -n find '+folder+' -type f -exec chmod 600 {} +')
lines=[l[len('DESCRIPTION_RESULT '):] for l in output.decode().splitlines() if l.startswith('DESCRIPTION_RESULT ')]
assert len(lines)==1,'Check current state before retrying'
print(lines[0])

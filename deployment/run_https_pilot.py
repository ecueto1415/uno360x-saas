"""Explicit controlled pilot. Not started automatically by deployment."""
import json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from deployment.pilot_adapter import PilotAdapter
from deployment.https_pilot import HTTPSGatewayManager,HTTPSIdentityServer
from control.mail_delivery import SMTPDelivery
from control.identity import dummy_password_hash
STATE=Path('/var/lib/uno360x-saas/control')
def main():
 os.umask(0o077);dummy_password_hash()
 config=json.loads(Path('/etc/uno360x-saas/https-pilot.json').read_text())
 if config.get('enabled') is not True:raise RuntimeError('Pilot is not enabled')
 delivery=SMTPDelivery.from_file(STATE/'mail-resend.json')
 if delivery.config['public_origin']!=config['central_origin']:raise RuntimeError('Mail origin must match identity origin')
 manager=HTTPSGatewayManager(STATE/'control.sqlite3',PilotAdapter(),config['central_origin'],config['tenant_origin'],shared_origin=config.get('shared_gateway',False))
 server=HTTPSIdentityServer(18183,STATE/'control.sqlite3',delivery,manager.launch,config['central_origin'],config.get('allowed_emails',[]),config['tenant_origin'],public_signup=config.get('public_signup',False),operational_login=config.get('operational_login',False),operational_directory=config.get('operational_directory'))
 server.admission_status_path=STATE/'admission-status.json'
 try:server.serve_forever()
 finally:server.server_close();manager.close()
if __name__=='__main__':main()

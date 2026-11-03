"""Run after approval of the new admin DNS/public access. Never changes legacy vhosts."""
import pathlib,subprocess,socket,time,urllib.request,json
SOURCE=pathlib.Path('/srv/uno360x-saas/master-current').resolve()
TARGET=pathlib.Path('/etc/nginx/sites-available/uno360x-admin')
LINK=pathlib.Path('/etc/nginx/sites-enabled/uno360x-admin')
socket.getaddrinfo('admin.uno360x.com',443)
if LINK.exists():raise SystemExit('Administrative vhost already enabled; review before changing it.')
TARGET.write_text('''server {
 listen 80;
 server_name admin.uno360x.com;
 location ^~ /.well-known/acme-challenge/ { root /var/lib/uno360x-acme; }
 location / { return 404; }
}
''')
LINK.symlink_to(TARGET)
try:
 subprocess.run(['nginx','-t'],check=True,capture_output=True)
 subprocess.run(['systemctl','reload','nginx'],check=True)
 result=subprocess.run(['certbot','certonly','--webroot','--webroot-path','/var/lib/uno360x-acme','--cert-name','uno360x-admin','-d','admin.uno360x.com','--non-interactive'],capture_output=True,text=True,timeout=180)
 if result.returncode:raise RuntimeError('Certificate issuance failed; public admin proxy remains closed.')
 TARGET.write_bytes((SOURCE/'deployment/nginx-admin-console.conf').read_bytes())
 subprocess.run(['nginx','-t'],check=True,capture_output=True)
 subprocess.run(['systemctl','reload','nginx'],check=True)
 print(json.dumps({'certificate_installed':True,'admin_vhost_enabled':True,'cloudflare_per_host_full_strict_required':True,'legacy_services_restarted':False}))
except Exception:
 if LINK.is_symlink():LINK.unlink()
 subprocess.run(['nginx','-t'],check=True,capture_output=True);subprocess.run(['systemctl','reload','nginx'],check=True)
 raise

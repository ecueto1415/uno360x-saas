"""Fixed local assets and preserved public snapshots; no filesystem URL mapping."""
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'control' / 'web'
APP_ROUTES = {'/prueba', '/prueba/inicio', '/prueba/cuenta', '/prueba/revisa-correo', '/prueba/confirmar',
              '/prueba/restablecer', '/prueba/empresa', '/prueba/empresas', '/prueba/preparando',
              '/prueba/espacio', '/web/login', '/web/reset_password', '/web/signup'}


def nav():
    return (WEB / 'nav.html').read_text(encoding='utf-8')


def snapshot(kind):
    tree = ET.fromstring((ROOT / 'website_snapshots' / f'uno360x.{kind}_public.es_ES.xml').read_text(encoding='utf-8'))
    return next(e for e in tree.iter('div') if e.get('id') == 'uno360x-public')


def public_page(kind):
    root = snapshot(kind)
    for parent in list(root.iter()):
        for child in list(parent):
            if child.tag == 'nav' and child.get('class') == 'u-nav':
                parent.remove(child)
                parent.insert(0, ET.fromstring(nav()))
            if child.tag == 'script':
                parent.remove(child)
            if child.tag == 'input' and child.get('name') == 'csrf_token':
                parent.remove(child)
        for key in list(parent.attrib):
            if key.startswith('t-'):
                del parent.attrib[key]
    if kind == 'homepage':
        copy = next(e for e in root.iter() if e.get('class') == 'u-hero-copy')
        copy.append(ET.fromstring('''<div class="home-trial"><div><strong>15 días gratis para conocer UNO360X</strong><small>Sin tarjeta de crédito.</small></div><a class="button" href="/prueba">Probar gratis 15 días</a></div>'''))
        # Original production CRM form is presentation only in this isolated copy.
        for form in root.iter('form'):
            form.set('action', '#contacto')
            for item in form.iter():
                if item.tag in ('input', 'select'):
                    item.set('disabled', 'disabled')
            for a in form.iter('a'):
                if 's_website_form_send' in a.get('class', ''):
                    a.set('href', 'https://uno360x.com/#contacto')
                    a.set('target', '_blank')
                    a.set('rel', 'noopener')
                    a.text = 'Solicitar demo en el sitio público'
            note = ET.Element('p', {'class': 'fineprint'})
            note.text = 'Formulario ilustrativo en laboratorio. No envía solicitudes a producción.'
            form.insert(0, note)
    else:
        # Keep the existing Base + options picker and give it a trial action.
        for element in root.iter('a'):
            if 'p-' in element.get('class', '') and element.get('href') in ('/#contacto', '#contacto'):
                element.set('href', '/prueba')
                element.set('data-trial', 'true')
                element.text = 'Probar gratis por 15 días'
        # A separate explicit CTA works even when the original summary link changes.
        intro = next(e for e in root.iter() if 'p-intro' in e.get('class', '').split())
        intro.append(ET.fromstring('<p><a class="button" href="/prueba" data-trial="true">Probar gratis por 15 días</a></p>'))
        summary = next(e for e in root.iter() if 'p-summary' in e.get('class', '').split())
        summary.append(ET.fromstring('<p><a class="u-btn" href="/prueba" data-trial="true">Probar gratis por 15 días</a></p>'))
    html = ET.tostring(root, encoding='unicode', method='html')
    title = 'Inicio' if kind == 'homepage' else 'Planes y precios'
    scripts = '<script src="/assets/plans.js" defer></script>' if kind == 'plans' else ''
    return f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>{title} | UNO360X · Laboratorio</title><link rel="stylesheet" href="/assets/app.css">{scripts}<style>#uno360x-public .u-footer .u-wordmark{{color:#fff}}#uno360x-public .site-nav .button{{color:#fff}}#uno360x-public .home-trial .button{{color:#fff}}#uno360x-public .u-wordmark:after{{content:'◯';color:currentColor;margin-left:10px}}</style></head><body><div class="lab-notice">Laboratorio privado · Datos de prueba · Sin cargos ni correo real</div>{html}</body></html>'''


def asset(path):
    if path in ('/assets/app.css', '/assets/app.js'):
        name = path.rsplit('/', 1)[1]
        return ('text/css' if name.endswith('.css') else 'text/javascript'), (WEB / name).read_bytes()
    if path == '/assets/plans.js':
        scripts = '\n'.join(e.text or '' for e in snapshot('plans').iter('script'))
        scripts += '''\ndocument.querySelectorAll('[data-trial]').forEach(a=>a.addEventListener('click',()=>{const modules=Array.from(document.querySelectorAll('[data-module]:checked'),e=>({'Nómina y RR. HH.':'payroll_hr','Jenifer IA':'jenifer_ai','Proyectos y Servicios':'projects_services'}[e.dataset.module])).filter(Boolean);sessionStorage.setItem('uno-trial-draft',JSON.stringify({name:'',email:'',modules}));}));'''
        return 'text/javascript', scripts.encode()
    if path == '/':
        return 'text/html', public_page('homepage').encode()
    if path == '/planes-y-precios':
        return 'text/html', public_page('plans').encode()
    if path in APP_ROUTES:
        return 'text/html', (WEB / 'app.html').read_text(encoding='utf-8').replace('{{NAV}}', nav()).encode()
    if path in ('/condiciones', '/privacidad'):
        title = 'Condiciones de la prueba de laboratorio' if path == '/condiciones' else 'Privacidad del laboratorio'
        content = ('Esta versión se utiliza con datos ficticios para probar el recorrido. La prueba dura 15 días desde la preparación del espacio, no requiere tarjeta y no genera cargos. No es una contratación comercial. Los precios, límites y términos comerciales deben definirse antes del lanzamiento.'
                   if path == '/condiciones' else 'Usa únicamente información ficticia en este laboratorio. Los datos de registro se guardan localmente; las contraseñas se almacenan con hash. Los enlaces de verificación se entregan a un buzón privado local, sin correo real. No se comparten datos con producción. La política comercial y el plazo de conservación se definirán antes del lanzamiento.')
        return 'text/html', f'<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} | UNO360X</title><link rel="stylesheet" href="/assets/app.css"><body><div class="page-shell">{nav()}<main class="legal"><h1>{title}</h1><p>{content}</p><a href="/prueba/cuenta">Volver al registro</a></main></div></body></html>'.encode()
    return None

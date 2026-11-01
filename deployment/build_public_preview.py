"""Build a browser-only preview from the approved master UI. No real signup API."""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]

MOCK=r'''
const previewState={authenticated:false,email:'persona@example.test',name:'Mi empresa de ejemplo',modules:[],created:false,polls:0};
window.UNO360X_PREVIEW_API=async function(path,options={}){
 const data=options.body?JSON.parse(options.body):{};let result={},status=200;
 switch(path){
 case '/session':if(!previewState.authenticated){status=401;result={error:'Vista previa sin sesión.'};}else result={email:previewState.email,csrf_token:'preview'};break;
 case '/trial/register':previewState.email=data.email;previewState.modules=data.modules;result={message:'Correo simulado. No se envía ningún mensaje.'};break;
 case '/verify':result={verified:true};break;
 case '/login':previewState.authenticated=true;previewState.email=data.email;result={csrf_token:'preview'};break;
 case '/logout':previewState.authenticated=false;result={logged_out:true};break;
 case '/trial/draft':result={name:'',modules:previewState.modules};break;
 case '/companies':result={companies:previewState.created?[{id:'preview-company',name:previewState.name,slug:'empresa-ejemplo',role:'owner'}]:[]};break;
 case '/trial/create':previewState.name=data.name;previewState.modules=data.modules;previewState.created=true;result={tenant_id:'preview-company',status:'queued'};break;
 case '/trial/status':{
   const ready=++previewState.polls>1;
   result={tenant_id:'preview-company',name:previewState.name,country:'DO',currency:'DOP',modules:previewState.modules,is_trial:true,
     status:ready?'ready_local':'running',completed_steps:ready?['network','database','installation','identity','validation']:['network'],
     local_ready:ready,trial_active:ready,days_remaining:ready?15:null,started:ready?Date.now()/1000:null,expires:ready?Date.now()/1000+15*86400:null};break;
 }
 case '/setup/status':result={fiscal_emission_enabled:false};break;
 case '/reset/request':result={message:'Recuperación simulada: no se envía correo.'};break;
 default:status=400;result={error:'Esta acción no está disponible en la vista previa.'};
 }
 return {ok:status>=200&&status<300,status,json:async()=>result};
};
'''


def build(destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    web=ROOT/'control/web'
    source=(web/'app.js').read_text(encoding='utf-8')
    assert source.count('await fetch(path,')==1
    source=source.replace('await fetch(path,','await window.UNO360X_PREVIEW_API(path,')
    source=source.replace('uno-trial-draft','uno-preview-draft')
    source=source.replace("history.pushState({},'',path)","history.pushState({},'','#pantalla='+encodeURIComponent(path))")
    source=source.replace('const path=location.pathname;',"const path=new URLSearchParams(location.hash.slice(1)).get('pantalla')||'/prueba';")
    source=source.replace("secret=params.get('token')||'';if(location.hash)history.replaceState({},'',location.pathname);", "secret='preview-confirmation';")
    source=source.replace("document.title='Prueba gratis | UNO360X'", "document.title='Vista previa del registro | UNO360X'")
    source=source.replace("$('#enter-space').onclick=()=>openOdoo(tenantId);", "$('#enter-space').onclick=()=>go('/prueba/espacio');")
    source=source.split('\nasync function openOdoo(')[0]+"\nasync function openOdoo(){message('Vista previa: no se ha creado una empresa real.');}\n"
    # The preview must never request or collect a real password.
    signature="function field(name,label,placeholder,type='text',value='',attrs=''){"
    assert signature in source
    source=source.replace(signature,signature+"if(type==='password')return '<p class=\"fineprint\">Acceso simulado. No se solicita tu contraseña real.</p><input type=\"hidden\" name=\"password\" value=\"preview\">';")
    start=source.index('function passwordFields(){');end=source.index('\nfunction authBrand()',start)
    source=source[:start]+'''function passwordFields(){return '<p>En el registro real definirás aquí tu contraseña. Esta vista previa no solicita contraseñas.</p><input type="hidden" name="password" value="preview"><input type="hidden" name="confirm" value="preview">';}'''+source[end:]
    source=source.replace("$('#resend').onclick=async e=>", "const next=document.createElement('button');next.className='primary';next.textContent='Simular confirmación de correo';next.onclick=()=>go('/prueba/confirmar');$('#screen').querySelector('section').append(next);$('#resend').onclick=async e=>")
    source=source.replace('En este laboratorio no enviamos correo real. El enlace se guarda en el buzón privado del equipo para las pruebas.',
                          'Vista previa: no se envían correos. Pulsa Simular confirmación de correo para continuar.')
    source=source.replace('¡Tu empresa está lista!','Así se verá tu empresa lista')
    source=source.replace('Acceso de laboratorio. Tus datos y permisos se comprueban al entrar.','Simulación del diseño: no se creó una empresa real.')
    source=source.replace('Preparada en laboratorio','Módulo de ejemplo').replace('Preparado en laboratorio','Módulo de ejemplo')
    source=source.replace('Vista inicial de tu empresa en laboratorio. El acceso a Odoo pasa por el control de sesiones de UNO360X.',
                          'Vista previa de la configuración elegida. No es una sesión de Odoo ni una empresa real.')
    source=source.replace('Correo confirmado. Inicia sesión para continuar con tu empresa.','Confirmación simulada. Continúa con el acceso de ejemplo.')
    source=source.replace('<span>Acepto las <a href="/condiciones" target="_blank" rel="noopener">condiciones de la prueba de laboratorio</a> y he leído la <a href="/privacidad" target="_blank" rel="noopener">información de privacidad</a>.</span>',
                          '<span>Entiendo que es una simulación y usaré solo datos ficticios.</span>')
    source=source.replace('Esta pantalla avanza cuando el trabajador local completa la preparación.','Esta pantalla simula la preparación. No se ejecuta ningún alta real.')
    assert 'await fetch(' not in source and '127.0.0.1' not in source
    js='(()=>{\n'+MOCK+'\n'+source+'\n})();\n'
    css=(web/'app.css').read_text(encoding='utf-8')+'''
body:has(#uno360x-preview) #wrapwrap>header,body:has(#uno360x-preview) #wrapwrap>footer{display:none!important}
#uno360x-preview{background:white}#uno360x-preview .lab-notice{position:sticky;top:0;z-index:50;background:#e5f3ee;color:#22584e;font-size:12px;padding:10px}
#uno360x-preview #open-odoo{display:none}
'''
    nav=(web/'nav.html').read_text(encoding='utf-8')
    body=(web/'app.html').read_text(encoding='utf-8').split('<body>',1)[1].split('</body>',1)[0].replace('{{NAV}}',nav)
    body=body.replace('Laboratorio privado · Datos de prueba · Sin cargos ni correo real',
                      'VISTA PREVIA · Usa datos ficticios. No crea cuentas ni empresas reales, no pide contraseñas y no envía correos.')
    body=body.replace('<a href="/condiciones">Condiciones de la prueba</a><a href="/privacidad">Privacidad</a>',
                      '<span>Solo simulación del diseño aprobado</span><a href="/">Volver al inicio</a>')
    arch='''<t t-name="uno360x.signup_preview_public"><t t-call="website.layout"><t t-set="additional_title">Vista previa del registro | UNO360X</t><t t-set="no_index" t-value="True"/><div id="wrap"><div id="uno360x-preview"><link rel="stylesheet" href="__CSS_URL__"/>'''+body+'''<script src="__JS_URL__" defer="defer"></script></div></div></t></t>'''
    # HTML void tags to XML-compatible syntax before a QWeb write.
    arch=arch.replace(' hidden>', ' hidden="hidden">')
    ET.fromstring(arch)
    (destination/'preview.js').write_text(js,encoding='utf-8')
    (destination/'preview.css').write_text(css,encoding='utf-8')
    (destination/'preview.xml').write_text(arch,encoding='utf-8')
    manifest={'source':'master control/web','mode':'browser_only_simulation','real_accounts_created':False,
              'real_password_inputs':False,'real_mail_sent':False,'files':{name:hashlib.sha256((destination/name).read_bytes()).hexdigest() for name in ('preview.js','preview.css','preview.xml')}}
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    print(json.dumps(build(args.output),indent=2))

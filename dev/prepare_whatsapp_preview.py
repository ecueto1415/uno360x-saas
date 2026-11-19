"""Package exported QWeb views as local, read-only design snapshots.

No real invoices, credentials, API calls or server-side mutations in this viewer.
"""
from pathlib import Path
import re
import shutil
import sys

root=Path(__file__).resolve().parents[1]
output=Path(sys.argv[1]).resolve()
assets=output/'assets';assets.mkdir(exist_ok=True)
names=['workspace.css','extra.css','reference.css','areas.css','brand_orbit.css']
for name in names:
    shutil.copyfile(root/'addons/uno360x_workspace/static/src/css'/name,assets/name)
shutil.copyfile(root/'addons/uno360x_whatsapp/static/collections.css',assets/'collections.css')
css=''.join(f'<link rel="stylesheet" href="assets/{name}">' for name in names+['collections.css'])
for file in output.glob('*.html'):
    text=file.read_text(encoding='utf-8')
    text=re.sub(r'<script\b[^>]*>.*?</script>','',text,flags=re.S|re.I)
    text=re.sub(r'<link\b[^>]*>','',text,flags=re.I)
    text=re.sub(r'\sdata-navigation="1"','',text)
    def link(match):
        url=match[1]
        if '/configuracion' in url:target='configuration.html'
        elif '/cliente/' in url:target='customer.html'
        elif '/factura/' in url:target='review.html'
        elif '/aviso/' in url:target='reminder.html'
        elif '/cobros/whatsapp' in url:target='home.html'
        else:target='#'
        return 'href="'+target+'"'
    text=re.sub(r'href="([^"]*)"',link,text)
    text=text.replace('</head>',css+'''<meta http-equiv="Content-Security-Policy" content="default-src 'self' data:; script-src 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'none'; form-action 'none'"><style>.wa-prototype{font-size:12px;color:#526e79;background:#eaf1f4;padding:10px 14px;border-radius:8px}</style></head>''')
    text=text.replace('<main class="wa-page">','<main class="wa-page"><p class="wa-prototype">Vista de consulta del laboratorio. Datos y números fiscales ficticios, no emitidos. Los botones de guardado no operan en esta copia del diseño.</p>')
    text=text.replace('</body>',"""<script>document.querySelectorAll('form').forEach(f=>f.addEventListener('submit',e=>{e.preventDefault();alert('Esta copia muestra el diseño. El guardado y la simulación se validaron en Odoo del laboratorio; aquí no se envían mensajes.')}))</script></body>""")
    file.write_text(text,encoding='utf-8')
shutil.copyfile(output/'home.html',output/'index.html')
print('READ_ONLY_WHATSAPP_PREVIEW_READY',output)

"""Small, reversible homepage addition matching the approved trial design."""
import re
import xml.etree.ElementTree as ET

STYLE='''<style id="uno360x-home-trial-style">
#uno360x-public .u-trial-start{display:flex;gap:18px;align-items:center;justify-content:space-between;padding:18px;background:#1b3546;border-radius:12px;margin-top:25px}
#uno360x-public .u-trial-start strong{display:block;color:#fff;font-size:17px;line-height:1.45}
#uno360x-public .u-trial-start small{display:block;color:#a9dcd4;font-size:12px;margin-top:6px}
#uno360x-public .u-trial-start .u-btn{flex-shrink:0;white-space:nowrap;background:#12877c;border-color:#12877c}
#uno360x-public .u-trial-preview-note{font-size:10px;color:#a5b8ce;margin:10px 0 0;line-height:1.6}
@media(max-width:760px){#uno360x-public .u-trial-start{flex-direction:column;align-items:stretch;gap:17px}#uno360x-public .u-trial-start .u-btn{width:100%;white-space:normal}}
</style>'''
BANNER='''<div class="u-trial-start" id="uno360x-home-trial"><div><strong>15 días gratis para conocer UNO360X</strong><small>Sin tarjeta de crédito.</small></div><a class="u-btn" href="/prueba-saas" aria-label="Probar gratis por 15 días: vista previa del recorrido">Probar gratis por 15 días</a></div><p class="u-trial-preview-note u-note">Vista previa del recorrido. Usa datos ficticios; todavía no crea una cuenta real.</p>'''


def add_trial(original):
    root=ET.fromstring(original)
    assert not any(e.get('id')=='uno360x-home-trial' for e in root.iter()), 'La portada ya tiene un bloque de prueba; revisar antes de repetir.'
    assert any(e.get('id')=='uno360x-public' for e in root.iter()), 'Portada no reconocida.'
    hero=next(e for e in root.iter() if e.get('class')=='u-hero-copy')
    assert len([e for e in hero if e.get('class')=='u-note'])==1
    notes=list(re.finditer(r'<p\b[^>]*class="u-note"[^>]*>.*?</p>',original,re.S))
    assert len(notes)==1 and '</style>' in original
    note=notes[0]
    updated=original[:note.end()]+BANNER+original[note.end():]
    updated=updated.replace('</style>','</style>'+STYLE,1)
    ET.fromstring(updated)
    assert updated.replace(STYLE,'',1).replace(BANNER,'',1)==original
    return updated

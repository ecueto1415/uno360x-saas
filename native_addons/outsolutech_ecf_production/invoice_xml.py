"""Preserve detailed invoice labels in the official optional description field."""
from copy import deepcopy
from lxml import etree
from odoo.addons.outsolutech_ecf_flujo.builder import build_invoice as base_build, text, validate_preliminary


def build_invoice(data, encf):
    normalized=deepcopy(data)
    descriptions={}
    for index, row in enumerate(normalized['lines']):
        original=str(row.get('name') or '').strip()
        if len(original)>80:
            descriptions[index]=text(original,'Descripcion de item',1000)
            row['name']=original.splitlines()[0].strip()[:80]
    root=etree.fromstring(base_build(normalized,encf))
    items=root.findall('DetallesItems/Item')
    for index, description in descriptions.items():
        node=etree.Element('DescripcionItem');node.text=description
        items[index].find('IndicadorBienoServicio').addnext(node)
    xml=etree.tostring(root,encoding='UTF-8',xml_declaration=True)
    validate_preliminary(xml,str(data.get('document_type','31')))
    return xml

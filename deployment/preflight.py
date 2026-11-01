"""Offline deployment preparation checks. Never connects, pays or deploys.

Checks configuration shape, separation from the operational server, and the
existing release gate. A valid declaration is not infrastructure verification.
"""
import argparse
import ipaddress
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
PROTECTED_ADDRESSES={ipaddress.ip_address('140.82.47.80')}
FIELDS={'environment','server_address','server_provider','monthly_budget_usd',
        'central_origin','tenant_domain','smtp_config_path','external_backup_destination'}

def saas_domain(value):
    return isinstance(value,str) and len(value)<=253 and bool(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*\.uno360x\.com',value))


def inspect(config, readiness):
    issues=[]
    if not isinstance(config,dict) or set(config)!=FIELDS:
        return {'configuration_complete':False,'deployment_allowed':False,'issues':['Esquema de configuración inválido.'],'external_state_verified':False}
    if config['environment']!='isolated_pilot':issues.append('Solo se admite un piloto separado.')
    try:
        address=ipaddress.ip_address(config['server_address'])
        if address in PROTECTED_ADDRESSES:issues.append('Objetivo rechazado: servidor operativo de OUTSOLUTECH.')
        elif not address.is_global:issues.append('Se requiere la IP pública del servidor nuevo.')
    except (ValueError,TypeError):issues.append('Falta la IP del servidor separado.')
    if not isinstance(config['server_provider'],str) or not config['server_provider'].strip():issues.append('Falta identificar el proveedor del servidor.')
    budget=config['monthly_budget_usd']
    if isinstance(budget,bool) or not isinstance(budget,(int,float)) or not 0<budget<=100000:
        issues.append('Falta el presupuesto mensual máximo aprobado.')
    origin=config['central_origin']
    try:
        url=urlsplit(origin)
        host=url.hostname
        if url.scheme!='https' or not saas_domain(host) or url.username or url.password or url.port not in (None,443) or url.path not in ('','/') or url.query or url.fragment:
            raise ValueError()
        if host in ('www.uno360x.com','outsolutech.uno360x.com'):raise ValueError()
    except (ValueError,TypeError,AttributeError):issues.append('Falta un origen HTTPS exclusivo para el acceso SaaS.')
    tenant=config['tenant_domain']
    if not saas_domain(tenant) or tenant in ('www.uno360x.com','outsolutech.uno360x.com'):
        issues.append('Falta el dominio independiente para las empresas del piloto.')
    elif isinstance(origin,str) and tenant==urlsplit(origin).hostname:
        issues.append('El dominio de empresas debe distinguirse del acceso central.')
    if not isinstance(config['smtp_config_path'],str) or not config['smtp_config_path'].strip():
        issues.append('Falta la referencia al archivo privado del correo nuevo.')
    if not isinstance(config['external_backup_destination'],str) or not config['external_backup_destination'].strip():
        issues.append('Falta el destino externo de respaldos.')
    return {'configuration_complete':not issues,'deployment_allowed':False,
            'issues':issues,'external_state_verified':False,
            'release_gate_open':readiness.get('public_release_allowed') is True,
            'remaining_product_requirements':readiness.get('required_before_public_release',[]),
            'note':'Solo comprobación offline. No acredita DNS, TLS, capacidad, propiedad del host, correo ni aptitud comercial.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    try:
        config=json.loads(args.config.read_text(encoding='utf-8'))
        readiness=json.loads((ROOT/'product/readiness.json').read_text(encoding='utf-8'))
        report=inspect(config,readiness)
    except (OSError,ValueError):
        raise SystemExit('No se pudo leer la configuración de preparación.') from None
    encoded=json.dumps(report,indent=2,ensure_ascii=False)+'\n'
    if args.output:args.output.write_text(encoded,encoding='utf-8')
    print(encoded,end='')
    return 0 if report['configuration_complete'] else 2


if __name__=='__main__':raise SystemExit(main())

"""Explicit independent SMTP transport. Disabled unless an operator configures it.

No discovery of existing mail credentials, no fallback to production SMTP.
"""
from email.message import EmailMessage
import json
import os
from pathlib import Path
import smtplib
import ssl
from urllib.parse import urlsplit

from .identity import email_key


class SMTPDelivery:
    def __init__(self, config):
        required = {'host','port','security','username','password','from_address','public_origin','independent_saas_mailbox'}
        if not isinstance(config,dict) or set(config)!=required or config['independent_saas_mailbox'] is not True:
            raise ValueError('Se requiere una configuración exclusiva de correo SaaS.')
        if not all(isinstance(config[k],str) and config[k] and '\r' not in config[k] and '\n' not in config[k]
                   for k in ('host','username','password','from_address','public_origin')):
            raise ValueError('Configuración de correo inválida.')
        if (config['security'],config['port']) not in (('ssl',465),('starttls',587)):
            raise ValueError('Solo SMTP autenticado con TLS verificado en 465 o 587.')
        sender=email_key(config['from_address'])
        if sender.split('@')[1]!='uno360x.com':
            raise ValueError('Se requiere un remitente nuevo de UNO360X.')
        origin=urlsplit(config['public_origin'])
        if origin.scheme!='https' or not origin.hostname or not (origin.hostname=='uno360x.com' or origin.hostname.endswith('.uno360x.com')) or origin.port not in (None,443) or origin.username or origin.password or origin.path not in ('','/') or origin.query or origin.fragment:
            raise ValueError('Se requiere el origen HTTPS definitivo de UNO360X.')
        self.config=dict(config,from_address=sender,public_origin=config['public_origin'].rstrip('/'))

    @classmethod
    def from_file(cls, path):
        path=Path(path)
        if path.is_symlink():raise ValueError('Configuración de correo no válida.')
        if os.name=='posix':
            info=path.stat()
            if info.st_uid!=os.geteuid() or info.st_mode & 0o077:
                raise ValueError('La configuración de correo debe ser privada (0600).')
        return cls(json.loads(path.read_text(encoding='utf-8')))

    def __call__(self, notice):
        purpose=notice.get('purpose')
        if purpose not in ('verify','reset'):
            raise ValueError('Este transporte solo admite confirmación y recuperación.')
        recipient=email_key(notice['email'])
        if recipient.endswith(('.test','.invalid','.localhost')) or recipient.split('@')[1]=='localhost':
            raise ValueError('No se envían pruebas ficticias al proveedor real.')
        token=notice['token']
        if not isinstance(token,str) or not 32<=len(token)<=128 or any(ch not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for ch in token):
            raise ValueError('Enlace de correo inválido.')
        route='/prueba/confirmar' if purpose=='verify' else '/prueba/restablecer'
        subject='Confirma tu correo en UNO360X' if purpose=='verify' else 'Recupera tu acceso a UNO360X'
        message=EmailMessage();message['From']=self.config['from_address'];message['To']=recipient;message['Subject']=subject
        message.set_content(subject+'\n\nAbre este enlace para continuar:\n'+self.config['public_origin']+route+'#token='+token+
                            '\n\nEl enlace es personal, temporal y de un solo uso. Si no hiciste esta solicitud, ignora este correo.\n\nUNO360X\n')
        context=ssl.create_default_context()
        if self.config['security']=='ssl':
            transport=smtplib.SMTP_SSL(self.config['host'],465,timeout=20,context=context)
        else:
            transport=smtplib.SMTP(self.config['host'],587,timeout=20)
        with transport as client:
            if self.config['security']=='starttls':
                client.ehlo();client.starttls(context=context);client.ehlo()
            client.login(self.config['username'],self.config['password'])
            client.send_message(message)

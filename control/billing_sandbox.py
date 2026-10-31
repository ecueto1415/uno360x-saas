"""Subscription lifecycle rehearsal. No provider, cards, charges or real prices."""
import hashlib
import hmac
import json
import uuid
from .identity import IdentityError

class SandboxBilling:
    def __init__(self,identity,webhook_key,pricebook=None):
        if len(webhook_key)!=32:raise ValueError('Clave de sandbox inválida.')
        self.identity=identity;self.db=identity.db;self.key=webhook_key;self.pricebook=pricebook
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS sandbox_checkouts (
            id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL REFERENCES tenants(id),
            request_key TEXT UNIQUE NOT NULL,amount INTEGER NOT NULL,currency TEXT NOT NULL,
            quote TEXT NOT NULL,state TEXT NOT NULL,expires REAL
          );
          CREATE TABLE IF NOT EXISTS sandbox_payment_events (
            id TEXT PRIMARY KEY,digest TEXT NOT NULL,checkout_id TEXT NOT NULL REFERENCES sandbox_checkouts(id)
          );
        ''')
    def quote(self,session,tenant_id):
        account=self.identity._account(session);membership=self.identity._membership(account['id'],tenant_id)
        if membership['role']!='owner':raise IdentityError('Solo el propietario configura la suscripción.')
        if not self.pricebook:return {'price_status':'undefined','real_payment':False}
        modules=json.loads(self.db.execute('SELECT modules FROM tenants WHERE id=?',(tenant_id,)).fetchone()[0])
        names=['business_base']+modules;amount=0
        for name in names:
            value=self.pricebook['prices'].get(name)
            if type(value) is not int or value<0:raise ValueError('Precio no definido.')
            amount+=value
        currency=self.pricebook['currency']
        if currency not in ('DOP','USD') or amount<=0:raise ValueError('Cotización de prueba inválida.')
        return {'price_status':'synthetic_sandbox','amount_minor':amount,'currency':currency,'modules':names,'real_payment':False}
    def checkout(self,session,tenant_id,request_key):
        if not isinstance(request_key,str) or not 1<=len(request_key)<=128:raise ValueError('Solicitud inválida.')
        quote=self.quote(session,tenant_id)
        if quote['price_status']=='undefined':raise ValueError('Los precios siguen por definir.')
        key=hashlib.sha256((tenant_id+':'+request_key).encode()).hexdigest();encoded=json.dumps(quote,sort_keys=True)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            old=self.db.execute('SELECT * FROM sandbox_checkouts WHERE request_key=?',(key,)).fetchone()
            if old:
                if old['quote']!=encoded:raise ValueError('Solicitud repetida con cotización distinta.')
                return {'checkout_id':old['id'],'real_payment':False}
            cid=uuid.uuid4().hex
            self.db.execute("INSERT INTO sandbox_checkouts VALUES (?,?,?,?,?,?,'pending',NULL)",(cid,tenant_id,key,quote['amount_minor'],quote['currency'],encoded))
        return {'checkout_id':cid,'real_payment':False}
    def receive(self,body,signature):
        if not isinstance(body,bytes) or len(body)>4096 or not isinstance(signature,str):raise ValueError('Evento inválido.')
        if not hmac.compare_digest(hmac.new(self.key,body,hashlib.sha256).hexdigest(),signature):raise ValueError('Firma inválida.')
        data=json.loads(body)
        if set(data)!={'event_id','checkout_id','status','amount_minor','currency','period_seconds','sandbox'} or data['sandbox'] is not True:raise ValueError('Solo eventos sandbox.')
        if not isinstance(data['event_id'],str) or not 1<=len(data['event_id'])<=128:raise ValueError('ID de evento inválido.')
        if data['status'] not in ('paid','failed','cancelled','refunded') or type(data['period_seconds']) is not int or not 1<=data['period_seconds']<=366*86400:raise ValueError('Estado inválido.')
        fingerprint=hashlib.sha256(body).hexdigest()
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            prior=self.db.execute('SELECT digest FROM sandbox_payment_events WHERE id=?',(data['event_id'],)).fetchone()
            if prior:
                if prior['digest']!=fingerprint:raise ValueError('Evento repetido con datos distintos.')
                return {'accepted':True,'duplicate':True,'real_payment':False}
            checkout=self.db.execute('SELECT * FROM sandbox_checkouts WHERE id=?',(data['checkout_id'],)).fetchone()
            if not checkout or type(data['amount_minor']) is not int or data['amount_minor']!=checkout['amount'] or data['currency']!=checkout['currency']:raise ValueError('Importe o moneda no corresponden.')
            state=checkout['state'];expires=checkout['expires']
            if data['status']=='refunded':state='refunded'
            elif data['status']=='paid' and state!='refunded':
                if state!='active':expires=self.identity.clock()+data['period_seconds']
                state='active'
            elif state=='pending':state='cancelled'
            self.db.execute('UPDATE sandbox_checkouts SET state=?,expires=? WHERE id=?',(state,expires,checkout['id']))
            self.db.execute('INSERT INTO sandbox_payment_events VALUES (?,?,?)',(data['event_id'],fingerprint,checkout['id']))
            self.identity._audit('sandbox_payment_event',tenant=checkout['tenant_id'])
        return {'accepted':True,'duplicate':False,'real_payment':False}
    def entitlement(self,session,tenant_id):
        account=self.identity._account(session);self.identity._membership(account['id'],tenant_id)
        row=self.db.execute("SELECT 1 FROM sandbox_checkouts WHERE tenant_id=? AND state='active' AND expires>? LIMIT 1",(tenant_id,self.identity.clock())).fetchone()
        return {'sandbox_subscription_active':bool(row),'production_access_enabled':False,'real_payment':False}

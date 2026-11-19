"""Trusted operator import of existing subscription invoices, never payment processing.

Run locally on the SaaS server as root; no public invoice-creation endpoint exists.
Amounts are minor units; PDF is the already issued document, not a generated tax receipt.
"""
import argparse
import hashlib
import os
from pathlib import Path
import sqlite3
import time
import uuid
from control.subscription_store import Subscription
from types import SimpleNamespace

def import_invoice(db,tenant,number,total,currency,issued,due,pdf):
 if not db.execute('SELECT 1 FROM tenants WHERE id=?',(tenant,)).fetchone():raise ValueError('Empresa no disponible.')
 if not isinstance(number,str) or not 1<=len(number)<=80 or any(ord(ch)<32 for ch in number):raise ValueError('Número no válido.')
 if type(total) is not int or not 0<total<=10**12 or currency not in ('USD','DOP'):raise ValueError('Importe o moneda no válidos.')
 if not isinstance(pdf,bytes) or not pdf.startswith(b'%PDF-') or len(pdf)>5*1024*1024:raise ValueError('PDF no válido o mayor de 5 MB.')
 with db:
  db.execute('BEGIN IMMEDIATE')
  prior=db.execute('SELECT * FROM subscription_invoices WHERE tenant_id=? AND number=?',(tenant,number)).fetchone()
  if prior:
   if (prior['total_minor'],prior['currency'],prior['issued'],prior['due'],bytes(prior['pdf']))!=(total,currency,issued,due,pdf):raise ValueError('La factura ya existe con otros datos; no se modifica.')
   return prior['id']
  invoice=uuid.uuid4().hex
  db.execute("INSERT INTO subscription_invoices VALUES (?,?,?,?,?,?,?,'pending',?)",(invoice,tenant,number,issued,due,total,currency,pdf))
  db.execute('INSERT INTO subscription_audit(tenant_id,actor,event,created) VALUES (?,?,?,?)',(tenant,'operator','invoice_imported',time.time()))
 return invoice

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--database',default='/var/lib/uno360x-saas/control/control.sqlite3')
 parser.add_argument('--tenant',required=True)
 parser.add_argument('--number',required=True)
 parser.add_argument('--amount-minor',type=int,required=True)
 parser.add_argument('--currency',choices=['DOP','USD'],required=True)
 parser.add_argument('--issued',type=float,required=True)
 parser.add_argument('--due',type=float)
 parser.add_argument('--pdf',type=Path,required=True)
 args=parser.parse_args()
 if not hasattr(os,'geteuid') or os.geteuid()!=0:parser.error('Ejecutar localmente como operador root del SaaS.')
 db=sqlite3.connect(args.database);db.row_factory=sqlite3.Row
 try:
  Subscription(SimpleNamespace(db=db)).initialize()
  print(import_invoice(db,args.tenant,args.number,args.amount_minor,args.currency,args.issued,args.due,args.pdf.read_bytes()))
 finally:db.close()

if __name__=='__main__':main()

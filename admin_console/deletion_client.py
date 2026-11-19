"""Eligibility shared by the admin panel and the private deletion service."""
import json
import re
import socket

SOCKET = '/run/uno360x-test-deletion/delete.sock'


def is_test_company(name, email):
    if not isinstance(name, str) or not isinstance(email, str):
        return False
    if email in ('outsolutech@gmail.com', 'cuetoexpress@gmail.com'):
        return bool(re.fullmatch(r'PRUEBA .{1,140}', name, re.IGNORECASE))
    return bool(re.fullmatch(r'PRUEBA REAL20 [0-9]{2}', name) and
                re.fullmatch(r'notificaciones\+alta20-[a-f0-9]{8}-[0-9]{2}@uno360x\.com', email))


def request_deletion(tenant_id, email):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(75)
        client.connect(SOCKET)
        client.sendall(json.dumps({'tenant_id': tenant_id, 'email': email}).encode() + b'\n')
        with client.makefile('rb') as stream:
            return json.loads(stream.readline(1024))

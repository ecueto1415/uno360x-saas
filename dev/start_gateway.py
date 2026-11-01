"""Trusted loopback gateway broker, isolated WSL lab only."""
import fcntl
import json
from multiprocessing.connection import Listener
import os
from pathlib import Path
import socket
import stat
import struct
import sys
import threading

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from auto_adapter import LocalAdapter
from control_state import control_database
from control.gateway import GatewayManager
from control.gateway_ipc import SOCKET


def main():
    adapter=LocalAdapter();os.umask(0o077);database=control_database()
    manager=GatewayManager(database,adapter)
    def handle(connection):
        try:
            with connection:
                with socket.fromfd(connection.fileno(),socket.AF_UNIX,socket.SOCK_STREAM) as peer:
                    _,uid,_=struct.unpack('3i',peer.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                    if uid!=os.geteuid():return
                if not connection.poll(5):return
                data=json.loads(connection.recv_bytes(4096))
                if not isinstance(data,dict) or set(data)!={'session','ticket'}:raise ValueError()
                result=manager.launch(data['session'],data['ticket'])
                connection.send_bytes(json.dumps(result).encode())
        except Exception:
            try:connection.send_bytes(b'{"error":"Acceso local no disponible."}')
            except Exception:pass
    with (SOCKET.parent/'gateway.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if SOCKET.exists():
            info=SOCKET.lstat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid!=os.geteuid():raise RuntimeError('Ruta de socket inesperada.')
            SOCKET.unlink()
        listener=Listener(str(SOCKET),family='AF_UNIX');os.chmod(SOCKET,0o600)
        print('Broker local iniciado. Sin puertos públicos ni cookies Odoo en el navegador.',flush=True)
        try:
            while True:
                connection=listener.accept()
                threading.Thread(target=handle,args=(connection,),daemon=True).start()
        except KeyboardInterrupt:pass
        finally:
            listener.close();manager.close();SOCKET.unlink(missing_ok=True)


if __name__=='__main__':main()

"""Loopback-only TCP relay for the internal Podman network in WSL.

No authentication or TLS: development only, never bind a public address.
The target is supplied by the lab launcher, never by an incoming request.
"""
import argparse
import select
import socket
import socketserver

parser = argparse.ArgumentParser()
parser.add_argument('--target', required=True)
args = parser.parse_args()


class Relay(socketserver.BaseRequestHandler):
    def handle(self):
        with socket.create_connection((args.target, 8069), timeout=10) as backend:
            sockets = [self.request, backend]
            while True:
                ready, _, _ = select.select(sockets, [], [], 60)
                if not ready:
                    return
                for source in ready:
                    data = source.recv(65536)
                    if not data:
                        return
                    (backend if source is self.request else self.request).sendall(data)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


with Server(('127.0.0.1', 18069), Relay) as server:
    server.serve_forever()

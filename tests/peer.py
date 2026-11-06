#!/usr/bin/env python3
"""Socket peer for isolated QEMU/network-namespace integration tests."""
import argparse
import json
import socket
import socketserver
import threading
import time
import uuid


class Peer:
    def __init__(self, address):
        self.address = address
        self.udp = {}
        self.received = {}
        self.connections = []
        self.listeners = []
        self.lock = threading.Lock()

    def udp_open(self, port, address=None):
        address = address or self.address
        sock = socket.socket(socket.AF_INET6 if ':' in address else socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((address, port))
        self.udp[port] = sock
        self.received[port] = []

        def receive():
            while True:
                data, remote = sock.recvfrom(65535)
                if data.startswith(b'probe:'):
                    sock.sendto(json.dumps({'token': data.decode(), 'observed': list(remote[:2])}).encode(), remote)
                else:
                    with self.lock:
                        self.received[port].append((data.decode(), list(remote[:2])))
        threading.Thread(target=receive, daemon=True).start()
        return True

    def udp_probe(self, port, destination, timeout=2):
        token = 'probe:' + uuid.uuid4().hex
        self.udp[port].sendto(token.encode(), tuple(destination))
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self.lock:
                for index, (data, remote) in enumerate(self.received[port]):
                    value = json.loads(data)
                    if value.get('token') == token:
                        self.received[port].pop(index)
                        return {'observed': value['observed'], 'responder': remote}
            time.sleep(.01)
        raise TimeoutError('UDP probe received no matching response')

    @staticmethod
    def configure(sock):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

    def tcp_listen(self, port):
        sock = socket.socket()
        self.configure(sock)
        sock.bind((self.address, port))
        sock.listen(64)
        self.listeners.append(sock)

        def session(client, remote):
            try:
                client.sendall(json.dumps({'observed': list(remote)}).encode() + b'\n')
                while True:
                    data = client.recv(65536)
                    if not data:
                        break
                    client.sendall(data)
            except (OSError, ConnectionError):
                pass
            finally:
                client.close()

        def accept():
            while True:
                client, remote = sock.accept()
                threading.Thread(target=session, args=(client, remote), daemon=True).start()
        threading.Thread(target=accept, daemon=True).start()
        return True

    def tcp_probe(self, port, destination, timeout=3):
        sock = socket.socket()
        self.configure(sock)
        sock.settimeout(timeout)
        sock.bind((self.address, port))
        try:
            sock.connect(tuple(destination))
            line = b''
            while not line.endswith(b'\n'):
                part = sock.recv(1)
                if not part:
                    raise RuntimeError('Peer closed before greeting')
                line += part
            observed = json.loads(line)['observed']
            payload = (uuid.uuid4().hex * 1024).encode()
            sock.sendall(payload)
            response = b''
            while len(response) < len(payload):
                part = sock.recv(len(payload) - len(response))
                if not part:
                    raise RuntimeError('Truncated TCP payload')
                response += part
            if response != payload:
                raise AssertionError('TCP bidirectional payload differs')
            self.connections.append(sock)
            return {'observed': observed, 'bytes_each_direction': len(payload)}
        except BaseException:
            sock.close()
            raise

    def tcp_close_all(self):
        for sock in self.connections:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()
        self.connections.clear()
        return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('control')
    parser.add_argument('address')
    args = parser.parse_args()
    peer = Peer(args.address)

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            try:
                request = json.loads(self.rfile.readline())
                method = request.pop('method')
                if method not in ('udp_open', 'udp_probe', 'tcp_listen', 'tcp_probe', 'tcp_close_all'):
                    raise ValueError('Unknown test method')
                value = getattr(peer, method)(**request)
                result = {'ok': True, 'value': value}
            except Exception as exc:
                result = {'ok': False, 'error': type(exc).__name__, 'detail': str(exc)}
            self.wfile.write(json.dumps(result).encode() + b'\n')

    class ControlServer(socketserver.ThreadingUnixStreamServer):
        # The test launches 32 concurrent controllers; the default backlog of
        # five rejects local control connections before any NAT packet is sent.
        request_queue_size = 128

    with ControlServer(args.control, Handler) as server:
        server.daemon_threads = True
        server.serve_forever()


if __name__ == '__main__':
    main()


import socket
import os


def get_free_port() -> int:
    sock = socket.socket()
    sock.bind(('', 0))
    ip, port = sock.getsockname()
    sock.close()
    return port


def development_mode():
    return os.getenv('FLASK_DEBUG', '0') == '1'

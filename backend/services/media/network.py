"""Public-only HTTP networking for isolated yt-dlp processes."""
import ipaddress
import socket
from contextlib import contextmanager
from urllib.parse import urlsplit


def public_address(value):
    address = ipaddress.ip_address(value)
    if not address.is_global or (getattr(address, "ipv4_mapped", None) and not address.ipv4_mapped.is_global):
        raise OSError("Private and local network addresses are not allowed")
    return address


def validate_public_url(value):
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError()
        if parsed.port not in (None, 443 if parsed.scheme == "https" else 80):
            raise ValueError()
        try:
            ipaddress.ip_address(parsed.hostname)
        except ValueError:
            if parsed.hostname.lower().rstrip(".") in {"localhost", "localhost.localdomain"}:
                raise ValueError()
        else:
            public_address(parsed.hostname)
    except (OSError, ValueError) as exc:
        raise ValueError("Нужна публичная HTTP/HTTPS-ссылка без авторизации") from exc
    return value


@contextmanager
def public_network():
    """Guard redirects, fragments and actual connections, including DNS rebinding.

    This changes process globals: it MUST only be used by the isolated worker,
    never around requests in the API process.
    """
    resolve, connect, connect_ex = socket.getaddrinfo, socket.socket.connect, socket.socket.connect_ex

    def safe_resolve(*args, **kwargs):
        records = resolve(*args, **kwargs)
        if not records:
            raise OSError("No public address found")
        for record in records:
            public_address(record[4][0])
        return records

    def safe_connect(sock, address):
        if sock.family not in (socket.AF_INET, socket.AF_INET6):
            raise OSError("Only public IP connections are allowed")
        public_address(address[0])
        if address[1] not in (80, 443):
            raise OSError("Only HTTP/HTTPS ports are allowed")
        return connect(sock, address)

    def safe_connect_ex(sock, address):
        if sock.family not in (socket.AF_INET, socket.AF_INET6):
            raise OSError("Only public IP connections are allowed")
        public_address(address[0])
        if address[1] not in (80, 443):
            raise OSError("Only HTTP/HTTPS ports are allowed")
        return connect_ex(sock, address)

    socket.getaddrinfo, socket.socket.connect, socket.socket.connect_ex = safe_resolve, safe_connect, safe_connect_ex
    try:
        yield
    finally:
        socket.getaddrinfo, socket.socket.connect, socket.socket.connect_ex = resolve, connect, connect_ex

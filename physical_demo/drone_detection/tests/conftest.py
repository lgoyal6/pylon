import socket
import struct

import pytest

import config


@pytest.fixture
def multicast_listener():
    """Factory yielding UDP sockets joined to a multicast group (auto-closed)."""
    opened = []

    def _make(group: str = config.MCAST_GROUP, port: int = config.MCAST_PORT):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", port))
        mreq = struct.pack("4sl", socket.inet_aton(group), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.settimeout(2.0)
        opened.append(sock)
        return sock

    yield _make

    for sock in opened:
        sock.close()

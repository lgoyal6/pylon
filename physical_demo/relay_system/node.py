"""Peer-to-peer mesh node.

Multiple instances on the same machine or on the same LAN auto-discover each
other over UDP multicast and exchange direct unicast messages — no central
server. Standard library only.
"""

from __future__ import annotations

import argparse
import os
import random
import socket
import string
import struct
import sys
import threading
import time
import uuid
from collections import OrderedDict
from typing import Callable, Dict, Optional, Tuple

MCAST_GROUP = "239.1.1.1"
MCAST_PORT = 50000
HELLO_INTERVAL = 1.0
PEER_TIMEOUT = 5.0
RECV_BUF = 4096
SEEN_MAX = 4096  # cap on remembered message IDs (LRU eviction)

PeerInfo = Tuple[str, int, float]  # (ip, data_port, last_seen)


def _random_id(n: int = 6) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def _open_multicast_socket() -> Tuple[socket.socket, bool]:
    """Open the discovery socket, joined to the multicast group.

    Returns (socket, multicast_ok). Falls back to plain broadcast on the same
    port if joining the multicast group fails (e.g. multicast blocked).
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except OSError:
            pass
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("", MCAST_PORT))

    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

    try:
        mreq = struct.pack("4sl", socket.inet_aton(MCAST_GROUP), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        return sock, True
    except OSError as e:
        print(f"[warn] multicast join failed ({e}); falling back to broadcast")
        return sock, False


class Node:
    def __init__(
        self,
        node_id: Optional[str] = None,
        on_message: Optional[Callable[[str, str], None]] = None,
        sink: Optional[Tuple[str, int]] = None,
    ) -> None:
        self.node_id = node_id or _random_id()
        self.on_message: Callable[[str, str], None] = on_message or self._default_on_message
        self._sink: Optional[Tuple[str, int]] = sink

        # Data socket: ephemeral port for direct unicast messages.
        self._data_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._data_sock.bind(("", 0))
        self.data_port: int = self._data_sock.getsockname()[1]

        # Separate egress socket for local sink, so sink traffic never gets
        # confused with peer-to-peer datagrams arriving on the data port.
        self._sink_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self._disc_sock, self._mcast_ok = _open_multicast_socket()

        self._peers: Dict[str, PeerInfo] = {}
        self._peers_lock = threading.Lock()

        self._seen: "OrderedDict[str, float]" = OrderedDict()
        self._seen_lock = threading.Lock()

        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    # ---- public API ----------------------------------------------------

    def start(self) -> None:
        mode = "multicast" if self._mcast_ok else "broadcast-fallback"
        print(
            f"[{self.node_id}] up on data_port={self.data_port} "
            f"discovery={mode} group={MCAST_GROUP}:{MCAST_PORT}"
        )
        for target in (self._hello_loop, self._discovery_loop, self._data_loop, self._reaper_loop):
            t = threading.Thread(target=target, name=target.__name__, daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._stop.set()

    def peers(self) -> Dict[str, PeerInfo]:
        with self._peers_lock:
            return dict(self._peers)

    def broadcast(self, message: str) -> int:
        """Originate a new message: tag with a fresh UUID and fan it out.

        Returns the number of peers the message was sent to.
        """
        msg_id = uuid.uuid4().hex
        # Mark our own UUID seen so any echo back to us is dropped silently.
        self._mark_seen(msg_id)
        self._to_sink(self.node_id, message)
        return self._send_msg(msg_id, self.node_id, message)

    def set_sink(self, sink: Optional[Tuple[str, int]]) -> None:
        """Enable or disable local UDP sink forwarding."""
        self._sink = sink

    def _to_sink(self, origin_id: str, message: str) -> None:
        if self._sink is None:
            return
        try:
            self._sink_sock.sendto(f"{origin_id}|{message}".encode("utf-8"), self._sink)
        except OSError as e:
            print(f"[{self.node_id}] sink forward failed: {e}")

    def _send_msg(
        self,
        msg_id: str,
        origin_id: str,
        message: str,
        exclude_addr: Optional[Tuple[str, int]] = None,
    ) -> int:
        payload = f"MSG|{msg_id}|{origin_id}|{message}".encode("utf-8")
        sent = 0
        for _peer_id, (ip, port, _seen) in self.peers().items():
            if exclude_addr is not None and (ip, port) == exclude_addr:
                continue
            try:
                self._data_sock.sendto(payload, (ip, port))
                sent += 1
            except OSError as e:
                print(f"[{self.node_id}] send to {ip}:{port} failed: {e}")
        return sent

    def _mark_seen(self, msg_id: str) -> bool:
        """Record `msg_id`. Returns True if new, False if already seen."""
        with self._seen_lock:
            if msg_id in self._seen:
                self._seen.move_to_end(msg_id)
                return False
            self._seen[msg_id] = time.time()
            while len(self._seen) > SEEN_MAX:
                self._seen.popitem(last=False)
            return True

    # ---- internals -----------------------------------------------------

    def _default_on_message(self, sender_id: str, message: str) -> None:
        print(f"[{self.node_id}] <- {sender_id}: {message}")

    def _send_discovery(self, payload: bytes) -> None:
        try:
            if self._mcast_ok:
                self._disc_sock.sendto(payload, (MCAST_GROUP, MCAST_PORT))
            else:
                self._disc_sock.sendto(payload, ("255.255.255.255", MCAST_PORT))
        except OSError as e:
            print(f"[{self.node_id}] hello send failed: {e}")

    def _hello_loop(self) -> None:
        payload = f"HELLO|{self.node_id}|{self.data_port}".encode("utf-8")
        while not self._stop.is_set():
            self._send_discovery(payload)
            self._stop.wait(HELLO_INTERVAL)

    def _discovery_loop(self) -> None:
        self._disc_sock.settimeout(1.0)
        while not self._stop.is_set():
            try:
                data, addr = self._disc_sock.recvfrom(RECV_BUF)
            except socket.timeout:
                continue
            except OSError:
                if self._stop.is_set():
                    return
                continue
            try:
                parts = data.decode("utf-8").split("|", 2)
            except UnicodeDecodeError:
                continue
            if len(parts) < 3 or parts[0] != "HELLO":
                continue
            peer_id, port_str = parts[1], parts[2]
            if peer_id == self.node_id:
                continue
            try:
                port = int(port_str)
            except ValueError:
                continue
            now = time.time()
            with self._peers_lock:
                existed = peer_id in self._peers
                self._peers[peer_id] = (addr[0], port, now)
            if not existed:
                print(f"[{self.node_id}] + peer joined: {peer_id} @ {addr[0]}:{port}")

    def _data_loop(self) -> None:
        self._data_sock.settimeout(1.0)
        while not self._stop.is_set():
            try:
                data, addr = self._data_sock.recvfrom(RECV_BUF)
            except socket.timeout:
                continue
            except OSError:
                if self._stop.is_set():
                    return
                continue
            try:
                parts = data.decode("utf-8").split("|", 3)
            except UnicodeDecodeError:
                continue
            if len(parts) < 4 or parts[0] != "MSG":
                continue
            msg_id, origin_id, message = parts[1], parts[2], parts[3]
            if origin_id == self.node_id:
                continue  # our own message echoed back
            if not self._mark_seen(msg_id):
                continue  # duplicate — drop without re-forwarding
            self._to_sink(origin_id, message)
            try:
                self.on_message(origin_id, message)
            except Exception as e:  # callback shouldn't kill the listener
                print(f"[{self.node_id}] on_message error: {e}")
            # Re-forward to the rest of the mesh (gossip flooding); skip
            # the peer we got it from since it already has it.
            self._send_msg(msg_id, origin_id, message, exclude_addr=addr)

    def _reaper_loop(self) -> None:
        while not self._stop.is_set():
            self._stop.wait(1.0)
            now = time.time()
            dropped = []
            with self._peers_lock:
                for pid, (ip, port, seen) in list(self._peers.items()):
                    if now - seen > PEER_TIMEOUT:
                        del self._peers[pid]
                        dropped.append((pid, ip, port))
            for pid, ip, port in dropped:
                print(f"[{self.node_id}] - peer dropped: {pid} @ {ip}:{port}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="P2P mesh node demo")
    parser.add_argument("--id", dest="node_id", default=None, help="optional node ID")
    parser.add_argument("--sink-host", default="127.0.0.1",
                        help="local UDP host to forward received messages to")
    parser.add_argument("--sink-port", type=int, default=None,
                        help="if set, forward each distinct mesh message to "
                             "udp://<sink-host>:<sink-port> as '<origin_id>|<message>'")
    args = parser.parse_args(argv)

    sink = (args.sink_host, args.sink_port) if args.sink_port is not None else None
    node = Node(node_id=args.node_id, sink=sink)
    node.start()
    if sink:
        print(f"[{node.node_id}] sink egress -> udp://{sink[0]}:{sink[1]}")

    last_broadcast = 0.0
    try:
        while True:
            peers = node.peers()
            print(f"[{node.node_id}] connected peers: {len(peers)} -> {sorted(peers)}")
            now = time.time()
            if now - last_broadcast >= 3.0:
                sent = node.broadcast(f"hello from {node.node_id}")
                if sent:
                    print(f"[{node.node_id}] -> broadcast to {sent} peer(s)")
                last_broadcast = now
            time.sleep(1.0)
    except KeyboardInterrupt:
        print(f"\n[{node.node_id}] shutting down")
        node.stop()
        return 0


if __name__ == "__main__":
    sys.exit(main())

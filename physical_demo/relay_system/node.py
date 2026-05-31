"""Peer-to-peer mesh node with bootstrap-by-known-peer discovery.

No multicast, no broadcast, no interface enumeration. Each node binds one
UDP port. New nodes are told the address of any existing peer ("the
bootstrap") and JOIN it; from then on, gossip in every HELLO propagates the
full peer list across the mesh within a couple of seconds.

Demo on one Wi-Fi:

    Terminal 1 (any laptop):
        python3 node.py --port 5000
        [node-A] listening on 192.168.1.5:5000
        [node-A] to add more nodes: python3 node.py --bootstrap 192.168.1.5:5000

    Terminal 2..N (any other laptop on the same Wi-Fi):
        python3 node.py --bootstrap 192.168.1.5:5000

Bootstraps may be specified more than once; the first one that answers wins,
so you can hand out a list of "known good" peers and survive any single
listener going down. Once a node has any peer, gossip takes over.

Wire format (UTF-8 text, '|' separators):

    JOIN|<id>|<port>                      one-shot, sent until we have a peer
    HELLO|<id>|<port>|<peer_list>         periodic keepalive, includes gossip
    MSG|<uuid>|<origin_id>|<text>         application message (multi-hop)

<peer_list> is "<id>@<ip>:<port>" entries joined by ';' (empty when alone).
"""

from __future__ import annotations

import argparse
import random
import socket
import string
import sys
import threading
import time
import uuid
from collections import OrderedDict
from typing import Callable, Dict, List, Optional, Tuple

HELLO_INTERVAL = 1.0
PEER_TIMEOUT = 5.0
RECV_BUF = 8192
SEEN_MAX = 4096

PeerInfo = Tuple[str, int, float]  # (ip, port, last_seen)


def _random_id(n: int = 6) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def _detect_local_ip() -> str:
    """Best-effort LAN IP guess (connected-UDP trick — no packets sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _parse_addr(spec: str) -> Tuple[str, int]:
    """'host:port' -> (host, int(port)). 'host' may be a name or dotted IP."""
    host, _, port_str = spec.rpartition(":")
    if not host or not port_str:
        raise ValueError(f"expected 'host:port', got {spec!r}")
    return host, int(port_str)


class Node:
    def __init__(
        self,
        node_id: Optional[str] = None,
        on_message: Optional[Callable[[str, str], None]] = None,
        sink: Optional[Tuple[str, int]] = None,
        port: int = 0,
        bootstrap: Optional[List[Tuple[str, int]]] = None,
        advertise_ip: Optional[str] = None,
        verbose: bool = False,
    ) -> None:
        self.node_id = node_id or _random_id()
        self.on_message: Callable[[str, str], None] = on_message or self._default_on_message
        self._sink: Optional[Tuple[str, int]] = sink
        self._verbose = verbose

        # One UDP socket for everything: JOIN, HELLO, MSG.
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("", port))
        self.data_port: int = self._sock.getsockname()[1]

        # Separate egress socket for the local sink so its packets never get
        # mixed up with mesh traffic on the data port.
        self._sink_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self.advertise_ip = advertise_ip or _detect_local_ip()
        self._bootstrap_list: List[Tuple[str, int]] = list(bootstrap or [])

        self._peers: Dict[str, PeerInfo] = {}
        self._peers_lock = threading.Lock()

        self._seen: "OrderedDict[str, float]" = OrderedDict()
        self._seen_lock = threading.Lock()

        self._stop = threading.Event()
        self._threads: List[threading.Thread] = []

    # ---- public API ----------------------------------------------------

    def start(self) -> None:
        addr = f"{self.advertise_ip}:{self.data_port}"
        print(f"[{self.node_id}] listening on {addr}")
        if self._bootstrap_list:
            targets = ", ".join(f"{h}:{p}" for h, p in self._bootstrap_list)
            print(f"[{self.node_id}] bootstrapping from {targets}")
        else:
            print(
                f"[{self.node_id}] to add more nodes: "
                f"python3 node.py --bootstrap {addr}"
            )
        for target in (self._hello_loop, self._recv_loop, self._reaper_loop):
            t = threading.Thread(target=target, name=target.__name__, daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._stop.set()

    def peers(self) -> Dict[str, PeerInfo]:
        with self._peers_lock:
            return dict(self._peers)

    def broadcast(self, message: str) -> int:
        """Originate a new message — fan out to every connected peer."""
        msg_id = uuid.uuid4().hex
        self._mark_seen(msg_id)
        self._to_sink(self.node_id, message)
        return self._send_msg(msg_id, self.node_id, message)

    def set_sink(self, sink: Optional[Tuple[str, int]]) -> None:
        self._sink = sink

    # ---- send helpers --------------------------------------------------

    def _send_msg(
        self,
        msg_id: str,
        origin_id: str,
        message: str,
        exclude_addr: Optional[Tuple[str, int]] = None,
    ) -> int:
        payload = f"MSG|{msg_id}|{origin_id}|{message}".encode("utf-8")
        sent = 0
        for _pid, (ip, port, _seen) in self.peers().items():
            if exclude_addr is not None and (ip, port) == exclude_addr:
                continue
            try:
                self._sock.sendto(payload, (ip, port))
                sent += 1
            except OSError as e:
                print(f"[{self.node_id}] send to {ip}:{port} failed: {e}")
        return sent

    def _send_hello(self, addr: Tuple[str, int]) -> None:
        peer_list = self._format_peer_list()
        payload = f"HELLO|{self.node_id}|{self.data_port}|{peer_list}".encode("utf-8")
        try:
            self._sock.sendto(payload, addr)
            if self._verbose:
                print(
                    f"[{self.node_id}] tx HELLO -> {addr[0]}:{addr[1]} "
                    f"({len(payload)}B, peerlist_n={len(self.peers())})"
                )
        except OSError as e:
            if self._verbose:
                print(f"[{self.node_id}] tx HELLO to {addr} failed: {e}")

    def _send_join(self, addr: Tuple[str, int]) -> None:
        payload = f"JOIN|{self.node_id}|{self.data_port}".encode("utf-8")
        try:
            self._sock.sendto(payload, addr)
            if self._verbose:
                print(f"[{self.node_id}] tx JOIN -> {addr[0]}:{addr[1]}")
        except OSError as e:
            print(f"[{self.node_id}] JOIN to {addr[0]}:{addr[1]} failed: {e}")

    def _to_sink(self, origin_id: str, message: str) -> None:
        if self._sink is None:
            return
        try:
            self._sink_sock.sendto(
                f"{origin_id}|{message}".encode("utf-8"), self._sink
            )
        except OSError as e:
            print(f"[{self.node_id}] sink forward failed: {e}")

    def _mark_seen(self, msg_id: str) -> bool:
        with self._seen_lock:
            if msg_id in self._seen:
                self._seen.move_to_end(msg_id)
                return False
            self._seen[msg_id] = time.time()
            while len(self._seen) > SEEN_MAX:
                self._seen.popitem(last=False)
            return True

    def _format_peer_list(self) -> str:
        return ";".join(
            f"{pid}@{ip}:{port}" for pid, (ip, port, _seen) in self.peers().items()
        )

    def _parse_peer_list(self, s: str) -> List[Tuple[str, str, int]]:
        out: List[Tuple[str, str, int]] = []
        if not s:
            return out
        for entry in s.split(";"):
            if not entry:
                continue
            try:
                pid, ipport = entry.split("@", 1)
                ip, port_str = ipport.rsplit(":", 1)
                out.append((pid, ip, int(port_str)))
            except (ValueError, IndexError):
                continue
        return out

    # ---- main loops ----------------------------------------------------

    def _hello_loop(self) -> None:
        """Every HELLO_INTERVAL: keepalive every peer, or retry bootstraps."""
        while not self._stop.is_set():
            current = self.peers()
            if current:
                for _pid, (ip, port, _seen) in current.items():
                    self._send_hello((ip, port))
            elif self._bootstrap_list:
                # We don't have any peers yet — keep knocking on every
                # bootstrap target until one responds (or one comes online).
                for addr in self._bootstrap_list:
                    self._send_join(addr)
            self._stop.wait(HELLO_INTERVAL)

    def _recv_loop(self) -> None:
        self._sock.settimeout(1.0)
        while not self._stop.is_set():
            try:
                data, addr = self._sock.recvfrom(RECV_BUF)
            except socket.timeout:
                continue
            except OSError:
                if self._stop.is_set():
                    return
                continue

            if self._verbose:
                preview = data[:96].decode("utf-8", errors="replace").replace("\n", " ")
                print(
                    f"[{self.node_id}] rx {len(data)}B from "
                    f"{addr[0]}:{addr[1]}: {preview!r}"
                )

            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            kind, _sep, rest = text.partition("|")
            if kind == "MSG":
                self._handle_msg(rest, addr)
            elif kind == "HELLO":
                self._handle_hello(rest, addr)
            elif kind == "JOIN":
                self._handle_join(rest, addr)

    def _handle_hello(self, rest: str, addr: Tuple[str, int]) -> None:
        parts = rest.split("|", 2)
        if len(parts) < 2:
            return
        peer_id = parts[0]
        # parts[1] is the advertised port — kept in the protocol for clarity
        # but ignored: through a NAT (e.g. WSL2 behind Windows, iPhone tether,
        # corporate firewall) the internal port isn't reachable from outside,
        # so we always use `addr` (the kernel-visible source), which IS the
        # address NAT will route replies back through.
        peer_list_str = parts[2] if len(parts) >= 3 else ""
        if peer_id != self.node_id:
            self._add_peer(peer_id, addr[0], addr[1])
        for pid, ip, pport in self._parse_peer_list(peer_list_str):
            self._add_peer(pid, ip, pport)

    def _handle_join(self, rest: str, addr: Tuple[str, int]) -> None:
        parts = rest.split("|", 1)
        if len(parts) < 1:
            return
        peer_id = parts[0]
        if not peer_id or peer_id == self.node_id:
            return
        # Use the kernel-visible source as the peer's reachable address — see
        # _handle_hello for why we ignore the advertised port.
        self._add_peer(peer_id, addr[0], addr[1])
        # Immediate HELLO back so the joiner gets our peer list within ms,
        # not after waiting up to HELLO_INTERVAL.
        self._send_hello(addr)

    def _handle_msg(self, rest: str, addr: Tuple[str, int]) -> None:
        parts = rest.split("|", 2)
        if len(parts) < 3:
            return
        msg_id, origin_id, message = parts[0], parts[1], parts[2]
        if origin_id == self.node_id:
            return
        if not self._mark_seen(msg_id):
            return  # duplicate — drop, do not re-forward
        self._to_sink(origin_id, message)
        try:
            self.on_message(origin_id, message)
        except Exception as e:
            print(f"[{self.node_id}] on_message error: {e}")
        # Re-forward to all other peers for multi-hop propagation.
        self._send_msg(msg_id, origin_id, message, exclude_addr=addr)

    def _add_peer(self, peer_id: str, ip: str, port: int) -> None:
        if peer_id == self.node_id:
            return
        now = time.time()
        with self._peers_lock:
            existed = peer_id in self._peers
            self._peers[peer_id] = (ip, port, now)
        if not existed:
            print(f"[{self.node_id}] + peer joined: {peer_id} @ {ip}:{port}")
            # Knock back so they learn about us right away (and add us as a
            # peer if they don't already have us via gossip).
            self._send_hello((ip, port))

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

    def _default_on_message(self, sender_id: str, message: str) -> None:
        print(f"[{self.node_id}] <- {sender_id}: {message}")


def _stdin_loop(node: Node) -> None:
    """Read lines from stdin and broadcast each non-empty line to the mesh.

    Runs as a daemon thread so EOF / process exit cleans it up automatically.
    """
    try:
        for line in sys.stdin:
            msg = line.rstrip("\r\n")
            if not msg:
                continue
            sent = node.broadcast(msg)
            print(f"[{node.node_id}] -> sent {msg!r} to {sent} peer(s)")
    except (OSError, ValueError):
        return


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="P2P mesh node — bootstrap by known peer, no multicast."
    )
    parser.add_argument("--id", dest="node_id", default=None,
                        help="optional short ID (auto-generated if omitted)")
    parser.add_argument("--port", type=int, default=0,
                        help="UDP port to bind (default: ephemeral). Pin a "
                             "fixed port like 5000 on the first node so the "
                             "rest can bootstrap to a predictable address.")
    parser.add_argument("--bootstrap", action="append", default=[],
                        metavar="HOST:PORT",
                        help="address of an existing peer to join through. "
                             "May be given more than once — first to answer "
                             "wins, so a list survives any single node going down.")
    parser.add_argument("--advertise-ip", default=None,
                        help="LAN IP to advertise to peers (default: auto-detect)")
    parser.add_argument("--sink-host", default="127.0.0.1",
                        help="local UDP host to forward received messages to")
    parser.add_argument("--sink-port", type=int, default=None,
                        help="if set, forward each distinct mesh message to "
                             "udp://<sink-host>:<sink-port> as '<origin_id>|<message>'")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="log every send and receive")
    args = parser.parse_args(argv)

    try:
        bootstrap = [_parse_addr(b) for b in args.bootstrap]
    except ValueError as e:
        parser.error(str(e))

    sink = (args.sink_host, args.sink_port) if args.sink_port is not None else None
    node = Node(
        node_id=args.node_id,
        port=args.port,
        bootstrap=bootstrap,
        advertise_ip=args.advertise_ip,
        sink=sink,
        verbose=args.verbose,
    )
    node.start()

    # Type a line, hit enter -> broadcast it to the mesh.
    stdin_t = threading.Thread(
        target=_stdin_loop, args=(node,), name="stdin", daemon=True
    )
    stdin_t.start()
    print(f"[{node.node_id}] type a message and hit enter to broadcast it")

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

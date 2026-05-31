"""Peer-to-peer mesh node.

Multiple instances on the same machine or on the same LAN auto-discover each
other over UDP multicast and exchange direct unicast messages — no central
server. Standard library only.
"""

from __future__ import annotations

import argparse
import errno
import os
import random
import socket
import string
import struct
import subprocess
import sys
import threading
import time
import uuid
from collections import OrderedDict
from typing import Callable, Dict, List, Optional, Tuple

MCAST_GROUP = "239.1.1.1"
MCAST_PORT = 5000
HELLO_INTERVAL = 1.0
PEER_TIMEOUT = 5.0
RECV_BUF = 4096
SEEN_MAX = 4096  # cap on remembered message IDs (LRU eviction)

PeerInfo = Tuple[str, int, float]  # (ip, data_port, last_seen)


def _random_id(n: int = 6) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def _detect_default_iface_ip() -> Optional[str]:
    """Local IP of the interface used for the default route (connected-UDP trick)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        if ip and not ip.startswith("127."):
            return ip
        return None
    except OSError:
        return None
    finally:
        s.close()


# Interfaces we never want to use for L2 mesh discovery: VPN tunnels, point-
# to-point, container/virtual bridges that aren't carrying peers.
_SKIP_IFACE_PREFIXES = ("lo", "utun", "tun", "tap", "ipsec", "ppp", "gif", "stf",
                        "awdl", "llw", "docker", "veth", "br-")


def _list_active_ipv4_interfaces() -> List[Tuple[str, str, Optional[str]]]:
    """Return [(name, ip, broadcast_or_None), ...] for usable IPv4 interfaces.

    Parses `ifconfig` (present on both macOS and typical Linux). Skips
    loopback and known-virtual interfaces. Interfaces without a broadcast
    address (point-to-point links like Tailscale's utun) are still returned
    but with bcast=None so callers can filter them out.
    """
    try:
        output = subprocess.check_output(
            ["ifconfig"], stderr=subprocess.DEVNULL, timeout=2
        ).decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError):
        return []

    results: List[Tuple[str, str, Optional[str]]] = []
    current_name: Optional[str] = None
    for line in output.splitlines():
        if line and not line[0].isspace():
            # interface header: "en0: flags=..." (mac) / "en0  Link encap:..." (linux)
            current_name = line.split(":")[0].split()[0].strip()
            continue
        if not current_name:
            continue
        if current_name.startswith(_SKIP_IFACE_PREFIXES):
            continue
        stripped = line.strip()
        if not stripped.startswith("inet "):
            continue
        parts = stripped.split()
        try:
            ip = parts[1]
        except IndexError:
            continue
        if ip.startswith("127."):
            continue
        bcast: Optional[str] = None
        if "broadcast" in parts:
            try:
                bcast = parts[parts.index("broadcast") + 1]
            except IndexError:
                pass
        results.append((current_name, ip, bcast))
    return results


def _pick_iface_ip(interfaces: List[Tuple[str, str, Optional[str]]]) -> Optional[str]:
    """Pick the best interface IP for multicast: prefer one with a broadcast addr."""
    for _name, ip, bcast in interfaces:
        if bcast:
            return ip
    if interfaces:
        return interfaces[0][1]
    return _detect_default_iface_ip()


def _open_multicast_socket(iface_ip: Optional[str]) -> Tuple[socket.socket, bool, Optional[str]]:
    """Open the discovery socket, joined to the multicast group.

    Returns (socket, multicast_ok, iface_ip_used). Pinning send/join to a
    specific interface avoids EHOSTUNREACH on multi-homed boxes. The caller
    is responsible for choosing `iface_ip`; pass None to use the default
    route's interface.
    """
    iface = iface_ip

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

    if iface:
        try:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                            socket.inet_aton(iface))
        except OSError as e:
            print(f"[warn] IP_MULTICAST_IF set failed for {iface}: {e}")

    if_addr = socket.inet_aton(iface) if iface else struct.pack("!I", socket.INADDR_ANY)
    try:
        mreq = socket.inet_aton(MCAST_GROUP) + if_addr
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        return sock, True, iface
    except OSError as e:
        print(f"[warn] multicast join failed ({e}); falling back to broadcast")
        return sock, False, iface


class Node:
    def __init__(
        self,
        node_id: Optional[str] = None,
        on_message: Optional[Callable[[str, str], None]] = None,
        sink: Optional[Tuple[str, int]] = None,
        iface: Optional[str] = None,
        broadcast: Optional[str] = None,
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

        # Enumerate every usable IPv4 interface (filters VPN/loopback/virtual).
        # On a Mac doing iPhone-USB → WiFi sharing this yields, e.g.,
        # `bridge0=192.168.2.1 (bcast 192.168.2.255)` and `en7=172.20.10.2
        # (bcast 172.20.10.15)`; the Tailscale `utun*` (100.84.x with no
        # broadcast) is correctly skipped.
        ifaces = _list_active_ipv4_interfaces()
        chosen_iface = iface or _pick_iface_ip(ifaces)
        self._disc_sock, self._mcast_ok, self._iface = _open_multicast_socket(chosen_iface)

        # Discovery destinations: multicast (if reachable) plus every
        # interface's directed broadcast. The kernel auto-routes each
        # directed broadcast out the matching interface based on the
        # destination subnet, so this works automatically on multi-homed
        # boxes (iPhone tether + WiFi sharing + VPN) with no flags.
        self._broadcast_dests: List[str] = ["255.255.255.255"]
        if broadcast:
            self._broadcast_dests.append(broadcast)
        else:
            for _name, _ip, bcast in ifaces:
                if bcast and bcast not in self._broadcast_dests:
                    self._broadcast_dests.append(bcast)
            # If enumeration found nothing useful, fall back to /24 derive.
            if len(self._broadcast_dests) == 1 and self._iface:
                octets = self._iface.split(".")
                if len(octets) == 4:
                    self._broadcast_dests.append(
                        f"{octets[0]}.{octets[1]}.{octets[2]}.255"
                    )
        self._warned_mcast_unreach = False
        self._dead_dests: set = set()  # destinations we've stopped trying

        self._peers: Dict[str, PeerInfo] = {}
        self._peers_lock = threading.Lock()

        self._seen: "OrderedDict[str, float]" = OrderedDict()
        self._seen_lock = threading.Lock()

        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    # ---- public API ----------------------------------------------------

    def start(self) -> None:
        mode = "multicast+broadcast" if self._mcast_ok else "broadcast-only"
        iface = self._iface or "auto"
        print(
            f"[{self.node_id}] up data_port={self.data_port} discovery={mode} "
            f"group={MCAST_GROUP}:{MCAST_PORT} iface={iface} "
            f"bcast={self._broadcast_dests}"
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
        """Fan out the HELLO to multicast plus every directed-broadcast path.

        Per-destination failures are isolated. A destination that fails with
        EHOSTUNREACH/ENETUNREACH is marked dead and skipped from then on, so
        a Tailscale-style point-to-point subnet doesn't spam the log forever.
        """
        sent_any = False
        last_err: Optional[Tuple[str, OSError]] = None

        dests: List[str] = []
        if self._mcast_ok and MCAST_GROUP not in self._dead_dests:
            dests.append(MCAST_GROUP)
        for d in self._broadcast_dests:
            if d not in self._dead_dests and d not in dests:
                dests.append(d)

        for dst in dests:
            try:
                self._disc_sock.sendto(payload, (dst, MCAST_PORT))
                sent_any = True
            except OSError as e:
                last_err = (dst, e)
                if e.errno in (errno.EHOSTUNREACH, errno.ENETUNREACH):
                    self._dead_dests.add(dst)
                    print(
                        f"[{self.node_id}] discovery dst {dst} unreachable ({e}); "
                        f"skipping from now on"
                    )
                    if dst == MCAST_GROUP:
                        self._mcast_ok = False
        if not sent_any and last_err is not None:
            dst, err = last_err
            print(f"[{self.node_id}] all discovery sends failed; last={dst} ({err})")

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
    parser.add_argument("--iface", default=None,
                        help="local IP of the interface to use for multicast "
                             "send/join (e.g. 192.168.1.42). Auto-detected by "
                             "default; set explicitly to override on a "
                             "multi-homed host (VPN, hotspot, Internet Sharing)")
    parser.add_argument("--broadcast", default=None,
                        help="explicit directed broadcast address to use for "
                             "discovery (e.g. 172.20.10.15 for iPhone hotspot "
                             "/28). Auto-derives a /24 broadcast from --iface "
                             "if omitted.")
    parser.add_argument("--sink-host", default="127.0.0.1",
                        help="local UDP host to forward received messages to")
    parser.add_argument("--sink-port", type=int, default=None,
                        help="if set, forward each distinct mesh message to "
                             "udp://<sink-host>:<sink-port> as '<origin_id>|<message>'")
    args = parser.parse_args(argv)

    sink = (args.sink_host, args.sink_port) if args.sink_port is not None else None
    node = Node(node_id=args.node_id, sink=sink, iface=args.iface,
                broadcast=args.broadcast)
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

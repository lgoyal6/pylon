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


# Interfaces we never want to use for L2 mesh discovery: VPN tunnels, point-
# to-point, container/virtual bridges that aren't carrying peers.
_SKIP_IFACE_PREFIXES = ("lo", "utun", "tun", "tap", "ipsec", "ppp", "gif", "stf",
                        "awdl", "llw", "docker", "veth", "br-")


def _is_apipa(ip: str) -> bool:
    """169.254.0.0/16 — link-local, assigned when DHCP fails."""
    return ip.startswith("169.254.")


def _is_cgnat(ip: str) -> bool:
    """100.64.0.0/10 — RFC 6598. Tailscale, iCloud Private Relay, Cloudflare
    WARP, and some ISP carrier-grade NAT all use this range. Never a real LAN."""
    if not ip.startswith("100."):
        return False
    try:
        return 64 <= int(ip.split(".")[1]) <= 127
    except (ValueError, IndexError):
        return False


def _is_rfc1918(ip: str) -> bool:
    """10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 — almost certainly a real LAN."""
    if ip.startswith("10.") or ip.startswith("192.168."):
        return True
    if ip.startswith("172."):
        try:
            return 16 <= int(ip.split(".")[1]) <= 31
        except (ValueError, IndexError):
            return False
    return False


def _classify_iface(name: str, ip: str, bcast: Optional[str]) -> Tuple[bool, str]:
    """Decide whether this interface is usable for mesh discovery.

    Returns (usable, reason). The reason string is shown at startup so a
    user looking at the log can immediately see why an interface was skipped.

    Note on CGNAT (100.64.0.0/10): this range is used by both VPNs
    (Tailscale, iCloud Private Relay, Cloudflare WARP — all on utun* names)
    AND by large public networks (schools, dorms, hotels, mobile carriers
    DHCPing clients into a CGNAT subnet). We trust the name-prefix filter
    above to catch the VPN cases, and accept CGNAT on a real NIC (en*,
    eth*, bridge*) as a usable LAN.
    """
    if name.startswith(_SKIP_IFACE_PREFIXES):
        return False, "name excluded (VPN/virtual)"
    if ip.startswith("127."):
        return False, "loopback"
    if _is_apipa(ip):
        return False, "APIPA self-assigned (no DHCP — interface has no real network)"
    if not bcast:
        return False, "point-to-point (no broadcast address)"
    if _is_rfc1918(ip):
        return True, "RFC1918 LAN"
    if _is_cgnat(ip):
        return True, "CGNAT LAN (school/hotel/carrier DHCP)"
    return True, "public-routable IP with broadcast"


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


UsableIface = Tuple[str, str, str]  # (name, ip, bcast) — bcast guaranteed non-None


def _select_usable_ifaces(
    all_ifaces: List[Tuple[str, str, Optional[str]]],
    log_prefix: str,
) -> List[UsableIface]:
    """Classify each enumerated interface, log every decision, return usable.

    Prefers RFC1918 LANs over non-private but-still-has-broadcast addresses,
    so a real Wi-Fi gets picked first even when an APIPA en0 happens to
    enumerate earlier.
    """
    rfc1918: List[UsableIface] = []
    other: List[UsableIface] = []
    print(f"{log_prefix} interfaces discovered:")
    for name, ip, bcast in all_ifaces:
        ok, reason = _classify_iface(name, ip, bcast)
        tag = "USE " if ok else "SKIP"
        bcast_str = bcast if bcast else "-"
        print(f"{log_prefix}   [{tag}] {name:<10} ip={ip:<16} bcast={bcast_str:<16} ({reason})")
        if ok and bcast is not None:
            (rfc1918 if _is_rfc1918(ip) else other).append((name, ip, bcast))
    return rfc1918 + other


def _open_recv_socket(usable: List[UsableIface], log_prefix: str) -> Tuple[socket.socket, int]:
    """Open the discovery RECEIVE socket and join multicast on every usable iface.

    Returns (socket, joined_count). joined_count == 0 means we're broadcast-only.
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

    joined = 0
    targets = usable or [("any", "0.0.0.0", "")]
    for name, ip, _b in targets:
        try:
            mreq = socket.inet_aton(MCAST_GROUP) + socket.inet_aton(ip)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            joined += 1
        except OSError as e:
            print(f"{log_prefix} multicast join failed on {name}/{ip}: {e}")
    return sock, joined


def _open_send_socket(iface_ip: str, log_prefix: str) -> Optional[socket.socket]:
    """One send socket per interface, bound to that interface's source IP.

    Binding to a specific source IP forces the kernel to send out that
    interface, sidestepping route-table fragility on macOS where
    IP_MULTICAST_IF alone isn't enough to avoid EHOSTUNREACH.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        try:
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                         socket.inet_aton(iface_ip))
        except OSError as e:
            print(f"{log_prefix} IP_MULTICAST_IF failed for {iface_ip}: {e}")
        s.bind((iface_ip, 0))
        return s
    except OSError as e:
        print(f"{log_prefix} failed to open send socket on {iface_ip}: {e}")
        return None


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

        # Enumerate every IPv4 interface and classify each. Logging the
        # decision per interface is critical for debugging weird networks
        # (iPhone-USB → Mac WiFi sharing + Tailscale + APIPA en0 etc.).
        log_prefix = f"[{self.node_id}]"
        all_ifaces = _list_active_ipv4_interfaces()
        usable = _select_usable_ifaces(all_ifaces, log_prefix)

        # Honor an explicit --iface override: keep only that one, even if it
        # would normally be filtered (escape hatch for unusual setups).
        if iface:
            forced = next((u for u in usable if u[1] == iface), None)
            if forced is None:
                # Find it in the raw list and force-include it.
                for name, ip, bcast in all_ifaces:
                    if ip == iface:
                        forced = (name, ip, bcast or f"{ip.rsplit('.', 1)[0]}.255")
                        break
            usable = [forced] if forced else []

        # One send socket per usable interface, bound to that iface's source
        # IP. Binding to a specific source forces the kernel to send out
        # that interface — far more reliable on macOS than IP_MULTICAST_IF
        # alone, which the kernel still subjects to a route lookup.
        self._send_paths: List[Tuple[str, str, str, socket.socket]] = []
        for name, ip, bcast in usable:
            s = _open_send_socket(ip, log_prefix)
            if s is not None:
                self._send_paths.append((name, ip, bcast, s))

        # Optional extra broadcast destination — added to every send path
        # (e.g. iPhone hotspot /28 directed broadcast 172.20.10.15).
        self._extra_bcast: Optional[str] = broadcast

        # Receive socket: bound to *:MCAST_PORT, joined to multicast on
        # every usable interface so we hear group traffic from any iface.
        self._disc_sock, joined = _open_recv_socket(usable, log_prefix)
        self._mcast_ok = joined > 0
        self._iface = usable[0][1] if usable else None

        # Per-(path, destination) dead set: once a particular send fails
        # with EHOSTUNREACH it stops being retried for that path.
        self._dead: set = set()

        self._peers: Dict[str, PeerInfo] = {}
        self._peers_lock = threading.Lock()

        self._seen: "OrderedDict[str, float]" = OrderedDict()
        self._seen_lock = threading.Lock()

        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    # ---- public API ----------------------------------------------------

    def start(self) -> None:
        mode = "multicast+broadcast" if self._mcast_ok else "broadcast-only"
        paths = ", ".join(f"{n}({ip}->{b})" for n, ip, b, _s in self._send_paths) or "<none>"
        print(
            f"[{self.node_id}] up data_port={self.data_port} discovery={mode} "
            f"group={MCAST_GROUP}:{MCAST_PORT} send_paths=[{paths}]"
        )
        if not self._send_paths:
            print(
                f"[{self.node_id}] WARNING: no usable interfaces — pass --iface "
                f"<ip> with the IP of the LAN interface you want to use"
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
        """Fan out the HELLO out every usable interface.

        For each send path (one socket per usable interface), try multicast
        AND the interface's directed broadcast AND limited broadcast. Each
        (path, destination) pair that fails with EHOSTUNREACH/ENETUNREACH
        is blacklisted independently so a bad path doesn't poison the rest.
        """
        sent_any = False
        last_err: Optional[Tuple[str, str, OSError]] = None

        for name, ip, bcast, sock in self._send_paths:
            dests = [bcast, "255.255.255.255"]
            if self._extra_bcast and self._extra_bcast not in dests:
                dests.append(self._extra_bcast)
            if self._mcast_ok:
                dests.insert(0, MCAST_GROUP)

            for dst in dests:
                key = (name, dst)
                if key in self._dead:
                    continue
                try:
                    sock.sendto(payload, (dst, MCAST_PORT))
                    sent_any = True
                except OSError as e:
                    last_err = (name, dst, e)
                    if e.errno in (errno.EHOSTUNREACH, errno.ENETUNREACH):
                        self._dead.add(key)
                        print(
                            f"[{self.node_id}] {name} -> {dst} unreachable "
                            f"({e}); skipping this path from now on"
                        )

        if not sent_any and last_err is not None:
            name, dst, err = last_err
            print(
                f"[{self.node_id}] all discovery sends failed; "
                f"last attempt {name}->{dst} ({err})"
            )

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

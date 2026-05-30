"""Sensor ingress relay.

Listens on local UDP port 5000 for sensor datagrams and forwards each one out
to every connected peer in the mesh via the Node substrate. Incoming mesh
messages are printed.

    sensor --(UDP :5000 localhost)--> [this node] --(unicast to peers)--> mesh

Test from another shell:
    echo -n "temp=21.4" | nc -u -w1 127.0.0.1 5000
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import time

from node import Node

SENSOR_PORT_DEFAULT = 5000
SENSOR_BIND_DEFAULT = "127.0.0.1"
RECV_BUF = 4096


def run_sensor_listener(node: Node, bind_host: str, bind_port: int, stop: threading.Event) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((bind_host, bind_port))
    sock.settimeout(1.0)
    print(f"[{node.node_id}] sensor ingress listening on udp://{bind_host}:{bind_port}")

    while not stop.is_set():
        try:
            data, addr = sock.recvfrom(RECV_BUF)
        except socket.timeout:
            continue
        except OSError:
            if stop.is_set():
                return
            continue
        try:
            text = data.decode("utf-8", errors="replace").rstrip()
        except Exception:
            text = repr(data)
        peer_count = len(node.peers())
        if peer_count == 0:
            print(f"[{node.node_id}] sensor <- {addr[0]}:{addr[1]}: {text!r} (no peers; dropped)")
            continue
        sent = node.broadcast(f"sensor:{text}")
        print(f"[{node.node_id}] sensor <- {addr[0]}:{addr[1]}: {text!r} -> relayed to {sent} peer(s)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sensor->mesh relay node")
    parser.add_argument("--id", dest="node_id", default=None)
    parser.add_argument("--sensor-host", default=SENSOR_BIND_DEFAULT,
                        help="local bind address for sensor ingress (default 127.0.0.1)")
    parser.add_argument("--sensor-port", type=int, default=SENSOR_PORT_DEFAULT)
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

    stop = threading.Event()
    t = threading.Thread(
        target=run_sensor_listener,
        args=(node, args.sensor_host, args.sensor_port, stop),
        name="sensor_listener",
        daemon=True,
    )
    t.start()

    last_log = 0.0
    try:
        while True:
            now = time.time()
            if now - last_log >= 1.0:
                peers = node.peers()
                print(f"[{node.node_id}] connected peers: {len(peers)} -> {sorted(peers)}")
                last_log = now
            time.sleep(0.5)
    except KeyboardInterrupt:
        print(f"\n[{node.node_id}] shutting down")
        stop.set()
        node.stop()
        return 0


if __name__ == "__main__":
    sys.exit(main())

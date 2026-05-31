"""CLI entrypoint: ``python main.py``."""
import argparse

import uvicorn

import config
import service


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="drone_detection",
        description="Iteration 0 detection service (:5001/status + UDP multicast).",
    )
    parser.add_argument("--port", type=int, default=config.SERVICE_PORT)
    parser.add_argument(
        "--publish-interval",
        type=float,
        default=config.PUBLISH_INTERVAL_S,
        metavar="SECONDS",
        help="re-publish a detection event this often while detected",
    )
    parser.add_argument(
        "--auto-toggle",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="hands-free: flip detection every N seconds (0 = off, use POST /sim)",
    )
    args = parser.parse_args()

    config.PUBLISH_INTERVAL_S = args.publish_interval
    service.auto_toggle_s = args.auto_toggle

    # host 0.0.0.0 so the teammate's relay can reach the service over the LAN.
    uvicorn.run(service.app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()

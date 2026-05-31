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
    parser.add_argument(
        "--source",
        choices=["sim", "live"],
        default="sim",
        help="sim = manual /sim only (fallback); live = RTL-SDR capture drives detection",
    )
    parser.add_argument(
        "--sdr",
        choices=["rtl", "pluto"],
        default="rtl",
        help="rtl = NESDR/RTL via rtl_sdr CLI (<=1.75 GHz); pluto = ADALM-Pluto via pyadi-iio (2.4 GHz)",
    )
    parser.add_argument(
        "--freq",
        type=float,
        default=None,
        metavar="HZ",
        help="center frequency to tune (live source); default 2.437 GHz for --sdr pluto, else FM",
    )
    parser.add_argument(
        "--sample-rate",
        type=float,
        default=config.SAMPLE_RATE_HZ,
        metavar="HZ",
        help="SDR sample rate (2.4 MHz recommended for RTL)",
    )
    parser.add_argument(
        "--gain",
        default=config.GAIN,
        help="tuner gain in dB, or 'auto'",
    )
    parser.add_argument(
        "--detector",
        choices=["anomaly", "energy"],
        default="anomaly",
        help="anomaly = open-world novelty (Iteration 2, product); energy = occupied-bw threshold (Iteration 1)",
    )
    parser.add_argument(
        "--learn-seconds",
        type=float,
        default=config.LEARN_SECONDS,
        metavar="SECONDS",
        help="anomaly detector: ambient-learning duration (keep the target OFF)",
    )
    parser.add_argument("--load-model", metavar="PATH", help="anomaly: load a saved baseline, skip learning")
    parser.add_argument("--save-model", metavar="PATH", help="anomaly: save the baseline after learning")
    parser.add_argument(
        "--relay",
        metavar="HOST:PORT",
        default=None,
        help="also forward each detection event (UDP unicast) to a mesh sensor-relay ingress "
             "(relay_system/sensor_relay.py), which rebroadcasts it across the mesh as sensor:<json>",
    )
    args = parser.parse_args()

    if args.freq is not None:
        freq = args.freq
    elif args.sdr == "pluto":
        freq = config.PLUTO_DEFAULT_CENTER_FREQ_HZ
    else:
        freq = config.DEFAULT_CENTER_FREQ_HZ

    config.PUBLISH_INTERVAL_S = args.publish_interval
    service.auto_toggle_s = args.auto_toggle
    service.source = args.source
    service.sdr_kind = args.sdr
    service.center_freq_hz = int(freq)
    service.sample_rate_hz = int(args.sample_rate)
    service.gain = args.gain
    service.detector_kind = args.detector
    service.learn_seconds = args.learn_seconds
    service.load_model_path = args.load_model
    service.save_model_path = args.save_model
    if args.relay:
        host, _, port = args.relay.rpartition(":")
        service.publisher.relay_addr = (host, int(port))
        print(f"[relay] forwarding detection events to mesh sensor ingress {host}:{port}")

    # host 0.0.0.0 so the teammate's relay can reach the service over the LAN.
    uvicorn.run(service.app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()

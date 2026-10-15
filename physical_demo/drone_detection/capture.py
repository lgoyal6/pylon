"""Read RTL-SDR or Pluto IQ for the detector and classifier runners.
RTL uses the installed CLI; Pluto loads its native driver only on use.
Reject incomplete RTL windows and bound reads to handle missing devices.
"""
import subprocess
import select
import time

import numpy as np

import config


class RtlCapture:
    def __init__(
        self,
        center_freq_hz: int,
        sample_rate: int,
        gain=config.GAIN,
        rtl_sdr_bin: str = "rtl_sdr",
    ) -> None:
        cmd = [
            rtl_sdr_bin,
            "-f", str(int(center_freq_hz)),
            "-s", str(int(sample_rate)),
        ]
        if str(gain) != "auto":  # omitting -g leaves rtl_sdr in automatic gain
            cmd += ["-g", str(gain)]
        cmd += ["-"]  # stream IQ to stdout
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)

    def read_window(self, n_samples: int) -> np.ndarray:
        """Read one IQ window. Returns an empty array if the stream ended
        (e.g. no device), so callers can detect/skip gracefully."""
        if n_samples <= 0:
            raise ValueError("n_samples must be positive")
        need = 2 * n_samples  # two bytes (I, Q) per complex sample
        buf = bytearray()
        deadline = time.monotonic() + 2.0
        while len(buf) < need:
            # A disconnected/stalled device must not hold shutdown forever.
            # In-memory test streams have no fd and do not block.
            try:
                fd = self.proc.stdout.fileno()
            except (AttributeError, OSError):
                fd = None
            if isinstance(fd, int):
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
                    break
            chunk = self.proc.stdout.read(need - len(buf))
            if not chunk:
                break
            buf += chunk
        if len(buf) != need:
            # A partial window is capture loss, never a valid quiet window.
            return np.empty(0, dtype=np.complex64)
        raw = np.frombuffer(bytes(buf), dtype=np.uint8).astype(np.float32)
        i, q = raw[0::2], raw[1::2]
        return ((i - 127.5) + 1j * (q - 127.5)).astype(np.complex64) / 127.5

    def close(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=2)


class PlutoCapture:
    """Live ADALM-Pluto capture via pyadi-iio (libiio USB backend).

    Same ``read_window(n) -> normalized complex64`` contract as RtlCapture, so it
    drops into DetectorRunner unchanged - but reaches 2.4 GHz (the RTL can't),
    enabling WiFi/BT-band detection. The Pluto's 12-bit ADC returns samples in
    int16 range (|sample| up to ~2048); we normalize by 2048 to land in ~[-1, 1],
    matching the RTL path's convention.

    `sdr` is injectable so the logic is testable without libiio/hardware; live
    runs leave it None and build ``adi.Pluto(uri)`` (lazy import, since only the
    live path needs libiio).
    """

    def __init__(
        self,
        center_freq_hz: int,
        sample_rate: int,
        gain=config.GAIN,
        uri: str = config.PLUTO_URI,
        sdr=None,
    ) -> None:
        if sdr is None:
            import adi  # lazy: only the live path needs libiio/pyadi-iio

            sdr = adi.Pluto(uri)
        self.sdr = sdr
        sdr.rx_lo = int(center_freq_hz)
        sdr.sample_rate = int(sample_rate)
        sdr.rx_rf_bandwidth = int(sample_rate)
        if str(gain) == "auto":
            sdr.gain_control_mode_chan0 = "slow_attack"  # AGC
        else:
            sdr.gain_control_mode_chan0 = "manual"
            sdr.rx_hardwaregain_chan0 = float(gain)
        self._buffer_size = None

    def read_window(self, n_samples: int) -> np.ndarray:
        """Read one IQ window of `n_samples` complex samples, normalized to ~[-1, 1]."""
        if self._buffer_size != n_samples:
            self.sdr.rx_buffer_size = int(n_samples)  # (re)sizes the rx buffer
            self._buffer_size = n_samples
        data = np.asarray(self.sdr.rx())
        return (data / 2048.0).astype(np.complex64)

    def close(self) -> None:
        try:
            self.sdr.rx_destroy_buffer()
        except Exception:
            pass

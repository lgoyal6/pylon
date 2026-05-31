"""Live RTL-SDR capture via the `rtl_sdr` CLI.

We shell out to `rtl_sdr` (Homebrew `librtlsdr`) rather than use pyrtlsdr: the
pyrtlsdr 0.4.0 ctypes bindings expect `rtlsdr_set_dithering`, which the Homebrew
librtlsdr 2.0.2 build doesn't export, so `import rtlsdr` fails. The compiled
`rtl_sdr` binary links the dylib correctly and streams raw IQ on stdout.

`rtl_sdr` emits interleaved unsigned 8-bit I/Q; we normalize to complex64 in
[-1, 1], matching what a detector expects.
"""
import subprocess

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
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def read_window(self, n_samples: int) -> np.ndarray:
        """Read one IQ window. Returns an empty array if the stream ended
        (e.g. no device), so callers can detect/skip gracefully."""
        need = 2 * n_samples  # two bytes (I, Q) per complex sample
        buf = bytearray()
        while len(buf) < need:
            chunk = self.proc.stdout.read(need - len(buf))
            if not chunk:
                break
            buf += chunk
        raw = np.frombuffer(bytes(buf), dtype=np.uint8).astype(np.float32)
        i, q = raw[0::2], raw[1::2]
        return ((i - 127.5) + 1j * (q - 127.5)).astype(np.complex64) / 127.5

    def close(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.proc.kill()


class PlutoCapture:
    """Live ADALM-Pluto capture via pyadi-iio (libiio USB backend).

    Same ``read_window(n) -> normalized complex64`` contract as RtlCapture, so it
    drops into DetectorRunner unchanged — but reaches 2.4 GHz (the RTL can't),
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

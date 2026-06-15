"""Real-time audio analysis.

`AudioAnalyzer` opens an input stream (microphone by default, or a loopback /
output-monitor device if configured) and continuously computes a smoothed
amplitude envelope plus an FFT spectrum. The render loop polls `level` and
`spectrum`; the audio callback runs on a separate thread, so all shared state
is guarded by a lock and kept to plain floats / small arrays.

Design notes
------------
* We never expose the raw RMS. The public `level` is exponentially smoothed
  (attack) and decays gently between callbacks (release) so the visuals stay
  fluid and never jitter on a single loud sample.
* FFT support is wired up now (used lightly for "speech dynamics") and is the
  hook for future spectral-reactive features.
"""

from __future__ import annotations

import threading

import numpy as np

try:
    import sounddevice as sd
except Exception:  # pragma: no cover - allows running without an audio device
    sd = None

from ..config import AudioConfig


class AudioAnalyzer:
    def __init__(self, config: AudioConfig | None = None, device: int | None = None):
        self.cfg = config or AudioConfig()
        self.device = device

        self._lock = threading.Lock()
        self._smoothed_level = 0.0
        self._peak = 0.0
        self._spectrum = np.zeros(self.cfg.fft_bins, dtype=np.float32)
        self._window = np.hanning(self.cfg.block_size).astype(np.float32)

        self._stream = None
        self._running = False
        self._available = sd is not None

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    @property
    def available(self) -> bool:
        return self._available

    def start(self) -> bool:
        """Open the input stream. Returns False if audio is unavailable."""
        if not self._available:
            return False
        if self._running:
            return True
        try:
            self._stream = sd.InputStream(
                samplerate=self.cfg.sample_rate,
                blocksize=self.cfg.block_size,
                channels=self.cfg.channels,
                dtype="float32",
                device=self.device,
                callback=self._callback,
            )
            self._stream.start()
            self._running = True
            return True
        except Exception as exc:  # pragma: no cover - hardware dependent
            print(f"[AudioAnalyzer] could not open input stream: {exc}")
            self._available = False
            return False

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
        self._stream = None
        self._running = False

    # ------------------------------------------------------------------ #
    # Audio thread
    # ------------------------------------------------------------------ #
    def _callback(self, indata, frames, time_info, status):  # noqa: D401
        if status:
            # Overflows are non-fatal; we just analyse what we have.
            pass
        samples = indata[:, 0] if indata.ndim > 1 else indata

        rms = float(np.sqrt(np.mean(np.square(samples))) + 1e-9)
        raw = min(1.0, rms * self.cfg.input_gain)

        n = min(self.cfg.block_size, samples.shape[0])
        windowed = samples[:n] * self._window[:n]
        spec = np.abs(np.fft.rfft(windowed, n=self.cfg.fft_bins * 2))
        spec = spec[: self.cfg.fft_bins].astype(np.float32)
        m = float(spec.max())
        if m > 1e-6:
            spec /= m

        with self._lock:
            # Exponential smoothing (attack). The visuals must never use raw.
            self._smoothed_level += (raw - self._smoothed_level) * self.cfg.smoothing
            self._peak = max(self._peak * 0.96, raw)
            self._spectrum = spec

    # ------------------------------------------------------------------ #
    # Render-thread polling API
    # ------------------------------------------------------------------ #
    def poll(self) -> float:
        """Return the current smoothed level, applying gentle release decay.

        Called once per rendered frame. Between audio callbacks the level
        relaxes toward zero so the orb settles smoothly after speech stops.
        """
        with self._lock:
            self._smoothed_level *= self.cfg.decay
            return self._smoothed_level

    @property
    def level(self) -> float:
        with self._lock:
            return self._smoothed_level

    @property
    def peak(self) -> float:
        with self._lock:
            return self._peak

    @property
    def spectrum(self) -> np.ndarray:
        with self._lock:
            return self._spectrum.copy()

    # Convenience: low / mid / high band energies (handy for state logic).
    def bands(self) -> tuple[float, float, float]:
        spec = self.spectrum
        third = max(1, len(spec) // 3)
        low = float(spec[:third].mean())
        mid = float(spec[third : 2 * third].mean())
        high = float(spec[2 * third :].mean())
        return low, mid, high

    @staticmethod
    def list_devices() -> str:
        if sd is None:
            return "sounddevice not installed"
        return str(sd.query_devices())

"""
Clap Detector — Monitors the microphone for a double-clap sound.

Runs in a daemon thread with its own sounddevice InputStream.
Only active when JARVIS is idle (LISTENING state or muted) to avoid
false positives during conversation.

A "clap" is detected when RMS audio energy exceeds a threshold within
a short analysis window. A "double clap" is two claps within 0.4–1.2 s.
"""

import threading
import time

import numpy as np
import sounddevice as sd


SAMPLE_RATE   = 16000   # Hz — matches JarvisLive mic settings
CHANNELS      = 1        # mono
DTYPE         = "int16"
BLOCK_SIZE    = 1024     # samples per callback
THRESHOLD     = 8000     # RMS energy — tune if needed
CLAP_WINDOW   = 0.15     # seconds — max duration of a single clap spike
MIN_GAP       = 0.4      # seconds — minimum gap between two claps
MAX_GAP       = 1.2      # seconds — maximum gap between two claps
COOLDOWN      = 2.0      # seconds — ignore claps this long after a detection


class ClapDetector:
    """Threaded double-clap detector.

    Args:
        on_double_clap: callback fired when a double-clap is detected.
        on_state_change: optional callback(armed: bool) for UI feedback.
        threshold: RMS energy threshold for a single clap (default 8000).
        sample_rate: audio sample rate in Hz.
        cooldown: seconds to wait after a detection before re-arming.
    """

    def __init__(
        self,
        on_double_clap: callable,
        on_state_change: callable = None,
        threshold: int = THRESHOLD,
        sample_rate: int = SAMPLE_RATE,
        cooldown: float = COOLDOWN,
    ):
        self._on_double_clap  = on_double_clap
        self._on_state_change = on_state_change
        self._threshold       = threshold
        self._sample_rate     = sample_rate
        self._cooldown        = cooldown

        self._running      = False
        self._armed        = True          # starts armed
        self._thread: threading.Thread | None = None
        self._last_clap_t  = 0.0
        self._clap_count    = 0
        self._lock          = threading.Lock()

    # ── public API ──────────────────────────────────────────────

    def start(self):
        """Start the clap detection background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[ClapDetector] ✅ Started.")

    def stop(self):
        """Stop the detector thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
        print("[ClapDetector] ⏹ Stopped.")

    def set_armed(self, armed: bool):
        """Enable or disable detection (e.g. disable while JARVIS is speaking)."""
        with self._lock:
            self._armed = armed
            if not armed:
                self._clap_count = 0
        if self._on_state_change:
            try:
                self._on_state_change(armed)
            except Exception:
                pass

    # ── internal loop ───────────────────────────────────────────

    def _loop(self):
        """Open a dedicated InputStream and process audio blocks."""
        try:
            with sd.InputStream(
                samplerate=self._sample_rate,
                channels=CHANNELS,
                dtype=DTYPE,
                blocksize=BLOCK_SIZE,
                callback=self._audio_callback,
            ):
                while self._running:
                    time.sleep(0.1)
        except Exception as e:
            print(f"[ClapDetector] ❌ Stream error: {e}")

    # ── audio callback (called from sounddevice thread) ────────

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            print(f"[ClapDetector] ⚠️ {status}")

        with self._lock:
            if not self._armed or not self._running:
                return

        # RMS energy of this block
        rms = float(np.sqrt(np.mean(indata.astype(np.float64) ** 2)))

        if rms < self._threshold:
            return

        now = time.time()

        with self._lock:
            if not self._armed:
                return

            # Cooldown check
            if now - self._last_clap_t < self._cooldown and self._clap_count == 0:
                return

            if self._clap_count == 0:
                # First clap
                self._clap_count = 1
                self._last_clap_t = now
                print(f"[ClapDetector] 👏 Clap 1 detected (rms={rms:.0f})")
            else:
                gap = now - self._last_clap_t
                if MIN_GAP <= gap <= MAX_GAP:
                    # Second clap — double clap detected!
                    self._clap_count = 0
                    self._last_clap_t = now
                    print(f"[ClapDetector] 👏👏 DOUBLE CLAP! (rms={rms:.0f})")
                    self._fire()
                elif gap < MIN_GAP:
                    # Too soon — ignore, keep waiting
                    pass
                else:
                    # Too late — reset and treat as first clap
                    self._clap_count = 1
                    self._last_clap_t = now
                    print(f"[ClapDetector] 👏 Clap 1 (reset, rms={rms:.0f})")

    def _fire(self):
        """Fire the callback outside the lock to avoid deadlocks."""
        cb = self._on_double_clap
        # Briefly disarm so the callback's audio doesn't re-trigger
        self._armed = False
        if cb:
            try:
                cb()
            except Exception as e:
                print(f"[ClapDetector] ❌ Callback error: {e}")
        # Re-arm after cooldown via a timer
        threading.Timer(self._cooldown, self._rearm).start()

    def _rearm(self):
        with self._lock:
            self._armed = True
            self._clap_count = 0
        print("[ClapDetector] 🔄 Re-armed.")

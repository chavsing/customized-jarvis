"""
Wake Phrase Monitor — Watches Gemini's input transcription for the wake phrase.

After a double-clap arms the monitor, it listens for "wake up daddy's home"
in the transcribed speech from Gemini Live. Uses fuzzy matching to handle
minor ASR variations.

The monitor auto-expires after a configurable timeout (default 5 seconds).
"""

import re
import threading
import time


# Accept common ASR variations
_WAKE_PATTERNS = [
    re.compile(r"wake\s+up\s+daddy'?s?\s+home", re.IGNORECASE),
    re.compile(r"wake\s+up\s+daddys\s+home", re.IGNORECASE),
    re.compile(r"wake\s+up\s+daddy'?s?\s+hom", re.IGNORECASE),   # partial
    re.compile(r"wake\s+up\s+father'?s?\s+home", re.IGNORECASE), # variation
]

_DEFAULT_TIMEOUT = 5.0  # seconds to wait for wake phrase after arming


class WakeMonitor:
    """Monitors transcribed speech for the wake phrase after a double clap.

    Args:
        on_wake: callback fired when the wake phrase is detected.
        timeout: seconds to wait after arming before auto-expiring.
    """

    def __init__(self, on_wake: callable, timeout: float = _DEFAULT_TIMEOUT):
        self._on_wake   = on_wake
        self._timeout   = timeout
        self._armed     = False
        self._timer: threading.Timer | None = None
        self._lock      = threading.Lock()

    # ── public API ──────────────────────────────────────────────

    def arm(self):
        """Arm the monitor — called when a double clap is detected."""
        with self._lock:
            self._armed = True
            # Cancel any existing timer
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(self._timeout, self._expire)
            self._timer.daemon = True
            self._timer.start()
        print("[WakeMonitor] 🔫 Armed — listening for wake phrase...")

    def disarm(self):
        """Manually disarm the monitor."""
        with self._lock:
            self._armed = False
            if self._timer:
                self._timer.cancel()
                self._timer = None
        print("[WakeMonitor] 🔒 Disarmed.")

    def on_transcript(self, text: str):
        """Feed a transcription string from Gemini Live.

        Called by JarvisLive every time an input_transcription arrives.
        """
        if not text:
            return
        with self._lock:
            if not self._armed:
                return
        if self._matches(text):
            with self._lock:
                self._armed = False
                if self._timer:
                    self._timer.cancel()
                    self._timer = None
            print(f"[WakeMonitor] 🎯 Wake phrase detected: \"{text}\"")
            if self._on_wake:
                try:
                    self._on_wake()
                except Exception as e:
                    print(f"[WakeMonitor] ❌ Callback error: {e}")

    @property
    def is_armed(self) -> bool:
        with self._lock:
            return self._armed

    # ── internal ────────────────────────────────────────────────

    def _expire(self):
        """Auto-expire after timeout."""
        with self._lock:
            was_armed = self._armed
            self._armed = False
            self._timer = None
        if was_armed:
            print("[WakeMonitor] ⏰ Expired — wake phrase not detected in time.")

    @staticmethod
    def _matches(text: str) -> bool:
        for pat in _WAKE_PATTERNS:
            if pat.search(text):
                return True
        return False

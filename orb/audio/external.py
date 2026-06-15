"""Audio analyzer driven externally by the host (JARVIS), not by its own mic.

JARVIS already measures its output-audio amplitude (set_audio_level). Rather than
opening a second microphone stream, we feed that level here so the orb reacts to
JARVIS's voice. Implements the same poll()/level interface the renderer expects.
"""

from __future__ import annotations


class ExternalAnalyzer:
    def __init__(self, decay: float = 0.90):
        self._level = 0.0
        self._decay = decay
        self._available = True

    @property
    def available(self) -> bool:
        return self._available

    def start(self) -> bool:
        return True

    def stop(self) -> None:
        pass

    def set_level(self, value: float) -> None:
        """Host feeds the latest amplitude (0..1). Keeps the highest recent value."""
        v = max(0.0, min(1.0, float(value)))
        if v > self._level:
            self._level = v

    def poll(self) -> float:
        """Called once per rendered frame; relaxes toward zero between feeds."""
        self._level *= self._decay
        return self._level

    @property
    def level(self) -> float:
        return self._level

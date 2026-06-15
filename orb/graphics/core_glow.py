"""Core glow layer — the molten heart with breathing + audio reactivity."""

from __future__ import annotations

import math

from ..config import CONFIG
from .gl_utils import FullscreenLayer


class CoreGlow(FullscreenLayer):
    FRAG = "core.frag"

    def draw(self, time: float, aspect: float, audio: float, *, glow: float,
             flash: float) -> None:
        # Smooth breathing: a slow sine, eased so it never feels mechanical.
        phase = (time / CONFIG.timings.breathing_period) * math.tau
        breath = 0.5 + 0.5 * math.sin(phase)

        pal = CONFIG.palette
        self.render(
            {
                "u_time": time,
                "u_aspect": aspect,
                "u_audio": audio,
                "u_radius": CONFIG.geometry.core_radius,
                "u_breath": breath,
                "u_glow": glow,
                "u_flash": flash,
                "u_color_hot": pal.core_hot,
                "u_color_warm": pal.core_warm,
            }
        )

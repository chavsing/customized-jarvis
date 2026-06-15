"""Light rays layer — radial god-rays emanating from the core."""

from __future__ import annotations

from ..config import CONFIG
from .gl_utils import FullscreenLayer


class LightRays(FullscreenLayer):
    FRAG = "rays.frag"

    def draw(self, time: float, aspect: float, audio: float, *, intensity: float,
             length: float, flicker: float) -> None:
        self.render(
            {
                "u_time": time,
                "u_aspect": aspect,
                "u_audio": audio,
                "u_ray_count": float(CONFIG.geometry.ray_count),
                "u_line_count": float(CONFIG.geometry.line_count),
                "u_intensity": intensity,
                "u_length": length,
                "u_flicker": flicker,
                "u_color": CONFIG.palette.rays,
            }
        )

"""Background glow layer."""

from __future__ import annotations

from ..config import CONFIG
from .gl_utils import FullscreenLayer


class Background(FullscreenLayer):
    FRAG = "background.frag"

    def draw(self, time: float, aspect: float, audio: float) -> None:
        pal = CONFIG.palette
        self.render(
            {
                "u_time": time,
                "u_aspect": aspect,
                "u_audio": audio,
                "u_radius": CONFIG.geometry.background_radius,
                "u_color_a": pal.background_a,
                "u_color_b": pal.background_b,
                "u_nebula_a": pal.nebula_a,
                "u_nebula_b": pal.nebula_b,
            }
        )

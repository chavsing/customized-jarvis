"""Energy ring layer — procedurally distorted luminous annulus."""

from __future__ import annotations

from ..config import CONFIG
from .gl_utils import FullscreenLayer


class EnergyRing(FullscreenLayer):
    FRAG = "energy_ring.frag"

    def draw(self, time: float, aspect: float, audio: float, *, turbulence: float,
             ripple: float, intensity: float) -> None:
        self.render(
            {
                "u_time": time,
                "u_aspect": aspect,
                "u_audio": audio,
                "u_radius": CONFIG.geometry.energy_radius,
                "u_sides": float(CONFIG.geometry.energy_sides),
                "u_turbulence": turbulence,
                "u_ripple": ripple,
                "u_color": CONFIG.palette.energy,
                "u_intensity": intensity,
            }
        )

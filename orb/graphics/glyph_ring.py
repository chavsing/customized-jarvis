"""Glyph ring layer — renders a rotating annulus of procedural runes.

A single class drives both rings; the renderer creates two instances with
different radii, rotation directions/periods and glyph counts.
"""

from __future__ import annotations

import math

import moderngl

from ..config import CONFIG
from .gl_utils import FullscreenLayer
from .glyph_atlas import make_glyph_texture


class GlyphRing(FullscreenLayer):
    FRAG = "glyph_ring.frag"

    def __init__(
        self,
        ctx: moderngl.Context,
        quad: moderngl.Buffer,
        *,
        radius: float,
        width: float,
        repeat: int,
        period: float,
        clockwise: bool,
        glyph_seed: int,
        cache_name: str,
    ):
        super().__init__(ctx, quad)
        self.radius = radius
        self.width = width
        self.repeat = repeat
        self.period = period
        self.direction = -1.0 if clockwise else 1.0
        self.texture = make_glyph_texture(
            ctx, glyph_count=repeat, cell=192, seed=glyph_seed, cache_name=cache_name
        )

    def draw(self, time: float, aspect: float, audio: float, rotation_mult: float,
             intensity: float) -> None:
        # One full turn per `period` seconds, scaled by the state rotation mult.
        rotation = self.direction * (time / self.period) * math.tau * rotation_mult
        self.texture.use(location=0)
        self.render(
            {
                "u_glyphs": 0,
                "u_time": time,
                "u_aspect": aspect,
                "u_audio": audio,
                "u_rotation": rotation,
                "u_radius": self.radius,
                "u_width": self.width,
                "u_repeat": float(self.repeat),
                "u_color": CONFIG.palette.ring_gold,
                "u_intensity": intensity,
            }
        )

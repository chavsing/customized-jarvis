"""Orb renderer.

Owns the ModernGL context and every visual layer. Each frame it renders the
orb's layers additively into an HDR offscreen buffer, then runs the bloom +
chromatic-aberration post pass to the screen framebuffer.

The renderer is deliberately decoupled from PyQt and from audio capture: it is
fed a `time`, `dt`, a smoothed `audio` level (0..1) and a blended `StateParams`
each frame. That makes it trivially testable and host-agnostic.
"""

from __future__ import annotations

import random

import moderngl

from .config import CONFIG, StateParams
from .graphics import (
    Background,
    CoreGlow,
    EnergyRing,
    GlyphRing,
    LightRays,
    ParticleSystem,
    PostProcessor,
)
from .graphics.gl_utils import fullscreen_quad


class OrbRenderer:
    def __init__(self, ctx: moderngl.Context):
        self.ctx = ctx
        self.quad = fullscreen_quad(ctx)

        geo = CONFIG.geometry
        tim = CONFIG.timings

        self.background = Background(ctx, self.quad)
        self.outer_ring = GlyphRing(
            ctx, self.quad,
            radius=geo.outer_ring_radius, width=geo.outer_ring_width,
            repeat=geo.glyph_count_outer, period=tim.outer_ring_period,
            clockwise=True, glyph_seed=7, cache_name="glyphs_outer.png",
        )
        self.inner_ring = GlyphRing(
            ctx, self.quad,
            radius=geo.inner_ring_radius, width=geo.inner_ring_width,
            repeat=geo.glyph_count_inner, period=tim.inner_ring_period,
            clockwise=False, glyph_seed=23, cache_name="glyphs_inner.png",
        )
        self.energy_ring = EnergyRing(ctx, self.quad)
        self.core = CoreGlow(ctx, self.quad)
        self.rays = LightRays(ctx, self.quad)
        self.particles = ParticleSystem(ctx, self.quad)
        self.post = PostProcessor(ctx, self.quad)

        self.scene_fbo = None
        self._w = self._h = 0
        self._aspect = 1.0
        self._flash = 0.0
        self._rng = random.Random(99)

        ctx.enable(moderngl.PROGRAM_POINT_SIZE)

    # ------------------------------------------------------------------ #
    def resize(self, width: int, height: int) -> None:
        width = max(1, width)
        height = max(1, height)
        if (width, height) == (self._w, self._h):
            return
        self._w, self._h = width, height
        self._aspect = width / height
        if self.scene_fbo is not None:
            self.scene_fbo.color_attachments[0].release()
            self.scene_fbo.release()
        tex = self.ctx.texture((width, height), 4, dtype="f2")
        tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.scene_fbo = self.ctx.framebuffer(tex)
        self.post.resize(width, height)

    # ------------------------------------------------------------------ #
    def _update_flash(self, dt: float, params: StateParams) -> None:
        # Micro-flashes near the centre (THINKING / SPEAKING). Poisson-ish.
        if self._rng.random() < params.flash_rate * dt:
            self._flash = 1.0
        self._flash *= pow(0.0008, dt)  # fast exponential decay (~ a few frames)

    # ------------------------------------------------------------------ #
    def render(self, time: float, dt: float, audio: float, params: StateParams,
               screen_fbo, dpr: float = 1.0) -> None:
        if self.scene_fbo is None:
            return
        ctx = self.ctx
        aspect = self._aspect
        self._update_flash(dt, params)

        # --- Render orb layers additively into the HDR scene buffer. ---
        self.scene_fbo.use()
        ctx.clear(0.0, 0.0, 0.0, 0.0)
        ctx.enable(moderngl.BLEND)
        ctx.blend_func = (moderngl.ONE, moderngl.ONE)  # additive

        self.background.draw(time, aspect, audio)
        self.outer_ring.draw(time, aspect, audio, params.rotation_mult,
                             intensity=params.glow_intensity * 0.9)
        self.inner_ring.draw(time, aspect, audio, params.rotation_mult,
                             intensity=params.glow_intensity * 0.9)
        self.energy_ring.draw(time, aspect, audio,
                              turbulence=params.energy_turbulence,
                              ripple=params.ripple_strength,
                              intensity=params.glow_intensity)
        self.rays.draw(time, aspect, audio, intensity=params.ray_intensity,
                       length=params.ray_length,
                       flicker=min(1.0, params.flash_rate * 0.3))
        self.core.draw(time, aspect, audio, glow=params.glow_intensity,
                       flash=self._flash)

        # Particles last so they sparkle over the glow.
        self.particles.update(dt, audio, params.particle_activity)
        self.particles.render(aspect, dpr, audio, params.particle_activity)

        # --- Post processing to screen. ---
        post = CONFIG.post
        bloom_intensity = post.bloom_intensity_idle + post.bloom_intensity_gain * audio
        bloom_intensity *= params.glow_intensity
        chromatic = post.chromatic_base + post.chromatic_gain * audio

        self.post.process(
            self.scene_fbo.color_attachments[0],
            screen_fbo,
            bloom_intensity=bloom_intensity,
            chromatic=chromatic,
            audio=audio,
        )

    # ------------------------------------------------------------------ #
    def release(self) -> None:
        try:
            if self.scene_fbo is not None:
                self.scene_fbo.color_attachments[0].release()
                self.scene_fbo.release()
        except Exception:
            pass

"""GPU-rendered, CPU-simulated particle system.

Particles are born near the core and drift outward, accelerating with audio.
Simulation is vectorised NumPy (a few thousand particles is trivial at 60 FPS);
only the live particles are uploaded to the VBO each frame and drawn as soft
additive point sprites.
"""

from __future__ import annotations

import moderngl
import numpy as np

from ..config import CONFIG
from .gl_utils import make_program


class ParticleSystem:
    def __init__(self, ctx: moderngl.Context, quad: moderngl.Buffer):
        self.ctx = ctx
        self.cfg = CONFIG.particles
        n = self.cfg.max_particles

        self.pos = np.zeros((n, 2), dtype=np.float32)
        self.vel = np.zeros((n, 2), dtype=np.float32)
        self.life = np.zeros(n, dtype=np.float32)       # remaining seconds
        self.max_life = np.ones(n, dtype=np.float32)
        self.size = np.zeros(n, dtype=np.float32)
        self.seed = np.random.rand(n).astype(np.float32)
        self._emit_accum = 0.0
        self._rng = np.random.default_rng(1234)

        self.prog = make_program(ctx, "particle.vert", "particle.frag")
        # 5 floats per vertex: pos.xy, life01, size, seed
        self.vbo = ctx.buffer(reserve=n * 5 * 4, dynamic=True)
        self.vao = ctx.vertex_array(
            self.prog,
            [(self.vbo, "2f 1f 1f 1f", "in_pos", "in_life", "in_size", "in_seed")],
        )

    # ------------------------------------------------------------------ #
    def _spawn(self, count: int, audio: float) -> None:
        dead = np.flatnonzero(self.life <= 0.0)
        if dead.size == 0 or count <= 0:
            return
        idx = dead[:count]
        k = idx.size

        ang = self._rng.uniform(0.0, 2.0 * np.pi, k).astype(np.float32)
        r0 = CONFIG.geometry.core_radius * self._rng.uniform(0.3, 0.9, k).astype(np.float32)
        cos, sin = np.cos(ang), np.sin(ang)
        self.pos[idx, 0] = cos * r0
        self.pos[idx, 1] = sin * r0

        speed = self.cfg.base_speed + audio * self.cfg.speed_audio_gain
        speed = speed * self._rng.uniform(0.6, 1.4, k).astype(np.float32)
        # Mostly radial, with a touch of tangential swirl.
        swirl = self._rng.uniform(-0.4, 0.4, k).astype(np.float32)
        self.vel[idx, 0] = cos * speed - sin * swirl * speed
        self.vel[idx, 1] = sin * speed + cos * swirl * speed

        self.max_life[idx] = self._rng.uniform(
            self.cfg.min_life, self.cfg.max_life, k
        ).astype(np.float32)
        self.life[idx] = self.max_life[idx]
        self.size[idx] = self._rng.uniform(
            self.cfg.size_min, self.cfg.size_max, k
        ).astype(np.float32)
        self.seed[idx] = self._rng.random(k).astype(np.float32)

    # ------------------------------------------------------------------ #
    def update(self, dt: float, audio: float, activity: float) -> None:
        alive = self.life > 0.0
        if np.any(alive):
            # Outward drift with mild drag; gentle upward buoyancy for life.
            self.pos[alive] += self.vel[alive] * dt
            self.vel[alive] *= (1.0 - 0.6 * dt)
            self.life[alive] -= dt

        # Emission: base trickle plus activity- and audio-scaled bursts.
        rate = (
            self.cfg.base_emission * max(activity, 0.05)
            + self.cfg.speaking_emission * activity * audio
        )
        self._emit_accum += rate * dt
        count = int(self._emit_accum)
        if count > 0:
            self._emit_accum -= count
            self._spawn(count, audio)

    # ------------------------------------------------------------------ #
    def render(self, aspect: float, dpr: float, audio: float, activity: float) -> None:
        alive = np.flatnonzero(self.life > 0.0)
        if alive.size == 0:
            return

        life01 = (self.life[alive] / np.maximum(self.max_life[alive], 1e-4)).astype("f4")
        data = np.empty((alive.size, 5), dtype="f4")
        data[:, 0:2] = self.pos[alive]
        data[:, 2] = life01
        data[:, 3] = self.size[alive]
        data[:, 4] = self.seed[alive]

        self.vbo.write(data.tobytes())
        self.prog["u_aspect"].value = aspect
        self.prog["u_dpr"].value = dpr
        self.prog["u_color"].value = CONFIG.palette.particles
        self.prog["u_intensity"].value = float(np.clip(0.5 + activity + audio, 0.4, 2.0))
        self.vao.render(moderngl.POINTS, vertices=alive.size)

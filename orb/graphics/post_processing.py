"""Post-processing: bloom + chromatic aberration final composite.

Pipeline:
    scene_tex --bright-pass--> bloom (downsampled)
                  |
                  +--> separable Gaussian blur (ping-pong, N iterations)
                  |
    scene_tex + bloom --composite (+ chromatic aberration)--> screen
"""

from __future__ import annotations

import moderngl

from ..config import CONFIG
from .gl_utils import make_program, set_uniform


class PostProcessor:
    def __init__(self, ctx: moderngl.Context, quad: moderngl.Buffer):
        self.ctx = ctx
        self.cfg = CONFIG.post
        self.extract = make_program(ctx, "fullscreen.vert", "bloom_extract.frag")
        self.blur = make_program(ctx, "fullscreen.vert", "blur.frag")
        self.composite = make_program(ctx, "fullscreen.vert", "composite.frag")

        self.vao_extract = ctx.vertex_array(self.extract, [(quad, "2f", "in_pos")])
        self.vao_blur = ctx.vertex_array(self.blur, [(quad, "2f", "in_pos")])
        self.vao_composite = ctx.vertex_array(self.composite, [(quad, "2f", "in_pos")])

        self._w = self._h = 0
        self._bw = self._bh = 0
        self.bloom_a = None
        self.bloom_b = None

    def resize(self, width: int, height: int) -> None:
        if (width, height) == (self._w, self._h):
            return
        self._w, self._h = width, height
        ds = max(1, self.cfg.bloom_downsample)
        self._bw = max(1, width // ds)
        self._bh = max(1, height // ds)
        for fbo in (self.bloom_a, self.bloom_b):
            if fbo is not None:
                fbo.color_attachments[0].release()
                fbo.release()
        self.bloom_a = self.ctx.framebuffer(
            self.ctx.texture((self._bw, self._bh), 4, dtype="f2")
        )
        self.bloom_b = self.ctx.framebuffer(
            self.ctx.texture((self._bw, self._bh), 4, dtype="f2")
        )
        for fbo in (self.bloom_a, self.bloom_b):
            fbo.color_attachments[0].filter = (moderngl.LINEAR, moderngl.LINEAR)
            fbo.color_attachments[0].repeat_x = False
            fbo.color_attachments[0].repeat_y = False

    def process(self, scene_tex, screen_fbo, *, bloom_intensity: float,
                chromatic: float, audio: float, iterations: int = 3) -> None:
        ctx = self.ctx
        ctx.disable(moderngl.BLEND)

        # 1) Bright-pass extract into bloom_a.
        self.bloom_a.use()
        ctx.clear(0.0, 0.0, 0.0, 0.0)
        scene_tex.use(0)
        self.extract["u_scene"].value = 0
        self.extract["u_threshold"].value = self.cfg.bloom_threshold
        self.vao_extract.render(moderngl.TRIANGLES)

        # 2) Separable Gaussian blur, ping-ponging between a and b.
        texel_x = 1.0 / self._bw
        texel_y = 1.0 / self._bh
        src, dst = self.bloom_a, self.bloom_b
        for _ in range(iterations):
            # horizontal
            dst.use()
            ctx.clear(0.0, 0.0, 0.0, 0.0)
            src.color_attachments[0].use(0)
            self.blur["u_tex"].value = 0
            self.blur["u_direction"].value = (texel_x, 0.0)
            self.vao_blur.render(moderngl.TRIANGLES)
            src, dst = dst, src
            # vertical
            dst.use()
            ctx.clear(0.0, 0.0, 0.0, 0.0)
            src.color_attachments[0].use(0)
            self.blur["u_tex"].value = 0
            self.blur["u_direction"].value = (0.0, texel_y)
            self.vao_blur.render(moderngl.TRIANGLES)
            src, dst = dst, src
        bloom_result = src  # final blurred bloom

        # 3) Composite to the target framebuffer (the screen).
        screen_fbo.use()
        ctx.clear(0.0, 0.0, 0.0, 0.0)
        scene_tex.use(0)
        bloom_result.color_attachments[0].use(1)
        set_uniform(self.composite, "u_scene", 0)
        set_uniform(self.composite, "u_bloom", 1)
        set_uniform(self.composite, "u_bloom_intensity", bloom_intensity)
        set_uniform(self.composite, "u_chromatic", chromatic)
        set_uniform(self.composite, "u_audio", audio)
        self.vao_composite.render(moderngl.TRIANGLES)

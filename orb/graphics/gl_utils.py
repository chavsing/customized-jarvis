"""Shared ModernGL helpers: shader loading, include injection, fullscreen quad."""

from __future__ import annotations

from pathlib import Path

import moderngl
import numpy as np

_SHADER_DIR = Path(__file__).parent / "shaders"
_INCLUDE_CACHE: dict[str, str] = {}


def _load_include(name: str) -> str:
    if name not in _INCLUDE_CACHE:
        path = _SHADER_DIR / f"_{name}.glsl"
        _INCLUDE_CACHE[name] = path.read_text(encoding="utf-8")
    return _INCLUDE_CACHE[name]


def _resolve_includes(src: str) -> str:
    """Replace `#pragma include <name>` lines with the include's contents."""
    out_lines = []
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("#pragma include"):
            name = stripped.split()[-1].strip('"')
            out_lines.append(_load_include(name))
        else:
            out_lines.append(line)
    return "\n".join(out_lines)


def read_shader(filename: str) -> str:
    return _resolve_includes((_SHADER_DIR / filename).read_text(encoding="utf-8"))


def make_program(ctx: moderngl.Context, vert: str, frag: str) -> moderngl.Program:
    return ctx.program(vertex_shader=read_shader(vert), fragment_shader=read_shader(frag))


def fullscreen_quad(ctx: moderngl.Context) -> moderngl.Buffer:
    """A buffer of two triangles covering the screen in NDC."""
    verts = np.array(
        [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
        dtype="f4",
    )
    return ctx.buffer(verts.tobytes())


def set_uniform(prog: moderngl.Program, name: str, value) -> None:
    """Set a uniform if it exists (shaders may optimise some away)."""
    if name in prog:
        prog[name].value = value


class FullscreenLayer:
    """Base for any layer drawn as a fullscreen fragment shader.

    Subclasses implement `uniforms(ctx_state)` returning a dict of uniform
    name -> value; the base handles VAO creation and the additive draw.
    """

    FRAG: str = ""

    def __init__(self, ctx: moderngl.Context, quad: moderngl.Buffer):
        self.ctx = ctx
        self.prog = make_program(ctx, "fullscreen.vert", self.FRAG)
        self.vao = ctx.vertex_array(self.prog, [(quad, "2f", "in_pos")])

    def apply(self, values: dict) -> None:
        for name, val in values.items():
            set_uniform(self.prog, name, val)

    def render(self, values: dict) -> None:
        self.apply(values)
        self.vao.render(moderngl.TRIANGLES)


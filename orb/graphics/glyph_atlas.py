"""Procedural glyph-strip generator.

Rather than ship a font, we synthesise a horizontal strip of arcane-looking
runes with Pillow at startup. Each glyph is built from a few random strokes,
arcs and dots on a transparent background; the alpha channel is the "ink" the
ring shader samples. The result is deterministic (seeded) so the orb looks the
same across runs, and is cached to assets/ so we only generate it once.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

import moderngl
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

_ASSET_DIR = Path(__file__).parent.parent / "assets"


def _draw_glyph(draw: ImageDraw.ImageDraw, x0: int, cell: int, rng: random.Random) -> None:
    """Draw one ornate, inscribed-looking rune inside the cell.

    Each rune is composed from one of several archetypes (spine+serifs, looped,
    arc, enclosed, branching) so the band reads as distinct *characters*. A
    central spine is allowed — legibility wins — but every rune also carries
    strong horizontal / curved features so it doesn't collapse to a bare radial
    line once wrapped onto the ring.
    """
    pad = int(cell * 0.18)
    left, right = x0 + pad, x0 + cell - pad
    top, bottom = pad, cell - pad
    cx, cy = (left + right) // 2, (top + bottom) // 2
    w = max(4, cell // 11)          # bold strokes survive minification
    col = 255
    span = right - left

    def line(a, b):
        draw.line([a, b], fill=col, width=w, joint="curve")

    def arc(box, a0, a1):
        draw.arc(box, a0, a1, fill=col, width=w)

    archetype = rng.randint(0, 4)

    if archetype == 0:                       # spine with serifs + node
        line((cx, top), (cx, bottom))
        line((left, top), (right, top))
        line((cx - span // 4, bottom), (cx + span // 4, bottom))
        if rng.random() < 0.6:
            line((cx, cy), (right, cy - span // 4))
        if rng.random() < 0.5:
            r = w
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)

    elif archetype == 1:                     # looped / enclosed form
        arc([left, top, right, bottom], rng.randint(20, 90), rng.randint(250, 340))
        line((cx, cy), (cx, bottom))
        if rng.random() < 0.5:
            line((left, cy), (right, cy))

    elif archetype == 2:                     # double-arc (S / wave)
        mid = cy
        arc([left, top, right, mid], 180, 360)
        arc([left, mid, right, bottom], 0, 180)
        line((cx, top), (cx, bottom))

    elif archetype == 3:                     # enclosed diamond / triangle
        if rng.random() < 0.5:
            draw.polygon([(cx, top), (right, cy), (cx, bottom), (left, cy)],
                         outline=col, width=w)
        else:
            draw.polygon([(cx, top), (right, bottom), (left, bottom)],
                         outline=col, width=w)
        line((cx, cy), (cx, bottom))

    else:                                    # branching trunk
        line((cx, top), (cx, bottom))
        for _ in range(rng.randint(2, 3)):
            y = rng.randint(top + w, bottom - w)
            dx = rng.choice([-1, 1]) * rng.randint(span // 4, span // 2)
            dy = rng.choice([-1, 1]) * rng.randint(0, span // 4)
            line((cx, y), (max(left, min(right, cx + dx)),
                           max(top, min(bottom, y + dy))))


def generate_glyph_strip(
    glyph_count: int = 48,
    cell: int = 128,
    seed: int = 7,
    cache_name: str | None = None,
) -> Image.Image:
    """Return an RGBA strip of `glyph_count` runes, each `cell` px square."""
    cache_path = None
    if cache_name:
        cache_path = _ASSET_DIR / cache_name
        if cache_path.exists():
            try:
                return Image.open(cache_path).convert("RGBA")
            except Exception:
                pass

    rng = random.Random(seed)
    # Supersample 2x then downscale for crisp anti-aliased strokes.
    ss = 2
    width = glyph_count * cell
    big = Image.new("L", (width * ss, cell * ss), 0)
    draw = ImageDraw.Draw(big)
    for i in range(glyph_count):
        _draw_glyph(draw, i * cell * ss, cell * ss, rng)
    img = big.resize((width, cell), Image.LANCZOS)

    # A whisper of blur so the runes glow rather than look like hard decals.
    img = img.filter(ImageFilter.GaussianBlur(radius=cell * 0.006))

    # Compose into RGBA: warm-gold ink, alpha from the drawn strokes.
    alpha = np.array(img, dtype=np.float32) / 255.0
    rgba = np.zeros((cell, width, 4), dtype=np.uint8)
    rgba[..., 0] = 255
    rgba[..., 1] = 210
    rgba[..., 2] = 130
    rgba[..., 3] = (alpha * 255).astype(np.uint8)
    out = Image.fromarray(rgba, "RGBA")

    if cache_path is not None:
        try:
            _ASSET_DIR.mkdir(parents=True, exist_ok=True)
            out.save(cache_path)
        except Exception:
            pass
    return out


def make_glyph_texture(
    ctx: moderngl.Context,
    glyph_count: int = 48,
    cell: int = 128,
    seed: int = 7,
    cache_name: str | None = None,
) -> moderngl.Texture:
    img = generate_glyph_strip(glyph_count, cell, seed, cache_name)
    tex = ctx.texture(img.size, 4, img.tobytes())
    tex.build_mipmaps()
    tex.repeat_x = True
    tex.repeat_y = False
    # Plain trilinear, NO anisotropy: anisotropic filtering smears the runes
    # radially along the high-minification (tangential) axis, turning the ring
    # into "fur". Without it the glyphs stay legible.
    tex.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
    tex.anisotropy = 1.0
    return tex

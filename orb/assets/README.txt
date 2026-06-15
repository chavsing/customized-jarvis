Assets
======

orb_reference.png
    The artistic reference image for the orb. It is used by humans only — the
    application never loads or scales it at runtime. Every visual element (glyph
    rings, energy ring, glow, rays, particles) is generated procedurally on the
    GPU. Drop your reference image here as `orb_reference.png` if you want it
    alongside the project.

glyphs_inner.png / glyphs_outer.png
    Generated automatically on first launch by app/graphics/glyph_atlas.py — a
    horizontal strip of procedural runes used as the glyph-ring texture. Safe to
    delete; they will be regenerated (deterministically) next run.

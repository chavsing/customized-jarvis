#version 330

// Glyph ring: samples a procedurally generated strip of arcane runes wrapped
// around an annulus. Rotation, radius and width come from uniforms so a single
// shader serves both the inner and outer rings.

in vec2 v_uv;
out vec4 f_color;

uniform sampler2D u_glyphs;   // horizontal strip atlas (RGBA, alpha = ink)
uniform float u_time;
uniform float u_aspect;
uniform float u_audio;
uniform float u_rotation;     // radians
uniform float u_radius;       // centre radius (0..1 of half-viewport)
uniform float u_width;        // band half-width
uniform float u_repeat;       // glyph repetitions around the circle
uniform vec3  u_color;
uniform float u_intensity;

#pragma include noise

void main() {
    vec2 p = (v_uv * 2.0 - 1.0);
    p.x *= u_aspect;
    float r = length(p);
    float ang = atan(p.y, p.x);

    // Radial band mask with soft edges (extended a touch for the glow + lines).
    float d = abs(r - u_radius);
    float reach = u_width * 1.5;
    if (d > reach) { f_color = vec4(0.0); return; }
    float band = smoothstep(u_width, u_width * 0.4, d);

    // Map angle to the glyph strip. The atlas already holds `u_repeat` glyphs
    // across its [0,1] width, so going once around the circle must traverse the
    // atlas exactly once — DO NOT multiply the texture coord by repeat (that
    // squishes every glyph into every cell and produces fine striping).
    float around = (ang + u_rotation) / TAU;
    float u_tex = fract(around);                       // samples one glyph per cell
    float local = fract(around * u_repeat);            // 0..1 within current cell
    float v = clamp((r - (u_radius - u_width)) / (2.0 * u_width), 0.0, 1.0);

    float ink_raw = texture(u_glyphs, vec2(u_tex, v)).a;
    // Sharpen so characters read crisply instead of blurring into stripes.
    float ink = smoothstep(0.12, 0.45, ink_raw);
    // Wide dark gaps between cells so each rune stands alone as a character.
    float gap = smoothstep(0.06, 0.16, local) * smoothstep(0.94, 0.84, local);
    ink *= gap * band;

    // Two thin bright guide circles bounding the text band — the "arcane
    // diagram" structure from the reference.
    float line_in = smoothstep(0.006, 0.0, abs(r - (u_radius - u_width)));
    float line_out = smoothstep(0.006, 0.0, abs(r - (u_radius + u_width)));
    float lines = line_in + line_out;

    // Only a whisper of base glow — keep the dark space between characters dark.
    float base = band * 0.03;

    float pulse = 0.7 + 0.3 * sin(ang * 3.0 - u_time * 1.5);
    float total = (ink * 2.6 + lines * 0.9 + base) * u_intensity;
    total *= (0.9 + 0.3 * pulse) * (1.0 + 0.6 * u_audio);

    vec3 col = u_color * total;
    f_color = vec4(col, clamp(total, 0.0, 1.0));
}

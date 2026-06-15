#version 330

// Core glow: the molten white-gold heart of the orb. Smooth radial falloff,
// breathing pulse when idle, audio-reactive brightness + scale, and brief
// micro-flashes for the THINKING state.

in vec2 v_uv;
out vec4 f_color;

uniform float u_time;
uniform float u_aspect;
uniform float u_audio;
uniform float u_radius;
uniform float u_breath;        // 0..1 breathing phase output (precomputed)
uniform float u_glow;          // state glow multiplier
uniform float u_flash;         // 0..1 micro-flash intensity
uniform vec3  u_color_hot;
uniform vec3  u_color_warm;

#pragma include noise

void main() {
    vec2 p = (v_uv * 2.0 - 1.0);
    p.x *= u_aspect;
    float r = length(p);

    // Audio + breathing both modulate the effective radius.
    float scale = u_radius * (1.0 + 0.06 * u_breath + 0.35 * u_audio);

    float t = r / max(scale, 1e-4);

    // Smooth radial falloff: bright plateau core, exponential-ish tail.
    float falloff = exp(-t * t * 2.3);
    float halo = smoothstep(2.4, 0.0, t) * 0.35;

    // Internal turbulent texture so the core looks like contained plasma.
    float turb = fbm(p * 6.0 + vec2(0.0, u_time * 0.4));
    turb = 0.7 + 0.3 * turb;

    float bright = (falloff * turb * 1.5 + halo) * u_glow * (1.0 + u_audio * 1.4);
    bright += u_flash * falloff * 1.5;     // micro-flash spike

    // Colour ramp from warm amber (outer) to hot white-gold (centre). The very
    // centre is pushed toward pure white so the heart reads as incandescent.
    vec3 col = mix(u_color_warm, u_color_hot, clamp(falloff * 1.2, 0.0, 1.0));
    col = mix(col, vec3(1.0), smoothstep(0.55, 1.0, falloff) * 0.8);
    col *= bright;

    f_color = vec4(col, clamp(bright, 0.0, 1.0));
}

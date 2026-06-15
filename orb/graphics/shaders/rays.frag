#version 330

// Light rays: thin radial beams emanating from the core, like the reference's
// god-rays. Length and brightness pulse with audio; subtle flicker in THINKING.

in vec2 v_uv;
out vec4 f_color;

uniform float u_time;
uniform float u_aspect;
uniform float u_audio;
uniform float u_ray_count;
uniform float u_line_count;   // crisp full-width filaments
uniform float u_intensity;
uniform float u_length;       // 0..1 reach of the rays
uniform float u_flicker;      // 0..1 flicker amount
uniform vec3  u_color;

#pragma include noise

void main() {
    vec2 p = (v_uv * 2.0 - 1.0);
    p.x *= u_aspect;
    float r = length(p);
    float ang = atan(p.y, p.x);

    // Angular ray pattern: alternating bright/dark wedges, with per-ray noise
    // so they vary in brightness and don't look mechanical.
    float a = (ang / TAU + 0.5) * u_ray_count;
    float idx = floor(a);
    float frac = fract(a);

    float rayShape = pow(abs(sin(frac * PI)), 8.0);   // sharp central spine
    float perRay = 0.4 + 0.6 * hash11(idx + 3.0);
    float flicker = 1.0 - u_flicker * (0.5 + 0.5 * sin(u_time * 9.0 + idx * 1.7)) * hash11(idx);

    // Radial falloff: rays start near the core and fade out at u_length.
    float reach = u_length * (1.0 + 0.6 * u_audio);
    float radial = smoothstep(reach, 0.06, r) * smoothstep(0.02, 0.12, r);

    float beam = rayShape * perRay * radial * flicker;
    float intensity = beam * u_intensity * (1.0 + u_audio * 2.0);

    // --- Crisp full-width filaments: thin, near-straight white-gold lines that
    // cross the entire orb, like the reference's light lines. ---
    float la = (ang / TAU + 0.5) * u_line_count;
    float lidx = floor(la);
    float lfrac = fract(la);
    float lineShape = pow(abs(sin(lfrac * PI)), 90.0);   // very thin
    float exists = step(0.45, hash11(lidx + 0.5));       // only ~half present
    float lineReach = smoothstep(0.97, 0.1, r) * smoothstep(0.04, 0.14, r);
    float lineFlicker = 1.0 - u_flicker * 0.5 * (0.5 + 0.5 * sin(u_time * 7.0 + lidx));
    float filament = lineShape * exists * lineReach * lineFlicker;
    // Independent base so the crisp lines stay visible even when god-rays are dim.
    filament *= (0.4 + u_intensity * 0.5 + u_audio * 1.2);

    vec3 col = u_color * intensity;
    col += vec3(1.0, 0.96, 0.85) * filament * 0.9;       // white-gold filaments

    float outA = clamp(intensity + filament, 0.0, 1.0);
    f_color = vec4(col, outA);
}

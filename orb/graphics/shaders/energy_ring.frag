#version 330

// Energy ring: a luminous annulus whose radius is perturbed by periodic noise.
// The distortion scales with audio so the ring writhes and never reads as a
// perfect circle while speaking. Additive glow, time-animated.

in vec2 v_uv;
out vec4 f_color;

uniform float u_time;
uniform float u_aspect;
uniform float u_audio;
uniform float u_radius;
uniform float u_sides;          // polygon side count (heptagon = 7)
uniform float u_turbulence;     // base turbulence (state-driven)
uniform float u_ripple;         // travelling ripple strength (thinking/speaking)
uniform vec3  u_color;
uniform float u_intensity;

#pragma include noise

// Regular N-gon radius as a function of angle: 1.0 at vertices, cos(pi/N) at
// edge centres. Gives the ring crisp polygonal edges like the reference.
float polygon_factor(float ang, float sides) {
    float seg = TAU / sides;
    float a = mod(ang, seg) - 0.5 * seg;
    return cos(0.5 * seg) / cos(a);
}

void main() {
    vec2 p = (v_uv * 2.0 - 1.0);
    p.x *= u_aspect;
    float r = length(p);
    float ang = atan(p.y, p.x);

    // Heptagonal base shape, slowly rotating.
    float poly = polygon_factor(ang + u_time * 0.08, u_sides);
    float base = u_radius * mix(1.0, poly, 0.55);

    // Audio-driven turbulent displacement of the ring edge.
    float distort = u_turbulence + u_audio * 0.22;
    float n1 = ring_noise(ang * 3.0, u_time * 0.6, 2.0) - 0.5;
    float n2 = ring_noise(ang * 7.0, u_time * 1.1, 4.0) - 0.5;
    float edge = base + (n1 * 0.6 + n2 * 0.4) * distort;

    // Ripples that race around the ring (energy pulses).
    float ripple = sin(ang * 9.0 - u_time * 4.0) * 0.012 * u_ripple;
    edge += ripple;

    // Thin, bright filament with a soft outer bloom.
    float thickness = 0.012 + 0.02 * u_audio;
    float dist = abs(r - edge);
    float core = smoothstep(thickness, 0.0, dist);
    float glow = smoothstep(thickness * 6.0, 0.0, dist) * 0.5;

    float intensity = (core + glow) * u_intensity * (1.0 + u_audio * 1.2);

    // Hot inner edge → warmer outer edge.
    vec3 col = mix(u_color, vec3(1.0, 0.95, 0.8), core * 0.6) * intensity;

    f_color = vec4(col, clamp(intensity, 0.0, 1.0));
}

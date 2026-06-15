#version 330

// Background glow: a large, slowly swirling halo of teal-green and warm amber
// that gives the orb depth and a sense of contained atmosphere.

in vec2 v_uv;
out vec4 f_color;

uniform float u_time;
uniform float u_aspect;
uniform float u_audio;
uniform float u_radius;
uniform vec3 u_color_a;   // cool halo
uniform vec3 u_color_b;   // warm shadow
uniform vec3 u_nebula_a;  // magenta wisp
uniform vec3 u_nebula_b;  // cyan-blue wisp

#pragma include noise

void main() {
    vec2 p = (v_uv * 2.0 - 1.0);
    p.x *= u_aspect;
    float r = length(p);
    float ang = atan(p.y, p.x);

    // Slow nebulous swirl.
    float swirl = fbm(p * 1.6 + vec2(cos(u_time * 0.05), sin(u_time * 0.04)) * 1.2);
    swirl += 0.4 * fbm(p * 3.1 - u_time * 0.03);

    float halo = smoothstep(u_radius, 0.0, r);
    halo = pow(halo, 1.6);
    // Strongly dim the cool halo in the central region so the warm gold core
    // dominates there instead of reading as green.
    halo *= mix(1.0, 0.12, smoothstep(0.42, 0.0, r));

    // Petal-like angular variation reminiscent of the reference's coloured wisps.
    float petals = 0.5 + 0.5 * sin(ang * 6.0 + u_time * 0.2 + swirl * 3.0);

    vec3 col = mix(u_color_b, u_color_a, clamp(swirl * 1.3, 0.0, 1.0));
    col *= halo * (0.55 + 0.45 * petals);
    col += u_color_a * halo * 0.25 * (0.8 + 0.2 * u_audio);

    // --- Coloured nebula wisps in the outer field (domain-warped fbm). ---
    vec2 q = p * 2.3;
    vec2 warp = vec2(fbm(q + u_time * 0.04), fbm(q.yx - u_time * 0.05));
    float neb = fbm(q + warp * 2.0 + vec2(0.0, u_time * 0.02));
    neb = pow(clamp(neb, 0.0, 1.0), 1.8);
    // Concentrate wisps in a mid/outer annulus so the centre stays clean.
    float band = smoothstep(0.15, 0.5, r) * smoothstep(u_radius, 0.45, r);
    float tint = fbm(q * 0.7 + 5.0);
    vec3 nebcol = mix(u_nebula_b, u_nebula_a, smoothstep(0.35, 0.65, tint));
    col += nebcol * neb * band * 0.9 * (0.85 + 0.3 * u_audio);

    float alpha = max(halo * 0.9, neb * band * 0.6);
    f_color = vec4(col, alpha);
}

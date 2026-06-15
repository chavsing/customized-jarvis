#version 330

// Soft additive point-sprite particles. Positions live in aspect-corrected orb
// space (matching the fragment-shader layers); we map them back to NDC here.

in vec2  in_pos;     // orb-space position (x already aspect-scaled)
in float in_life;    // 0..1 remaining lifetime fraction
in float in_size;    // pixel size
in float in_seed;    // per-particle random

out float v_life;
out float v_seed;

uniform float u_aspect;
uniform float u_dpr;     // device pixel ratio (for crisp sprites on HiDPI)

void main() {
    vec2 ndc = vec2(in_pos.x / u_aspect, in_pos.y);
    gl_Position = vec4(ndc, 0.0, 1.0);
    // Particles shrink slightly as they age.
    gl_PointSize = in_size * u_dpr * (0.5 + 0.5 * in_life);
    v_life = in_life;
    v_seed = in_seed;
}

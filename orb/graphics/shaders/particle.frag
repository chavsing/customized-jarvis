#version 330

in float v_life;
in float v_seed;
out vec4 f_color;

uniform vec3 u_color;
uniform float u_intensity;

void main() {
    // Soft round sprite from the point-coord.
    vec2 c = gl_PointCoord * 2.0 - 1.0;
    float d = dot(c, c);
    if (d > 1.0) discard;

    float soft = exp(-d * 3.5);

    // Fade in quickly, fade out over life. Slight colour temperature variation.
    float fade = smoothstep(0.0, 0.15, v_life) * smoothstep(0.0, 0.6, v_life);
    vec3 col = mix(u_color, vec3(1.0, 0.95, 0.85), 0.4 * v_seed);

    float a = soft * fade * u_intensity;
    f_color = vec4(col * a, a);
}

#version 330

// Separable 9-tap Gaussian blur. Direction is supplied via u_direction so the
// same program does both the horizontal and vertical passes.
in vec2 v_uv;
out vec4 f_color;

uniform sampler2D u_tex;
uniform vec2 u_direction;   // (texel, 0) or (0, texel)

void main() {
    float w[5] = float[](0.227027, 0.1945946, 0.1216216, 0.054054, 0.016216);
    vec3 result = texture(u_tex, v_uv).rgb * w[0];
    for (int i = 1; i < 5; i++) {
        vec2 off = u_direction * float(i);
        result += texture(u_tex, v_uv + off).rgb * w[i];
        result += texture(u_tex, v_uv - off).rgb * w[i];
    }
    f_color = vec4(result, 1.0);
}

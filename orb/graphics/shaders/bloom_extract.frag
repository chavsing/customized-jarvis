#version 330

// Bright-pass: keep only luminance above a threshold for the bloom blur.
in vec2 v_uv;
out vec4 f_color;

uniform sampler2D u_scene;
uniform float u_threshold;

void main() {
    vec3 c = texture(u_scene, v_uv).rgb;
    float lum = dot(c, vec3(0.2126, 0.7152, 0.0722));
    float k = max(0.0, lum - u_threshold);
    float scale = (lum > 0.0) ? (k / lum) : 0.0;
    f_color = vec4(c * scale, 1.0);
}

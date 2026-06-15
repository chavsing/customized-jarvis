#version 330

// A single triangle / quad covering the screen. Position arrives in NDC and we
// forward a 0..1 uv that fragment shaders re-centre into aspect-correct space.
in vec2 in_pos;
out vec2 v_uv;

void main() {
    v_uv = in_pos * 0.5 + 0.5;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}

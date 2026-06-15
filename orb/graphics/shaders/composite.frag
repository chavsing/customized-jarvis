#version 330

// Final composite to the screen: combine the scene with the blurred bloom,
// apply a tasteful audio-reactive chromatic aberration, gentle tone-mapping,
// and a soft vignette. Outputs straight alpha so the orb floats on the desktop.

in vec2 v_uv;
out vec4 f_color;

uniform sampler2D u_scene;
uniform sampler2D u_bloom;
uniform float u_bloom_intensity;
uniform float u_chromatic;       // RGB separation amount (uv units)
uniform float u_audio;

vec4 sample_scene(vec2 uv) {
    return texture(u_scene, uv);
}

void main() {
    vec2 dir = v_uv - 0.5;
    float dist = length(dir);
    vec2 offset = normalize(dir + 1e-6) * u_chromatic * dist;

    // Chromatic aberration: sample channels at slightly different radii.
    float sr = sample_scene(v_uv + offset).r;
    vec4  sg = sample_scene(v_uv);
    float sb = sample_scene(v_uv - offset).b;
    vec3 scene = vec3(sr, sg.g, sb);
    float alpha = sg.a;

    vec3 bloom = texture(u_bloom, v_uv).rgb;
    // Bloom carries its own colour; also lift alpha so glow halos are visible
    // against the transparent desktop.
    vec3 color = scene + bloom * u_bloom_intensity;
    alpha = max(alpha, dot(bloom, vec3(0.333)) * u_bloom_intensity);

    // Tone-map on LUMINANCE (not per-channel) so highlights roll off without
    // washing the colour out — then push saturation for that vivid arcane look.
    float lum = dot(color, vec3(0.2126, 0.7152, 0.0722));
    float tlum = lum / (lum + 0.75);
    color *= tlum / max(lum, 1e-4);

    float grey = dot(color, vec3(0.299, 0.587, 0.114));
    color = mix(vec3(grey), color, 1.3);           // saturation boost
    color = max(color, vec3(0.0));

    // Soft vignette pulls focus to the orb.
    float vig = smoothstep(1.05, 0.35, dist);
    color *= mix(0.9, 1.0, vig);

    f_color = vec4(color, clamp(alpha, 0.0, 1.0));
}

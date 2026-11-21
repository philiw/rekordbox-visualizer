#version 330
// Transition between the outgoing scene (uA) and the incoming one (uB).
uniform sampler2D uA, uB;
uniform float uMix;      // 0 = A, 1 = B
uniform int   uStyle;    // 0 crossfade, 1 iris, 2 wipe, 3 dissolve
uniform vec2  uRes;
in vec2 vUv;
out vec4 fragColor;

float hash21(vec2 p) { vec3 p3 = fract(vec3(p.xyx) * 0.1031); p3 += dot(p3, p3.yzx + 33.33); return fract((p3.x + p3.y) * p3.z); }

void main() {
    vec3 a = texture(uA, vUv).rgb;
    vec3 b = texture(uB, vUv).rgb;
    float m = uMix;
    float k;
    vec2 p = (vUv - 0.5) * vec2(uRes.x / uRes.y, 1.0);
    if (uStyle == 1) {            // iris from the centre
        k = smoothstep(m * 1.3 - 0.05, m * 1.3 + 0.05, length(p) * 1.1);
        k = 1.0 - k;
    } else if (uStyle == 2) {     // diagonal wipe with glowing edge
        float d = (vUv.x + vUv.y) * 0.5;
        k = smoothstep(m * 1.2 - 0.1, m * 1.2, d) ; k = 1.0 - k;
    } else if (uStyle == 3) {     // blocky dissolve
        float n = hash21(floor(vUv * uRes / 24.0));
        k = step(n, m);
    } else {
        k = smoothstep(0.0, 1.0, m);
    }
    vec3 c = mix(a, b, k);
    if (uStyle == 2) c += vec3(1.0) * smoothstep(0.03, 0.0, abs((vUv.x + vUv.y) * 0.5 - m * 1.2 + 0.05)) * 0.5 * (1.0 - m);
    fragColor = vec4(c, 1.0);
}

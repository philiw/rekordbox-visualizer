#version 330
// Final pass: bloom, chromatic aberration on kicks, flashes, tone mapping, vignette, HUD.
uniform sampler2D uTex;
uniform sampler2D uHud;
uniform float uHudOn;
uniform vec2  uHudSize;   // HUD size in screen pixels
uniform vec2  uRes;       // screen size in pixels
uniform float uKick, uEnergy, uFlash, uTime, uBloom, uExposure;
uniform float uPunch;     // kick punch strength from vibes.toml (0 = off)
uniform vec3  uFlashCol;
in vec2 vUv;
out vec4 fragColor;

float hash21(vec2 p) { vec3 p3 = fract(vec3(p.xyx) * 0.1031); p3 += dot(p3, p3.yzx + 33.33); return fract((p3.x + p3.y) * p3.z); }

void main() {
    // kick punch: a quick zoom into the picture plus a tiny shake, for every scene
    float k = uKick * uPunch;
    vec2 uv = 0.5 + (vUv - 0.5) * (1.0 - 0.04 * k);
    uv += (vec2(hash21(vec2(uTime * 61.0, 1.7)), hash21(vec2(uTime * 47.0, 3.1))) - 0.5) * 0.008 * k * k;
    vec2 d = uv - 0.5;
    float ca = 0.006 * uKick * (0.4 + uEnergy);
    vec3 c;
    c.r = texture(uTex, uv + d * ca * 2.0).r;
    c.g = texture(uTex, uv).g;
    c.b = texture(uTex, uv - d * ca * 2.0).b;

    vec3 bloom = textureLod(uTex, uv, 2.0).rgb * 0.35
               + textureLod(uTex, uv, 4.0).rgb * 0.35
               + textureLod(uTex, uv, 6.0).rgb * 0.30;
    c += bloom * uBloom;
    c += uFlashCol * uFlash;

    c = vec3(1.0) - exp(-c * uExposure);            // soft tone mapping
    c *= 1.0 - 0.55 * dot(d, d);                     // vignette
    c += (hash21(uv * uRes + fract(uTime) * 100.0) - 0.5) * 0.025;  // grain (kills banding)

    if (uHudOn > 0.5) {
        vec2 px = vec2(vUv.x, 1.0 - vUv.y) * uRes - vec2(18.0);   // HUD doesn't shake
        vec2 huv = px / uHudSize;
        if (huv.x >= 0.0 && huv.y >= 0.0 && huv.x <= 1.0 && huv.y <= 1.0) {
            vec4 h = texture(uHud, huv);
            c = mix(c, h.rgb, h.a);
        }
    }
    fragColor = vec4(clamp(c, 0.0, 1.0), 1.0);
}

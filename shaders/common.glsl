#version 330
// ---- shared uniforms (filled every frame by main.py) ----------------------
uniform vec2  uRes;       // render size in pixels
uniform float uTime;      // seconds since start
uniform float uBeat;      // continuous beat counter, tempo-locked (1.0 = one beat)
uniform float uBpm;
uniform float uBar;       // beat inside the bar, 0..4
uniform float uPhrase;    // 0..1 progress through the 32-beat phrase
uniform float uKick;      // 1 on a kick, decays fast
uniform float uSub, uBass, uLowMid, uMid, uHigh, uLevel;   // 0..1 smoothed bands
uniform float uEnergy;    // 0 (breakdown) .. 1 (full groove)
uniform float uBuild;     // buildup tension 0..1
uniform float uDrop;      // 1 right at a drop, decays over a few bars
uniform float uBright;    // spectral brightness 0..1
uniform float uSeed;      // random per scene activation -> variations
uniform vec3  uCol1, uCol2, uCol3;   // palette derived from the musical key
uniform sampler2D uSpec;  // 128 log-spaced spectrum bins (x = 0..1)
uniform sampler2D uWave;  // 256 waveform samples (-1..1)
uniform sampler2D uPrev;  // previous composited frame (for feedback effects)

in vec2 vUv;
out vec4 fragColor;

#define PI 3.14159265
#define TAU 6.2831853

float spec(float x) { return texture(uSpec, vec2(clamp(x, 0.0, 1.0), 0.5)).r; }
float wave(float x) { return texture(uWave, vec2(fract(x), 0.5)).r; }

float hash11(float p) { p = fract(p * 0.1031); p *= p + 33.33; p *= p + p; return fract(p); }
float hash21(vec2 p) { vec3 p3 = fract(vec3(p.xyx) * 0.1031); p3 += dot(p3, p3.yzx + 33.33); return fract((p3.x + p3.y) * p3.z); }
vec2  hash22(vec2 p) { vec3 p3 = fract(vec3(p.xyx) * vec3(0.1031, 0.1030, 0.0973)); p3 += dot(p3, p3.yzx + 33.33); return fract((p3.xx + p3.yz) * p3.zy); }

float noise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash21(i), hash21(i + vec2(1, 0)), u.x),
               mix(hash21(i + vec2(0, 1)), hash21(i + vec2(1, 1)), u.x), u.y);
}
float fbm(vec2 p) {
    float v = 0.0, a = 0.5;
    mat2 m = mat2(1.6, 1.2, -1.2, 1.6);
    for (int i = 0; i < 5; i++) { v += a * noise(p); p = m * p; a *= 0.5; }
    return v;
}
mat2 rot(float a) { float c = cos(a), s = sin(a); return mat2(c, -s, s, c); }

// palette: t in 0..1 walks col1 -> col2 -> col3 -> col1
vec3 pal(float t) {
    t = fract(t) * 3.0;
    if (t < 1.0) return mix(uCol1, uCol2, smoothstep(0.0, 1.0, t));
    if (t < 2.0) return mix(uCol2, uCol3, smoothstep(1.0, 2.0, t));
    return mix(uCol3, uCol1, smoothstep(2.0, 3.0, t));
}

// centred, aspect-corrected coordinates (y in -1..1)
vec2 centered(vec2 uv) { return (uv * 2.0 - 1.0) * vec2(uRes.x / uRes.y, 1.0); }

// beat pulse with sharp attack, tempo-locked (0..1)
float beatPulse(float sharp) { return exp(-fract(uBeat) * sharp); }

vec3 scene(vec2 uv, vec2 p);

void main() {
    vec3 c = scene(vUv, centered(vUv));
    fragColor = vec4(max(c, 0.0), 1.0);
}
// ---------------------------------------------------------------------------

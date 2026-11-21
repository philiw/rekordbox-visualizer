// @name: Kaleidoscope
// @moods: groove calm peak
vec3 scene(vec2 uv, vec2 p) {
    float n = floor(5.0 + hash11(uSeed) * 6.0) + floor(uEnergy * 2.0) * 2.0;
    p *= 1.0 - 0.12 * uKick;
    float a = atan(p.y, p.x), r = length(p);
    float seg = TAU / n;
    a = abs(mod(a + uBeat * 0.02 * TAU, seg) - seg * 0.5);
    vec2 q = vec2(cos(a), sin(a)) * r;
    vec3 col = vec3(0.0);
    float t = uBeat * 0.125;
    for (int i = 0; i < 6; i++) {
        q = abs(q) / dot(q, q) - (0.75 + 0.15 * sin(t + float(i)) + 0.1 * uBass);
        q *= rot(t * 0.3 + uSeed);
        float d = length(q);
        float glow = 0.012 / (abs(d - 0.5 - 0.3 * spec(float(i) / 6.0)) + 0.012);
        col += pal(float(i) * 0.17 + r * 0.5 + t * 0.2) * glow * (0.25 + 0.2 * uLevel);
    }
    col *= 0.6 + 1.2 * uKick + 0.5 * uDrop;
    col *= smoothstep(1.8, 0.2, r);
    return col;
}

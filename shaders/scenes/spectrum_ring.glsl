// @name: Spectrum Bloom
// @moods: groove calm
vec3 scene(vec2 uv, vec2 p) {
    // feedback: zoom + rotate the previous frame for trails
    vec2 fb = (uv - 0.5) * (0.985 - 0.02 * uKick);
    fb *= rot(0.004 * sin(uBeat * 0.25 * PI) + 0.003);
    vec3 prev = texture(uPrev, fb + 0.5).rgb * (0.80 + 0.08 * (1.0 - uEnergy));

    float a = atan(p.y, p.x);
    float r = length(p);
    float sym = abs(a / PI);                       // mirrored around the circle
    float s = spec(pow(sym, 1.3) * 0.85);
    float base = 0.38 + 0.08 * uBass + 0.05 * uKick;
    float barLen = s * (0.35 + 0.3 * uLevel);
    float inBar = step(base, r) * step(r, base + barLen);
    float stripes = smoothstep(0.35, 0.5, abs(fract(sym * 64.0) - 0.5));
    vec3 col = pal(sym + uBeat * 0.03) * inBar * stripes * 1.3;

    // waveform ring, mirrored top/bottom like the bars so the ends of the
    // waveform never meet (wrapping it once around the circle left a seam)
    float w = wave(sym * 0.5 + 0.25) * 0.06 * (0.5 + uLevel);
    float ring = smoothstep(0.012, 0.0, abs(r - (base - 0.06 + w)));
    col += uCol3 * ring * 1.5;
    // centre pulse
    col += uCol2 * smoothstep(base - 0.1, 0.0, r) * (0.15 + 0.9 * uKick) * 0.6;
    return max(col, prev);
}

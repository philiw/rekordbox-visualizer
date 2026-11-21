// @name: Liquid Plasma
// @moods: calm build
vec3 scene(vec2 uv, vec2 p) {
    float t = uBeat * 0.06 + uSeed * 10.0;
    p *= 1.2 + 0.6 * hash11(uSeed);
    vec2 q = vec2(fbm(p + t), fbm(p - t + 3.1));
    vec2 r = vec2(fbm(p + 3.0 * q + vec2(1.7, 9.2) + t * 1.3), fbm(p + 3.0 * q + vec2(8.3, 2.8) - t));
    float f = fbm(p + 3.5 * r);
    vec3 col = mix(uCol1 * 0.25, uCol2, smoothstep(0.2, 0.9, f));
    col = mix(col, uCol3, smoothstep(0.5, 1.2, length(r)) * 0.7);
    col *= 0.15 + 0.7 * f * f * f + 0.25 * uMid;
    // veins of light that follow the hi-hats and build-ups
    float vein = smoothstep(0.02, 0.0, abs(f - 0.55)) * (0.4 + uHigh * 1.5 + uBuild * 2.0);
    col += pal(f + uBeat * 0.01) * vein;
    col *= 1.0 + 0.5 * uKick;
    return col;
}

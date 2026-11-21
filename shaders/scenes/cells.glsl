// @name: Pulse Cells
// @moods: groove peak
vec3 scene(vec2 uv, vec2 p) {
    float scale = 3.0 + floor(hash11(uSeed) * 4.0);
    p *= scale;
    p += vec2(uBeat * 0.08, sin(uBeat * 0.1) * 0.5);
    vec2 id = floor(p), f = fract(p);
    float d1 = 9.0, d2 = 9.0;
    vec2 cid = vec2(0.0);
    for (int y = -1; y <= 1; y++) {
        for (int x = -1; x <= 1; x++) {
            vec2 g = vec2(float(x), float(y));
            vec2 o = hash22(id + g);
            o = 0.5 + 0.4 * sin(uBeat * 0.25 + TAU * o);
            float d = length(g + o - f);
            if (d < d1) { d2 = d1; d1 = d; cid = id + g; }
            else if (d < d2) { d2 = d; }
        }
    }
    float edge = smoothstep(0.06 + 0.06 * uBass, 0.0, d2 - d1);
    float h = hash21(cid);
    // every beat a different random set of cells lights up
    float lit = step(0.75 - 0.3 * uEnergy, hash21(cid + floor(uBeat)));
    float flash = lit * beatPulse(4.0);
    vec3 col = pal(h + uBeat * 0.02) * flash * (0.5 + uKick);
    col += pal(h + 0.4) * edge * (0.5 + 1.2 * uHigh);
    col += uCol1 * 0.08 * (1.0 - d1);
    return col;
}

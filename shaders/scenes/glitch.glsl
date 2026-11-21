// @name: Glitch Slice
// @moods: peak groove
// Bold squares that snap 45 degrees per beat, torn apart into RGB-split slices on
// every 8th note, with block-noise flashes. Hardest right after each hit.

float glitchShape(vec2 p) {
    float b = floor(uBeat);
    float ang = (b + smoothstep(0.0, 0.12, fract(uBeat))) * PI * 0.25;   // snap per beat
    vec2 q = rot(ang) * p;
    float s = 0.0;
    for (int i = 0; i < 3; i++) {
        float size = 0.22 + 0.24 * float(i) + 0.06 * uKick;
        vec2 d = abs(q) - vec2(size);
        float box = abs(max(d.x, d.y));
        s += smoothstep(0.03, 0.0, box - 0.014);
    }
    // a bar through the middle that flips direction every beat
    vec2 bq = mod(b, 2.0) < 0.5 ? p : p.yx;
    s += smoothstep(0.02, 0.0, abs(bq.y) - 0.01) * step(abs(bq.x), 0.9) * 0.7;
    return min(s, 1.2);
}

vec3 scene(vec2 uv, vec2 p) {
    float t8 = floor(uBeat * 2.0);
    float env = exp(-fract(uBeat * 2.0) * 6.0) * (0.35 + uKick + 0.5 * uHigh);
    float rows = 6.0 + floor(hash11(t8 + uSeed) * 26.0);
    float row = floor(uv.y * rows);
    float tear = step(0.55, hash21(vec2(row, t8 + 7.0)));
    float shift = (hash21(vec2(row, t8)) - 0.5) * 0.5 * env * tear;
    vec2 q = p + vec2(shift, 0.0);

    float split = 0.025 * env + 0.012 * uKick;
    float r = glitchShape(q + vec2(split, 0.0));
    float g = glitchShape(q);
    float bl = glitchShape(q - vec2(split, 0.0));
    vec3 col = vec3(r, g, bl) * 0.55 + g * uCol1 * 0.9;

    // block noise flashes on the hits
    vec2 blk = floor(uv * vec2(16.0, 9.0));
    col += pal(hash21(blk)) * step(0.975 - 0.06 * env, hash21(blk + t8)) * env * 1.2;
    // scanlines
    col *= 0.82 + 0.18 * sin(uv.y * uRes.y * 1.6);
    return col;
}

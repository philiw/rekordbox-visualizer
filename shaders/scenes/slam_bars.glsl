// @name: Slam Bars
// @moods: peak groove
// Full-screen bars that slam in on every beat. Each beat picks a new pattern
// (vertical, horizontal, diagonal, mirrored, rings); beats 1 and 3 hit hardest.
vec3 scene(vec2 uv, vec2 p) {
    float b = floor(uBeat);
    float t = fract(uBeat);
    float h = hash11(b * 1.37 + uSeed);
    int pattern = int(h * 5.0);
    float n = 3.0 + floor(hash11(b * 2.11 + uSeed * 3.0) * 4.0) * 2.0 + floor(uEnergy * 4.0);

    float coord;
    if (pattern == 0) coord = uv.x;
    else if (pattern == 1) coord = uv.y;
    else if (pattern == 2) coord = (uv.x + uv.y) * 0.5;
    else if (pattern == 3) coord = abs(uv.x - 0.5) * 2.0;     // mirrored from the centre
    else coord = length(p) * 0.6 - t * 0.25;                  // rings rushing outwards

    float id = floor(coord * n);
    float lit = step(0.6, hash21(vec2(id, b)));                // ~40% of the bars fire each beat
    float f = fract(coord * n);
    float bar = smoothstep(0.0, 0.04, f) * smoothstep(1.0, 0.9, f);

    // hard attack on the beat, gone by mid-beat; a smaller hit on the off-beat hats
    float decay = mix(9.0, 5.0, uStrobe);
    float env = exp(-t * decay) * (0.6 + 0.8 * uKick) + 0.35 * exp(-fract(uBeat + 0.5) * 10.0) * uHigh;
    bool strong = mod(b, 2.0) < 0.5;                           // beats 1 and 3
    vec3 c = strong ? mix(pal(h), vec3(1.0), 0.35 * uStrobe) : pal(h + 0.33);

    vec3 col = c * bar * lit * env * 1.8;
    float edge = 1.0 - smoothstep(0.0, 0.03, min(f, 1.0 - f));
    col += pal(h) * edge * 0.05;                               // faint grid lines, black between
    return col;
}

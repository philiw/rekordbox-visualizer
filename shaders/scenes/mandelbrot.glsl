// @name: Mandelbrot Zoom
// @moods: calm
// A slow, continuous dive into the Mandelbrot set for breakdowns and quiet parts:
// no beat jumps, the zoom glides at a steady, tempo-locked pace. Colour bands ripple
// gently with the beat, filaments shimmer with the hi-hats.
//
// GPU floats run out of precision around 10^4-10^5 zoom, so a dive can't go on forever.
// Instead dives overlap: the next one (into a new spot) starts while the current one is
// still zooming, and the two crossfade over OVERLAP beats - no jump, no black gap.

const float ZMIN = 60.0;             // dives start already close to the filaments: wider views
                                     // still show the set's black body or bulbs at the edge.
                                     // From 60x to 9000x no target shows any inside points.
const float ZMAX = 9000.0;
const float CYCLE = 128.0;           // a new dive starts every 32 bars (~55 s at 140 BPM)
const float OVERLAP = 16.0;          // crossfade length in beats (4 bars)

// Dive targets are Misiurewicz points: tips and spiral centres of the set's filaments.
// Unlike most edge points they have no black interior nearby at depth. Each was checked
// by simulating the whole dive (60x .. 9000x, rotated full screen): 0% inside points.
vec2 target(float i) {
    int k = int(mod(i, 8.0));
    vec2 t;
    if (k == 0) t = vec2(-0.204600218, 1.120160711);
    else if (k == 1) t = vec2(-0.017187977, 1.037652344);
    else if (k == 2) t = vec2(-1.768664733, 0.057774377);
    else if (k == 3) t = vec2(-0.249993740, 0.888062106);
    else if (k == 4) t = vec2(0.041338435, 0.815904374);
    else if (k == 5) t = vec2(-1.296355138, 0.441851606);
    else if (k == 6) t = vec2(0.343906996, 0.700620020);
    else t = vec2(-0.101096364, 0.956286511);
    // the set is mirror-symmetric: use the lower half for every other dive for variety
    if (hash11(i * 7.31 + 0.5) > 0.5) t.y = -t.y;
    return t;
}

// One dive. u = 0..1 progress through it (zoom ZMIN -> ZMAX).
vec3 dive(vec2 p, float id, float u, float beat) {
    float zoom = ZMIN * exp(clamp(u, 0.0, 1.0) * log(ZMAX / ZMIN));
    vec2 tgt = target(id + floor(uSeed));
    vec2 center = tgt;   // aim at the target from the start, never fly across the black body
    p *= rot(u * 2.0 + id * 1.7 + 0.1 * sin(beat * PI / 32.0));   // slow drift
    vec2 c = center + p * (1.4 / zoom);

    // deeper = slower escape near the edge: too few steps would paint those points black
    int maxIter = int(clamp(150.0 + 110.0 * log(zoom) / log(10.0), 150.0, 600.0));
    vec2 z = vec2(0.0);
    vec2 dz = vec2(0.0);
    float n = -1.0;
    for (int i = 0; i < 600; i++) {
        if (i >= maxIter) break;
        dz = 2.0 * vec2(z.x * dz.x - z.y * dz.y, z.x * dz.y + z.y * dz.x) + vec2(1.0, 0.0);
        z = vec2(z.x * z.x - z.y * z.y, 2.0 * z.x * z.y) + c;
        if (dot(z, z) > 256.0) { n = float(i); break; }
    }
    if (n < 0.0) {
        return uCol3 * 0.03;                                      // inside the set: dark
    }
    float mu = n + 1.0 - log2(log2(dot(z, z)) * 0.5);            // smooth iteration count
    float de = 0.5 * length(z) * log(length(z)) / max(length(dz), 1e-9);
    float px = 1.4 / zoom * 2.0 / uRes.y;
    float fil = exp(-de / px * 0.6);                              // crisp filaments
    float halo = exp(-de / px * 0.05);                            // soft glow around the set
    float haze = exp(-de / px * 0.006);                           // wide, faint glow further out

    // dark background, colour bands that drift outwards smoothly with the beat
    float band = pow(0.5 + 0.5 * cos(mu * 0.35 - beat * PI * 0.25), 4.0);
    vec3 col = pal(mu * 0.03 + beat * 0.01) * band * (0.18 + 0.4 * halo + 0.25 * haze) * (0.7 + 0.5 * uLevel);
    col += pal(mu * 0.03 + 0.7) * haze * 0.08;
    col += pal(mu * 0.03 + 0.4) * halo * (0.25 + 0.3 * uMid);
    col += mix(uCol2, vec3(1.0), 0.5) * fil * (0.55 + 0.6 * uHigh);
    return col;
}

vec3 scene(vec2 uv, vec2 p) {
    float beat = max(uGridBeat, 0.0);
    float span = CYCLE + OVERLAP;                 // each dive lasts a bit longer than the cycle
    float id = floor(beat / CYCLE);
    float since = beat - id * CYCLE;              // beats since the current dive started
    vec3 cur = dive(p, id, since / span, beat);
    if (since < OVERLAP && id > 0.0) {
        // the previous dive is still finishing its last OVERLAP beats: crossfade into the new one
        vec3 prev = dive(p, id - 1.0, (since + CYCLE) / span, beat);
        return mix(prev, cur, smoothstep(0.0, 1.0, since / OVERLAP));
    }
    return cur;
}

// @name: Retro Horizon
// @moods: groove peak
vec3 scene(vec2 uv, vec2 p) {
    vec3 col = vec3(0.0);
    float horizon = 0.05;
    // sky + striped sun
    vec2 sp = p - vec2(0.0, 0.38);
    float sunR = 0.42 + 0.04 * uKick;
    float sun = smoothstep(sunR, sunR - 0.01, length(sp));
    float bandsY = fract((p.y - horizon) * 14.0 - uBeat * 0.25);
    float cut = step(0.0, p.y - horizon) * step(mix(0.0, 0.55, smoothstep(0.35, 0.0, sp.y)), bandsY);
    col += mix(uCol2, uCol1, smoothstep(-0.4, 0.4, sp.y)) * sun * cut * 1.3;
    col += uCol1 * 0.12 / (abs(length(sp) - sunR) * 8.0 + 0.4) * step(horizon, p.y);
    // stars
    vec2 st = floor(p * 90.0);
    col += step(0.995, hash21(st)) * step(horizon, p.y) * (0.4 + 0.6 * uHigh);

    if (p.y < horizon) {
        // perspective floor grid, scrolls with the tempo
        float d = horizon - p.y;
        float z = 0.35 / d;
        float x = p.x * z;
        float zz = z + uBeat * (0.5 + uEnergy);
        // distance to the nearest grid line, anti-aliased with screen-space derivatives
        float lx = x * 1.5, lz = zz * 0.5;
        float dx = abs(fract(lx + 0.5) - 0.5) / max(fwidth(lx), 1e-4);
        float dz = abs(fract(lz + 0.5) - 0.5) / max(fwidth(lz), 1e-4);
        float gx = 1.0 - smoothstep(0.5, 1.8, dx);
        float gz = 1.0 - smoothstep(0.5, 1.8 + 2.0 * uKick, dz);
        float grid = max(gx, gz) * smoothstep(0.0, 0.02, d);
        float fade = exp(-z * 0.12);
        col += pal(0.66 + zz * 0.02) * grid * fade * (0.7 + 1.6 * uKick);
        col += uCol1 * 0.04 * fade * (0.3 + uBass);
    } else {
        // mountain silhouette made from the spectrum
        float m = spec(abs(p.x) * 0.45) * 0.28 + 0.02;
        float mount = step(p.y - horizon, m);
        col = mix(col, uCol3 * 0.08 + uCol1 * 0.15 * smoothstep(m - 0.02, m, p.y - horizon), mount);
    }
    col += uCol2 * 0.4 * smoothstep(0.03, 0.0, abs(p.y - horizon)) * (0.6 + uKick);
    return col;
}

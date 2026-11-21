// @name: Neon Tunnel
// @moods: groove peak build
vec3 scene(vec2 uv, vec2 p) {
    float sides = floor(4.0 + hash11(uSeed) * 5.0);          // 4..8 sided tunnel
    float dirSign = hash11(uSeed + 1.0) > 0.5 ? 1.0 : -1.0;
    p *= rot(uBeat * 0.0625 * TAU * dirSign);
    float a = atan(p.y, p.x);
    // polygonal radius
    float seg = TAU / sides;
    float r = length(p) * cos(seg * 0.5) / cos(mod(a, seg) - seg * 0.5);
    r = max(r, 1e-3);
    float speed = 0.5 + uEnergy * 0.8 + uBuild * 2.5;
    float z = 0.35 / r + uBeat * 0.5 * speed;
    float ang = a / TAU + 0.5;

    // rings: two per beat, fatter on kicks
    float ringId = floor(z * 2.0);
    float ringF = fract(z * 2.0);
    float ring = smoothstep(0.08, 0.0, abs(ringF - 0.5) - 0.02 - uKick * 0.06);
    // spectrum on the walls
    float s = spec(fract(ang * 2.0));
    float bars = smoothstep(0.0, 0.02, s * 0.4 - abs(fract(ang * sides * 4.0) - 0.5));
    float lines = smoothstep(0.015, 0.0, 0.5 - abs(fract(ang * sides) - 0.5));

    vec3 col = pal(ringId * 0.11 + uBeat * 0.02) * ring * (0.6 + 1.6 * uKick);
    col += pal(ang + 0.3) * bars * pow(fract(-z * 2.0), 3.0) * (0.2 + 0.6 * uMid);
    col += uCol3 * lines * 0.35;
    float fog = smoothstep(0.0, 0.7, r);
    col *= fog * (0.5 + 0.8 * uLevel);
    // bright core, flares up on drops and build-ups
    col += uCol2 * (0.03 / (r + 0.03)) * (0.3 + uDrop * 2.0 + uBuild);
    return col;
}

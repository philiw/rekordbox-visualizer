// @name: Hyperspace
// @moods: build calm peak
vec3 scene(vec2 uv, vec2 p) {
    vec3 col = vec3(0.0);
    float speed = 0.15 + uEnergy * 0.3 + uBuild * 1.8 + uKick * 0.4 + uDrop * 1.0;
    float t = uTime * 0.2 + uBeat * (0.06 + 0.25 * uBuild + 0.1 * uEnergy);
    vec2 dir = normalize(p + 1e-4);
    vec2 perp = vec2(-dir.y, dir.x);
    p *= rot(uBeat * 0.01);
    for (int L = 0; L < 4; L++) {
        float fl = float(L);
        float depth = fract(t * 0.25 + fl * 0.25);
        float scale = mix(20.0, 0.5, depth);
        float fade = smoothstep(0.0, 0.4, depth) * smoothstep(1.0, 0.85, depth);
        vec2 q = p * scale + fl * 17.0;
        vec2 id = floor(q);
        vec2 f = fract(q) - 0.5;
        vec2 h = hash22(id) - 0.5;
        float star = hash21(id + 7.0);
        if (star > 0.6) {
            vec2 d = f - h * 0.7;
            // streak along the radial direction, longer when it's fast
            float along = dot(d, dir), across = dot(d, perp);
            float len = 0.02 + speed * 0.12 * depth;
            float s = smoothstep(0.03, 0.0, abs(across)) * smoothstep(len, 0.0, abs(along));
            col += pal(star * 3.0 + fl * 0.2) * s * fade * 2.0;
        }
    }
    float r = length(p);
    col += uCol2 * 0.05 / (r + 0.08) * (0.4 + uBuild * 2.0 + uKick);
    col *= 0.7 + 0.6 * uLevel;
    return col;
}

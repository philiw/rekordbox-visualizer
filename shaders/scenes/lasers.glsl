// @name: Laser Show
// @moods: peak groove build
vec3 scene(vec2 uv, vec2 p) {
    vec3 col = vec3(0.0);
    int n = 6 + int(uEnergy * 8.0);
    float sweep = sin(uBeat * PI * 0.25 + uSeed * 6.0);
    float aspect = uRes.x / uRes.y;
    for (int side = 0; side < 2; side++) {
        float sd = side == 0 ? 1.0 : -1.0;
        vec2 origin = vec2(-1.0 * sd * aspect * 0.95, -1.05);
        for (int i = 0; i < 14; i++) {
            if (i >= n) break;
            float fi = float(i) / float(n - 1);
            float ang = mix(0.25, 1.3, fi) + sweep * 0.35 * sd;
            ang = side == 0 ? ang : PI - ang;
            vec2 dir = vec2(cos(ang), sin(ang));
            vec2 d = p - origin;
            float along = dot(d, dir);
            float dist = abs(dot(d, vec2(-dir.y, dir.x)));
            float on = step(0.0, along);
            // beams chop on/off in rhythm; the pattern changes every half beat
            float gate = step(0.35, hash21(vec2(float(i + side * 20), floor(uBeat * 2.0))));
            gate = mix(1.0, gate, uEnergy);
            float beam = 0.0025 / (dist + 0.0025) + 0.004 / (dist * 40.0 + 0.3);
            col += pal(fi * 0.5 + float(side) * 0.3 + uBeat * 0.03) * beam * on * gate
                   * (0.25 + 0.6 * uKick + 0.4 * uHigh);
        }
    }
    // haze
    col += uCol3 * 0.08 * fbm(p * 2.0 + uTime * 0.1) * (0.5 + uBass);
    return col;
}

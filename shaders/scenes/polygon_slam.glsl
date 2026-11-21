// @name: Polygon Slam
// @moods: peak groove
// Nested polygons that snap-rotate by one step per beat (with a little overshoot),
// slam towards the viewer on the kick and fill in on the first beat of each bar.
vec3 scene(vec2 uv, vec2 p) {
    float sides = 3.0 + floor(hash11(uSeed) * 4.0);              // triangle .. hexagon
    float b = floor(uBeat);
    float t = fract(uBeat);
    float snap = 1.0 - exp(-t * 14.0) * cos(t * 30.0);         // fast snap with overshoot
    float ang = (b + snap) * TAU / sides * 0.5;
    p *= 1.0 - 0.2 * uKick;                                      // punch towards the viewer
    vec2 q = rot(ang) * p;
    float a = atan(q.y, q.x);
    float r = length(q);
    float seg = TAU / sides;
    float d = r * cos(mod(a, seg) - seg * 0.5);                  // distance in polygon units

    vec3 col = vec3(0.0);
    for (int i = 0; i < 5; i++) {
        float fi = float(i);
        float size = 0.16 + fi * 0.21 + 0.03 * sin(uBeat * PI + fi);
        float w = 0.016 + 0.035 * uKick * (i == 0 ? 1.0 : 0.4);
        float line = smoothstep(w, w * 0.35, abs(d - size));
        col += pal(fi * 0.15 + b * 0.07) * line * (1.3 - fi * 0.17);
    }
    // the inner polygon fills on the downbeat
    float down = exp(-uBar * 5.0);
    col += mix(uCol2, vec3(1.0), 0.4 * uStrobe) * step(d, 0.16) * down * 1.4;
    // thin outer glow ring that pulses with the bass
    col += uCol3 * 0.06 / (abs(d - 1.2) + 0.06) * 0.15 * (0.3 + uBass);
    return col;
}

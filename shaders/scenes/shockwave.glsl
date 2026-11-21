// @name: Shockwave
// @moods: peak groove build
// Every beat fires a ring that explodes outwards; the core punches on the kick.
// In build-ups the rings come twice as fast.
vec3 scene(vec2 uv, vec2 p) {
    vec3 col = vec3(0.0);
    float rate = uBuild > 0.6 ? 2.0 : 1.0;
    float bb = uBeat * rate;
    float r = length(p);
    float a = atan(p.y, p.x);
    for (int k = 0; k < 4; k++) {
        float age = fract(bb) + float(k);                    // beats since this ring fired
        float id = floor(bb) - float(k);
        float rad = 1.9 * (1.0 - exp(-age * 2.4));           // explodes out, then eases
        float w = 0.012 + 0.05 * exp(-age * 2.5);
        float wob = (spec(fract(a / TAU + hash11(id))) - 0.3) * 0.08 * exp(-age);
        float ring = smoothstep(w, 0.0, abs(r - rad - wob));
        float glow = 0.004 / (abs(r - rad - wob) + 0.004);
        float fade = exp(-age * 1.4);
        col += pal(hash11(id) * 0.5 + 0.1 * float(k)) * (ring * 1.6 + glow * 0.25) * fade;
    }
    // core: hard punch on the kick
    float cr = 0.14 + 0.14 * uKick;
    float core = smoothstep(cr, cr - 0.015, r);
    col += mix(uCol2, vec3(1.0), 0.5 * uKick) * core * (0.2 + 1.4 * uKick);
    // radial spikes on the first beat of each bar
    float down = exp(-uBar * 3.0);
    float spikes = pow(abs(sin(a * 6.0 + floor(uBeat / 4.0))), 60.0) * smoothstep(0.15, 0.5, r) * exp(-r * 1.5);
    col += uCol1 * spikes * down * 2.0;
    return col;
}

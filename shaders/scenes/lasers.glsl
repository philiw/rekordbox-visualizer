// @name: Laser Show
// @moods: peak groove build
// A club laser rig: white-hot beam cores with saturated glow, fading into haze.
// Every bar picks a new pattern - twin fans, ceiling rotor, audience scanners,
// crossfire, starburst - and a drop fires fans + crossfire together.
// Beams chop in 16ths (quarters with strobe off), flare on the kick and all
// fire together on the first beat of each bar.

float gEnv;       // overall brightness envelope (beat, kick, drop)

float beamGate(float i) {
    float rate = uStrobe > 0.5 ? 4.0 : 1.0;                       // 16ths, or quarters without strobe
    float on = step(0.35, hash21(vec2(i * 3.7 + uSeed, floor(uBeat * rate))));
    float downbeat = step(uBar, 0.25);                            // everything on for the "1"
    return max(mix(1.0, on, 0.3 + 0.6 * uEnergy), downbeat);
}

// one beam from origin o at angle ang: white core + coloured glow, fading with distance
void addBeam(inout vec3 col, vec2 p, vec2 o, float ang, float w, vec3 c, float gain) {
    vec2 dir = vec2(cos(ang), sin(ang));
    vec2 d = p - o;
    float along = dot(d, dir);
    if (along < 0.0) return;
    float dist = abs(d.x * dir.y - d.y * dir.x);
    float fade = exp(-along * 0.28);
    float core = smoothstep(w, w * 0.2, dist);
    float glow = (w * 0.9) / (dist + w * 0.9);
    float wide = (w * 6.0) / (dist + w * 6.0);
    // the envelope (kick, beat) drives the beams themselves; the wide halo stays faint so
    // many beams don't add up to a fog that washes out the dark background
    col += ((mix(c, vec3(1.0), 0.75) * core * 1.4 + c * glow * 0.75) * gEnv + c * wide * 0.025) * fade * gain;
}

vec3 laserColour(float i) {
    vec3 c = pal(i * 0.37 + floor(uBeat / 4.0) * 0.21);
    return c * c * 1.6 + 0.05;                                    // push saturation for a laser look
}

void twinFans(inout vec3 col, vec2 p, float aspect, float w, float speed) {
    float sweep = sin(uBeat * PI * 0.5 * speed);
    for (int side = 0; side < 2; side++) {
        float sd = side == 0 ? 1.0 : -1.0;
        vec2 o = vec2(-sd * aspect * 0.98, -1.02);
        for (int i = 0; i < 9; i++) {
            float fi = float(i) / 8.0;
            float a = mix(0.18, 1.35, fi) + sweep * 0.32 * sd;
            a = side == 0 ? a : PI - a;
            float id = float(i + side * 16);
            addBeam(col, p, o, a, w, laserColour(fi + float(side) * 0.5), beamGate(id));
        }
    }
}

void ceilingRotor(inout vec3 col, vec2 p, float w, float speed) {
    vec2 o = vec2(0.0, 1.05);
    float snap = floor(uBeat) + smoothstep(0.0, 0.2, fract(uBeat));     // jumps on each beat
    float swing = sin(uBeat * PI * 0.25 * speed) * 0.5 + snap * 0.12;
    for (int i = 0; i < 12; i++) {
        float fi = float(i) - 5.5;
        float a = -PI * 0.5 + fi * 0.13 + sin(swing + fi * 0.3) * 0.35;
        addBeam(col, p, o, a, w, laserColour(abs(fi) / 6.0), beamGate(float(i) + 40.0));
    }
}

void scanners(inout vec3 col, vec2 p, float aspect, float w, float speed) {
    for (int i = 0; i < 6; i++) {
        float fi = float(i);
        vec2 o = vec2((fi / 5.0 * 2.0 - 1.0) * aspect * 0.85, -1.05);
        float a = PI * 0.5 + sin(uBeat * PI * speed + fi * 1.1) * 1.05;   // fast audience scan
        addBeam(col, p, o, a, w * 1.3, laserColour(fi / 6.0), beamGate(fi + 60.0));
        addBeam(col, p, o, a + 0.06, w * 0.8, laserColour(fi / 6.0 + 0.2), beamGate(fi + 70.0) * 0.6);
    }
}

void crossfire(inout vec3 col, vec2 p, float aspect, float w, float speed) {
    for (int side = 0; side < 2; side++) {
        float sd = side == 0 ? 1.0 : -1.0;
        for (int j = 0; j < 3; j++) {
            float fj = float(j) - 1.0;
            vec2 o = vec2(-sd * aspect * 1.02, fj * 0.55);
            float base = side == 0 ? 0.0 : PI;
            float wob = sin(uBeat * PI * 0.5 * speed + fj * 2.0 + float(side) * 1.3) * 0.35;
            for (int k = 0; k < 3; k++) {
                float fk = float(k) - 1.0;
                float a = base + (wob + fk * 0.11) * sd;
                float id = float(j * 3 + k + side * 9) + 80.0;
                addBeam(col, p, o, a, w, laserColour(float(j) / 3.0 + float(side) * 0.5), beamGate(id));
            }
        }
    }
}

void starburst(inout vec3 col, vec2 p, float w, float speed) {
    float snap = floor(uBeat) + smoothstep(0.0, 0.15, fract(uBeat));
    float rot0 = snap * TAU / 32.0 * speed;
    vec2 o = vec2(0.0);
    for (int i = 0; i < 16; i++) {
        float a = float(i) / 16.0 * TAU + rot0;
        vec2 dir = vec2(cos(a), sin(a));
        float along = dot(p, dir);
        // pulses racing outwards along the beams, one wave per beat
        float pulse = 0.35 + 0.65 * smoothstep(0.25, 0.0, abs(fract(along * 1.5 - uBeat) - 0.5) - 0.2);
        addBeam(col, p, o, a, w, laserColour(float(i) / 16.0), beamGate(float(i) + 110.0) * pulse);
    }
}

vec3 scene(vec2 uv, vec2 p) {
    float aspect = uRes.x / uRes.y;
    float bar = floor(max(uGridBeat, 0.0) / 4.0);
    int mode = int(hash11(bar * 1.913 + uSeed) * 5.0);
    float speed = 1.0 + 2.0 * uBuild;                              // build-ups sweep faster
    float w = 0.0045 + 0.0035 * uKick;                             // beams fatten on the kick
    gEnv = 0.55 + 0.45 * exp(-fract(uBeat) * 4.0) + 0.45 * uKick + 0.25 * uDrop;
    if (uDrop > 0.5) gEnv *= 0.75;                                 // twice the beams in a drop

    vec3 col = vec3(0.0);
    if (uDrop > 0.5) {                                             // drop: fans + crossfire at once
        twinFans(col, p, aspect, w, speed);
        crossfire(col, p, aspect, w, speed);
    } else if (mode == 0) twinFans(col, p, aspect, w, speed);
    else if (mode == 1) ceilingRotor(col, p, w, speed);
    else if (mode == 2) scanners(col, p, aspect, w, speed);
    else if (mode == 3) crossfire(col, p, aspect, w, speed);
    else starburst(col, p, w, speed);

    // haze the beams light up, a bit thicker with the bass
    float haze = fbm(p * 1.4 + vec2(uTime * 0.04, -uTime * 0.02));
    col *= 0.75 + 0.5 * haze;
    col += (uCol1 * 0.025 + uCol3 * 0.02) * haze * (0.4 + uBass);
    return col;
}

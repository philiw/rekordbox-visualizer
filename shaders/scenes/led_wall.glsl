// @name: LED Wall
// @moods: groove peak build
// A club LED panel: round LEDs on a grid, a new pattern every bar
// (spectrum columns, beat sweep, flipping checker, hi-hat sparkle, kick burst).
vec3 scene(vec2 uv, vec2 p) {
    vec2 grid = vec2(32.0, 18.0);
    vec2 cell = uv * grid;
    vec2 id = floor(cell);
    vec2 f = fract(cell) - 0.5;
    float led = smoothstep(0.42, 0.28, length(f));
    float b = floor(uBeat);
    int mode = int(hash11(floor(uBeat / 4.0) * 3.7 + uSeed) * 5.0);
    if (uBuild > 0.6) mode = 1;                                  // build-ups: sweeps
    float x = (id.x + 0.5) / grid.x;
    float y = (id.y + 0.5) / grid.y;

    float v;
    if (mode == 0) {            // spectrum columns, mirrored from the centre
        float s = spec(abs(x - 0.5) * 1.7);
        v = step(y, s * 1.05) * (0.7 + 0.6 * uKick);
    } else if (mode == 1) {     // a bright column sweeps across every beat (twice in build-ups)
        float pos = fract(uBeat * (uBuild > 0.6 ? 2.0 : 1.0));
        v = exp(-abs(x - pos) * 20.0) + exp(-abs(1.0 - x - pos) * 20.0);
    } else if (mode == 2) {     // checker that flips on every beat
        v = mod(id.x + id.y + b, 2.0) * exp(-fract(uBeat) * 4.0) * 1.3;
    } else if (mode == 3) {     // random sparkle on the 16ths, denser with more hi-hats
        v = step(0.88 - 0.3 * uHigh, hash21(id + floor(uBeat * 4.0) * 1.7));
    } else {                    // burst from the centre on the kick
        float d = length((vec2(x, y) - 0.5) * vec2(grid.x / grid.y, 1.0));
        v = smoothstep(0.09, 0.0, abs(d - fract(uBeat) * 1.3)) * 1.2
          + (1.0 - smoothstep(0.0, 0.2 + 0.25 * uKick, d)) * uKick * 1.5;
    }
    vec3 c = pal(x * 0.5 + b * 0.13);
    vec3 col = c * led * clamp(v, 0.0, 1.6) * 1.1;
    col += c * led * 0.035;                                      // unlit LEDs, faintly visible
    return col;
}

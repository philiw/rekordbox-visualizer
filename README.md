# Rekordbox Visualizer

Real-time visuals for your DJ set, generated on the GPU. The app listens to what rekordbox (or any other DJ software) is playing and works out:

- **Tempo and beat phase.** Motion is locked to the beat. If you turn on Ableton Link in rekordbox, it uses that for exact sync.
- **Kicks and frequency bands** (sub / bass / mids / highs) for pulses, flashes and spectrum shapes.
- **Song section:** `groove`, `breakdown`, `buildup` and `drop`. Scenes are chosen to fit each section, and a drop gets a hard cut and a flash.
- **Musical key.** This sets the colour palette. Keys that sit next to each other on the Camelot wheel get neighbouring hues, so harmonic mixes drift smoothly through the colours.

There are 8 GPU shader scenes: Neon Tunnel, Kaleidoscope, Pulse Cells, Liquid Plasma, Retro Horizon, Hyperspace, Laser Show and Spectrum Bloom. They switch on phrase boundaries (every 32 beats) and blend with transitions that run in time with the tempo.

## Requirements

- Windows 10/11. Audio capture uses WASAPI loopback.
- Python 3.10 or newer, from [python.org](https://www.python.org/downloads/).
- A GPU with OpenGL 3.3. Integrated graphics work too.

## Start

```bash
git clone https://github.com/philiw/rekordbox-visualizer.git
```

Then double-click **`Start Visualizer.bat`**. The first start creates a local Python environment and installs the dependencies, which takes about a minute. Then play something in rekordbox.

You can also set it up by hand: `pip install -r requirements.txt`, then `python main.py`.

To go fullscreen on an external monitor: press **M**, or run `"Start Visualizer.bat" --fullscreen --monitor 1`.
Fullscreen is borderless, so you can click around in rekordbox on the laptop screen and the visuals keep running.

To try it without rekordbox, point it at any WAV file: `--device path\to\track.wav`

## Getting rekordbox's audio into the app

By default the app picks the loudest audio source and prefers a connected Pioneer DJ controller (DDJ / XDJ / DJM). If the current source stays silent for a few seconds, it scans all sources and switches to the one that is playing music.

- **D** cycles through sources by hand. The HUD shows which source is in use.
- To see the current level of every source: `"Start Visualizer.bat" --list-devices`
- To force a source: `--device "DDJ"` (any part of its name works)

### DJ controllers (DDJ-FLX4 etc.)

Rekordbox opens DJ controllers in exclusive mode, so no other program can record their audio. The info panel then shows "locked by another app". The reliable fix is a silent virtual cable:

1. Install the free [VB-CABLE](https://vb-audio.com/Cable/) driver and restart rekordbox.
2. In rekordbox, open *Preferences → Audio* and turn on **PC MASTER OUT**. The full label reads "Output audio from the computer's built-in speakers and your DJ equipment".
3. In Windows, open *Settings → System → Sound → Volume mixer*. While a track is playing, set **rekordbox**'s output device to **CABLE Input**.

Your mix still plays through the controller. The copy for the PC goes into the cable, where nobody hears it, and the visualizer picks it up automatically.

Muting the laptop speakers instead doesn't work on many sound drivers, because the app then receives silence. As a last resort, the laptop microphone can listen to your speakers.

## Tighter sync: Ableton Link

If your rekordbox has the **LINK** button (Performance mode), switch it on. The HUD then shows `LINK`, and tempo and beat phase come straight from rekordbox instead of being worked out from the audio.

## Keys

| Key | Action |
|---|---|
| F / F11 | Toggle fullscreen |
| M | Fullscreen on the next monitor |
| → / Space, ← | Next / previous scene |
| 1–8 | Jump to a scene |
| L | Lock the current scene (stops automatic switching) |
| B | Press on a downbeat ("the 1") to line up bars and phrases with the music |
| C | Shift the colour palette |
| S | Strobe on/off. Strobes only fire on drops and at the peak of build-ups. |
| [ / ] | Visual latency −/+ 10 ms |
| D | Next audio source |
| H | Hide / show the HUD |
| R | Reload the shaders (after editing a scene) |
| P | Save a screenshot |
| Esc | Leave fullscreen, then quit |

## Options

```
--fullscreen          start fullscreen
--monitor N           monitor for fullscreen (0 = laptop, 1 = external)
--device NAME         audio source (part of its name), or a .wav file to test without rekordbox
--scale 0.75          render at lower resolution if the frame rate drops
--sensitivity 1.5     input gain for quiet sources
--latency 30          shift visuals in ms (+ = earlier)
--phrase 16           beats between automatic scene changes (default 32)
--scene tunnel        start on one scene and lock it
--no-strobe           never flash
--no-link             ignore Ableton Link
--no-hud              start with the HUD hidden
```

## Laptops with two GPUs

Windows may run Python on the integrated graphics. The app prints the GPU it uses at startup, and the HUD shows the fps.
To use the dedicated GPU, go to *Settings → System → Display → Graphics*, add your `python.exe` (run `where python` to find it), and set it to **High performance**.

## Make your own scenes

Drop a `.glsl` file into `shaders/scenes/` that defines `vec3 scene(vec2 uv, vec2 p)`. The available inputs are listed in `shaders/common.glsl`: `uBeat`, `uKick`, `uBass`, `uEnergy`, `uBuild`, `uDrop`, the palette `uCol1..3`, the spectrum `spec(x)` and so on. Tag it with
`// @name: My Scene` and `// @moods: calm groove build peak` so the director knows when to use it.
Press **R** to reload the shaders while the app is running.

## How it works

- `audio.py` captures 48 kHz audio through WASAPI. On every 10.7 ms hop it runs an FFT and computes:
  - adaptive-gain band levels;
  - spectral flux, used for onsets and kicks;
  - autocorrelation of the onset envelope (comb-filtered, with a prior centred on dance-music tempos) for BPM;
  - beat phase, by folding recent onsets onto the beat grid. This runs like a phase-locked loop and freewheels through breakdowns.
  - Chroma is matched against Krumhansl key profiles to get the key and its Camelot code.
  - Sections come from how strong the kick pattern is and the bass level compared with the track's groove level. A riser shows up as rising high-frequency energy.
- `main.py` is the OpenGL renderer (moderngl + GLFW). It renders the scene into a frame buffer, then a transition mix with feedback, then a post-processing pass (bloom, chromatic aberration on kicks, flashes, tone mapping, vignette, grain) plus the HUD. It also holds the scene director and the key-to-colour palette.

## Ready-made alternatives

If you'd rather use something off the shelf:
- **Synesthesia** (paid): a polished audio-reactive VJ app with a large scene library.
- **projectM**: free, the open-source successor to MilkDrop.
- **Resolume Avenue/Arena**: professional VJ software. It needs video content and more setup.

## License

MIT. See [LICENSE](LICENSE).

This project is not affiliated with or endorsed by AlphaTheta / Pioneer DJ. rekordbox is a trademark of AlphaTheta Corporation.

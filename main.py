"""Rekordbox Visualizer - audio-reactive visuals for a live DJ set.

Listens to the audio rekordbox plays (WASAPI loopback or the controller's
recording input), works out tempo, beat phase, kicks, key and song section,
and drives a set of GPU shader scenes with it.

Run:  python main.py            (see README.md for options and keys)
"""
from __future__ import annotations

import argparse
import colorsys
import math
import os
import random
import re
import sys
import time
from pathlib import Path

import glfw
import moderngl
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import audio
from vibes import Vibes

HERE = Path(__file__).resolve().parent
SHADERS = HERE / "shaders"

VERT = """
#version 330
in vec2 in_pos;
out vec2 vUv;
void main() { vUv = in_pos * 0.5 + 0.5; gl_Position = vec4(in_pos, 0.0, 1.0); }
"""

SECTION_MOOD = {"idle": "calm", "breakdown": "calm", "buildup": "build", "drop": "peak", "groove": "groove"}
SECTION_COLOR = {"idle": (140, 140, 140), "breakdown": (120, 170, 255), "buildup": (255, 200, 60),
                 "drop": (255, 60, 90), "groove": (90, 230, 140)}


def set_uniform(prog, name, value):
    if name in prog:
        try:
            prog[name].value = value
        except Exception:
            pass


# =========================================================================== scenes
class Scene:
    def __init__(self, path: Path, prog, vao):
        self.path = path
        self.prog = prog
        self.vao = vao
        src = path.read_text(encoding="utf-8")
        m = re.search(r"@name:\s*(.+)", src)
        self.name = m.group(1).strip() if m else path.stem
        m = re.search(r"@moods:\s*(.+)", src)
        self.moods = set(m.group(1).split()) if m else {"groove"}


def load_scenes(ctx, vbo):
    common = (SHADERS / "common.glsl").read_text(encoding="utf-8")
    scenes = []
    for f in sorted((SHADERS / "scenes").glob("*.glsl")):
        try:
            prog = ctx.program(vertex_shader=VERT, fragment_shader=common + "\n#line 1\n" + f.read_text(encoding="utf-8"))
            vao = ctx.vertex_array(prog, [(vbo, "2f", "in_pos")])
            scenes.append(Scene(f, prog, vao))
        except Exception as e:
            print(f"[shader] {f.name} failed to compile:\n{e}")
    if not scenes:
        raise SystemExit("No scene compiled - check the shader errors above")
    print("[shader] scenes: " + ", ".join(s.name for s in scenes))
    return scenes


# =========================================================================== director
TRANSITION_BEATS = {"calm": 8, "build": 2, "peak": 0, "groove": 1}  # 0 = hard cut


class Director:
    """Decides which scene is on screen, when to switch and how (cut / fade / wipe).

    Rules (configured in vibes.toml):
      * every part of the song (calm / groove / build / peak) has its own scene pool,
      * the playing track's genre narrows the pool further,
      * scenes stay for N bars and switch on the bar/phrase grid,
      * a drop cuts straight to a peak scene, other section changes fade.
    """

    def __init__(self, scenes, vibes):
        self.scenes = scenes
        self.vibes = vibes
        self.pace = 1.0               # +/- keys: multiplier on all bar counts
        self.cur = 0
        self.nxt = None
        self.t_start = 0.0
        self.t_dur = 1.0
        self.style = 0
        self.locked = False
        self.history = []
        self.seed = {i: random.random() * 100 for i in range(len(scenes))}
        self.last_bar = None
        self.bars_on_scene = 0
        self.last_section = "idle"
        self.section_seen = 0.0
        self._section_handled = True
        self.last_switch = 0.0
        self.genre = None
        self.genre_dirty = False
        self.flash = 0.0
        self.pick_start()

    # ------------------------------------------------------------------ choosing
    def moods(self, i):
        return self.vibes.moods_for(self.scenes[i])

    def pool(self):
        return self.vibes.genre_pool(self.genre)

    def fits(self, i, mood):
        return mood in self.moods(i) and self.vibes.in_pool(self.scenes[i], self.pool())

    def pick_start(self):
        calm = [i for i in range(len(self.scenes)) if self.fits(i, "calm")]
        self.cur = random.choice(calm or list(range(len(self.scenes))))

    def choose(self, mood):
        n = len(self.scenes)
        auto = [i for i in range(n) if self.moods(i)]            # [] in vibes.toml = manual only
        genre = [i for i in auto if self.vibes.in_pool(self.scenes[i], self.pool())]
        for cands in ([i for i in genre if mood in self.moods(i)],   # genre + song part
                      genre,                                          # genre, any part
                      [i for i in auto if mood in self.moods(i)],     # song part, any genre
                      auto or list(range(n))):
            others = [i for i in cands if i != self.cur]
            if others:
                fresh = [i for i in others if i not in self.history[-2:]]
                return random.choice(fresh or others)
        return self.cur

    def switch(self, idx, now, beats, bpm, style=None):
        if idx == self.cur and self.nxt is None:
            return
        if self.nxt is not None:  # finish a running transition first
            self.cur = self.nxt
        self.history.append(self.cur)
        self.seed[idx] = random.random() * 100
        if beats <= 0:
            self.cur, self.nxt = idx, None
        else:
            self.nxt = idx
            self.t_start = now
            self.t_dur = beats * 60.0 / max(bpm, 60)
            self.style = random.choice([0, 0, 1, 2, 3]) if style is None else style
        self.bars_on_scene = 0
        self.last_switch = now

    def manual(self, step=None, index=None, now=0.0, bpm=120.0):
        idx = (self.cur + step) % len(self.scenes) if index is None else index % len(self.scenes)
        self.switch(idx, now, 0.5, bpm, style=0)

    def bars_needed(self, section):
        return self.vibes.bars(SECTION_MOOD[section], self.pace)

    # ------------------------------------------------------------------ per frame
    def update(self, snap, beat, now):
        bpm = snap["bpm"]
        sec = snap["section"]
        mood = SECTION_MOOD[sec]
        self.vibes.reload()
        if self.nxt is not None and now - self.t_start >= self.t_dur:
            self.cur, self.nxt = self.nxt, None
        self.flash *= math.exp(-(1 / 60) / 0.12)

        track = snap.get("track")
        genre = (track or {}).get("genre") or None
        if genre != self.genre:
            self.genre = genre
            self.genre_dirty = True   # re-check the scene at the next 4-bar boundary

        # section changes: a drop cuts immediately, others wait 1 s to avoid flapping
        if sec != self.last_section:
            self.last_section = sec
            self.section_seen = now
            self._section_handled = sec == "drop"
            if sec == "drop":
                self.flash = 1.0
                if not self.locked:
                    self.switch(self.choose("peak"), now, 0, bpm)
        if not self._section_handled and now - self.section_seen > 1.0 and not self.locked:
            self._section_handled = True
            showing = self.nxt if self.nxt is not None else self.cur
            if not self.fits(showing, mood):
                self.switch(self.choose(mood), now, 4 if mood == "calm" else 2, bpm)

        # bar grid: count bars on the current scene and switch on (phrase-aligned) bars
        bar = math.floor((beat - snap["bar_offset"]) / 4)
        if self.last_bar is None:
            self.last_bar = bar
        if bar != self.last_bar:
            self.last_bar = bar
            self.bars_on_scene += 1
            if self.locked:
                return
            showing = self.nxt if self.nxt is not None else self.cur
            if self.genre_dirty and bar % 4 == 0:
                self.genre_dirty = False
                if not self.vibes.in_pool(self.scenes[showing], self.pool()):
                    self.switch(self.choose(mood), now, 4, bpm)   # new genre: fade to a fitting scene
                    return
            need = self.bars_needed(sec)
            align = 8 if need >= 8 else (4 if need >= 4 else 1)
            if (self.bars_on_scene >= need and bar % align == 0
                    and now - self.last_switch > self.vibes.min_seconds):
                self.switch(self.choose(mood), now, TRANSITION_BEATS[mood], bpm)

    @property
    def mix(self):
        if self.nxt is None:
            return 0.0
        return min(1.0, (time.perf_counter() - self.t_start) / self.t_dur)


# =========================================================================== palette
def hsv(h, s, v):
    return np.array(colorsys.hsv_to_rgb(h % 1.0, max(0, min(1, s)), max(0, min(1, v))), np.float32)


class Palette:
    """Colours follow the musical key: neighbouring keys on the Camelot wheel get
    neighbouring hues, so a harmonic mix glides smoothly through the colour wheel."""

    def __init__(self):
        self.cols = [hsv(0.62, 0.8, 1), hsv(0.75, 0.7, 1), hsv(0.5, 0.9, 0.9)]
        self.hue_shift = 0.0

    def update(self, snap, dt):
        known = snap["key"] != "--"
        h = ((snap["camelot"] - 1) / 12.0 + 0.55 + self.hue_shift) if known else 0.62 + self.hue_shift
        e, drop, build = snap["energy"], snap["drop"], snap["build"]
        spread = 0.06 + 0.08 * e + 0.15 * drop + 0.05 * build
        sat = 0.65 + 0.3 * e
        if snap["minor"]:
            # minor: moody analogous colours plus a cool split-complement accent
            tgt = [hsv(h, sat + 0.1, 1.0), hsv(h + spread, sat, 1.0), hsv(h - 0.33 - spread, 0.9, 0.9)]
        else:
            # major: brighter, complementary contrast
            tgt = [hsv(h, sat, 1.0), hsv(h + 0.5, sat - 0.1, 1.0), hsv(h + spread, 0.85, 0.95)]
        k = 1 - math.exp(-dt / (0.4 if drop > 0.9 else 2.5))
        self.cols = [c + (t - c) * k for c, t in zip(self.cols, tgt)]


# =========================================================================== HUD
class Hud:
    W, H = 600, 212

    def __init__(self, ctx):
        self.tex = ctx.texture((self.W, self.H), 4)
        self.tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        def font(names, size):
            for n in names:
                try:
                    return ImageFont.truetype(n, size)
                except Exception:
                    pass
            return ImageFont.load_default()
        self.f_big = font(["segoeuib.ttf", "arialbd.ttf"], 34)
        self.f = font(["segoeui.ttf", "arial.ttf"], 16)
        self.f_small = font(["segoeui.ttf", "arial.ttf"], 13)
        self.last = 0.0

    def draw(self, snap, beat, scene_name, locked, strobe, latency_ms, fps, bars=None):
        img = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, self.W - 1, self.H - 1], 14, fill=(8, 8, 14, 175))
        sec = snap["section"]
        sc = SECTION_COLOR.get(sec, (255, 255, 255))
        d.text((16, 8), f"{snap['bpm']:.1f}", font=self.f_big, fill=(255, 255, 255, 255))
        d.text((122, 26), "BPM" + ("  LINK" if snap["link"] else ""), font=self.f, fill=(170, 170, 190, 255))
        # beat dots
        b = int(math.floor(beat - snap["bar_offset"])) % 4
        for i in range(4):
            x = 232 + i * 22
            d.ellipse([x, 22, x + 14, 36], fill=(sc + (255,)) if i == b else (60, 60, 75, 255))
        d.text((336, 8), f"{snap['camelot_str']}", font=self.f_big, fill=(255, 255, 255, 255))
        from_rb = snap.get("key_source") == "rekordbox"  # exact key from the library -> green
        d.text((400, 26), snap["key"], font=self.f, fill=(110, 230, 140, 255) if from_rb else (170, 170, 190, 255))
        d.rounded_rectangle([462, 16, 584, 42], 8, fill=sc + (255,))
        d.text((523, 29), sec.upper(), font=self.f, fill=(10, 10, 10, 255), anchor="mm")

        d.text((16, 56), f"Scene: {scene_name}" + ("   [LOCKED]" if locked else f"   [auto, {bars} bars]"),
               font=self.f, fill=(230, 230, 240, 255))
        t = snap.get("track")
        if t:
            name = f"{t['artist']} - {t['title']}" if t["artist"] else t["title"]
            name = name if len(name) < 48 else name[:45] + "..."
            extra = (f"   {t['genre']}" if t.get("genre") else "") + (f"   {t['bpm']:.1f} BPM" if t.get("bpm") else "")
            d.text((16, 78), "Track: " + name + extra, font=self.f_small, fill=(110, 230, 140, 255))
        # phrase progress
        ph = ((beat - snap["bar_offset"]) % 32) / 32
        d.rounded_rectangle([400, 62, 584, 72], 5, fill=(50, 50, 65, 255))
        d.rounded_rectangle([400, 62, 400 + max(10, int(184 * ph)), 72], 5, fill=sc + (255,))

        bands = snap["bands"]
        meters = [("SUB", bands["sub"]), ("BASS", bands["bass"]), ("LOMID", bands["lowmid"]),
                  ("MID", bands["mid"]), ("HIGH", bands["high"]), ("ENERGY", snap["energy"]),
                  ("BUILD", snap["build"]), ("KICK", snap["kick"])]
        for i, (name, v) in enumerate(meters):
            x = 16 + i * 72
            d.text((x, 102), name, font=self.f_small, fill=(150, 150, 170, 255))
            d.rounded_rectangle([x, 120, x + 62, 128], 4, fill=(45, 45, 60, 255))
            d.rounded_rectangle([x, 120, x + max(6, int(62 * min(1, v))), 128], 4, fill=(120 + int(135 * v), 200, 255 - int(100 * v), 255))

        dev = snap["device"]
        dev = dev if len(dev) < 52 else dev[:49] + "..."
        d.text((16, 140), f"Source: {dev}", font=self.f_small, fill=(170, 170, 190, 255))
        if snap.get("status"):  # audio problem takes priority over the info line
            d.text((16, 160), "! " + snap["status"][:80], font=self.f_small, fill=(255, 170, 80, 255))
        else:
            d.text((16, 160), f"Strobe {'on' if strobe else 'off'}  ·  latency {latency_ms:+d} ms  ·  {fps:.0f} fps",
                   font=self.f_small, fill=(170, 170, 190, 255))
        d.text((16, 182), "F full · M monitor · ←/→ scene · L lock · +/- pace · S strobe · B downbeat · H hide",
               font=self.f_small, fill=(120, 120, 140, 255))
        self.tex.write(img.tobytes())


# =========================================================================== app
class App:
    def __init__(self, args):
        self.args = args
        if not glfw.init():
            raise SystemExit("GLFW init failed")
        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, True)
        self.win = glfw.create_window(1280, 720, "Rekordbox Visualizer", None, None)
        if not self.win:
            raise SystemExit("Could not open an OpenGL 3.3 window")
        glfw.make_context_current(self.win)
        glfw.swap_interval(1)
        self.ctx = moderngl.create_context()
        print(f"[gl] {self.ctx.info['GL_RENDERER']}")

        quad = np.array([-1, -1, 1, -1, -1, 1, 1, 1], np.float32)
        self.vbo = self.ctx.buffer(quad.tobytes())
        self.scenes = load_scenes(self.ctx, self.vbo)
        self.mix_prog = self.ctx.program(vertex_shader=VERT, fragment_shader=(SHADERS / "mix.glsl").read_text())
        self.post_prog = self.ctx.program(vertex_shader=VERT, fragment_shader=(SHADERS / "post.glsl").read_text())
        self.mix_vao = self.ctx.vertex_array(self.mix_prog, [(self.vbo, "2f", "in_pos")])
        self.post_vao = self.ctx.vertex_array(self.post_prog, [(self.vbo, "2f", "in_pos")])

        self.spec_tex = self.ctx.texture((audio.NSPEC, 1), 1, dtype="f4")
        self.wave_tex = self.ctx.texture((audio.NWAVE, 1), 1, dtype="f4")
        for t in (self.spec_tex, self.wave_tex):
            t.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.hud = Hud(self.ctx)
        self.hud_on = not args.no_hud
        self.strobe = not args.no_strobe
        self.latency = args.latency / 1000.0

        self.size = None
        self._alloc()

        self.analyzer = audio.Analyzer(args.device, sensitivity=args.sensitivity)
        if not args.no_link:
            self.analyzer.external_clock = audio.LinkClock()
        if not args.no_library:
            import rekordbox_db
            self.library = rekordbox_db.RekordboxLibrary()
            self.analyzer.library = self.library
        self.analyzer.start()
        self.director = Director(self.scenes, Vibes(HERE / "vibes.toml"))
        self.director.pace = args.pace
        if args.scene:
            hits = [i for i, s in enumerate(self.scenes) if args.scene.lower() in (s.name + s.path.stem).lower()]
            if hits:
                self.director.cur = hits[0]
                self.director.locked = True
        self.palette = Palette()
        self.t0 = time.perf_counter()
        self.frames = 0
        self.fps = 60.0
        self.windowed_pos = (100, 100, 1280, 720)
        self.monitor_idx = args.monitor
        self.fullscreen = False

        glfw.set_key_callback(self.win, self.on_key)
        glfw.set_char_callback(self.win, self.on_char)
        if args.fullscreen:
            self.set_fullscreen(True)

    # ------------------------------------------------------------------ buffers
    def _alloc(self):
        fw, fh = glfw.get_framebuffer_size(self.win)
        fw, fh = max(fw, 16), max(fh, 16)
        if self.size == (fw, fh):
            return
        self.size = (fw, fh)
        rw, rh = max(16, int(fw * self.args.scale)), max(16, int(fh * self.args.scale))
        self.rsize = (rw, rh)

        def tex(mip=False):
            t = self.ctx.texture((rw, rh), 4, dtype="f2")
            t.repeat_x = t.repeat_y = False
            t.filter = (moderngl.LINEAR_MIPMAP_LINEAR if mip else moderngl.LINEAR, moderngl.LINEAR)
            return t
        self.tex_a, self.tex_b = tex(), tex()
        self.fbo_a = self.ctx.framebuffer([self.tex_a])
        self.fbo_b = self.ctx.framebuffer([self.tex_b])
        self.comp = [tex(True), tex(True)]
        self.comp_fbo = [self.ctx.framebuffer([t]) for t in self.comp]
        for f, t in zip(self.comp_fbo, self.comp):
            f.clear(0, 0, 0, 1)
            t.build_mipmaps()
        self.comp_i = 0

    # ------------------------------------------------------------------ window
    def set_fullscreen(self, on):
        """Borderless fullscreen: no mode switch, and it stays up while you click
        around in rekordbox on the other screen."""
        monitors = glfw.get_monitors()
        if on:
            if not self.fullscreen:
                x, y = glfw.get_window_pos(self.win)
                w, h = glfw.get_window_size(self.win)
                self.windowed_pos = (x, y, w, h)
            mon = monitors[self.monitor_idx % len(monitors)]
            mx, my = glfw.get_monitor_pos(mon)
            mode = glfw.get_video_mode(mon)
            glfw.set_window_attrib(self.win, glfw.DECORATED, False)
            glfw.set_window_pos(self.win, mx, my)
            glfw.set_window_size(self.win, mode.size.width, mode.size.height)
            glfw.set_input_mode(self.win, glfw.CURSOR, glfw.CURSOR_HIDDEN)
            self.fullscreen = True
            print(f"[window] fullscreen on monitor {self.monitor_idx % len(monitors)}: {glfw.get_monitor_name(mon).decode(errors='ignore')} "
                  f"({mode.size.width}x{mode.size.height})")
        else:
            x, y, w, h = self.windowed_pos
            glfw.set_window_attrib(self.win, glfw.DECORATED, True)
            glfw.set_window_pos(self.win, x, y)
            glfw.set_window_size(self.win, w, h)
            glfw.set_input_mode(self.win, glfw.CURSOR, glfw.CURSOR_NORMAL)
            self.fullscreen = False

    def on_key(self, win, key, scancode, action, mods):
        if action != glfw.PRESS:
            return
        now = time.perf_counter()
        bpm = self.analyzer.snapshot()["bpm"]
        full = self.fullscreen
        if key == glfw.KEY_ESCAPE:
            if full:
                self.set_fullscreen(False)
            else:
                glfw.set_window_should_close(self.win, True)
        elif key in (glfw.KEY_F, glfw.KEY_F11) or (key == glfw.KEY_ENTER and mods & glfw.MOD_ALT):
            self.set_fullscreen(not full)
        elif key == glfw.KEY_M:
            self.monitor_idx = (self.monitor_idx + 1) % len(glfw.get_monitors())
            self.set_fullscreen(True)
        elif key in (glfw.KEY_RIGHT, glfw.KEY_SPACE):
            self.director.manual(step=1, now=now, bpm=bpm)
        elif key == glfw.KEY_LEFT:
            self.director.manual(step=-1, now=now, bpm=bpm)
        elif glfw.KEY_1 <= key <= glfw.KEY_9:
            self.director.manual(index=key - glfw.KEY_1, now=now, bpm=bpm)
        elif key == glfw.KEY_L:
            self.director.locked = not self.director.locked
        elif key == glfw.KEY_H:
            self.hud_on = not self.hud_on
        elif key == glfw.KEY_S:
            self.strobe = not self.strobe
        elif key == glfw.KEY_D:
            self.analyzer.next_device()
        elif key == glfw.KEY_B:
            self.analyzer.resync_downbeat()
        elif key == glfw.KEY_C:
            self.palette.hue_shift = (self.palette.hue_shift + 1 / 6) % 1.0
        elif key == glfw.KEY_R:
            try:
                self.scenes[:] = load_scenes(self.ctx, self.vbo)
                self.director.cur %= len(self.scenes)
                self.director.nxt = None
            except SystemExit as e:
                print(e)
        elif key == glfw.KEY_P:
            self.screenshot()

    def on_char(self, win, codepoint):
        """Typed characters (keyboard-layout aware): + - change scene pace, [ ] latency."""
        ch = chr(codepoint)
        d = self.director
        if ch == "+":
            d.pace = min(4.0, d.pace * 2)
        elif ch == "-":
            d.pace = max(0.25, d.pace / 2)
        elif ch in "[,":
            self.latency -= 0.01
        elif ch in "].":
            self.latency += 0.01
        else:
            return
        if ch in "+-":
            print(f"[vibes] scene pace x{d.pace:g}: groove scenes last {d.vibes.bars('groove', d.pace)} bars")

    def screenshot(self, path=None):
        w, h = self.size
        data = self.ctx.screen.read(viewport=(0, 0, w, h), components=3)
        img = Image.frombytes("RGB", (w, h), data).transpose(Image.FLIP_TOP_BOTTOM)
        out = Path(path) if path else HERE / "screenshots" / f"shot_{time.strftime('%Y%m%d_%H%M%S')}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(out)
        print(f"[shot] {out}")

    # ------------------------------------------------------------------ frame
    def uniforms(self, snap, beat, now):
        b = snap["bands"]
        age = now - snap["t"]
        kick = snap["kick"] * math.exp(-max(age, 0) / 0.16)
        p = self.palette.cols
        return {
            "uRes": (float(self.rsize[0]), float(self.rsize[1])), "uTime": now - self.t0, "uBeat": beat, "uBpm": snap["bpm"],
            "uBar": (beat - snap["bar_offset"]) % 4, "uPhrase": ((beat - snap["bar_offset"]) % 32) / 32,
            "uKick": kick, "uSub": b["sub"], "uBass": b["bass"], "uLowMid": b["lowmid"], "uMid": b["mid"],
            "uHigh": b["high"], "uLevel": snap["level"], "uEnergy": snap["energy"], "uBuild": snap["build"],
            "uDrop": snap["drop"], "uBright": snap["centroid"],
            "uCol1": tuple(p[0]), "uCol2": tuple(p[1]), "uCol3": tuple(p[2]),
        }

    def render_scene(self, idx, fbo, u):
        sc = self.scenes[idx]
        fbo.use()
        for k, v in u.items():
            set_uniform(sc.prog, k, v)
        set_uniform(sc.prog, "uSeed", self.director.seed.get(idx, 0.0))
        self.spec_tex.use(0)
        self.wave_tex.use(1)
        self.comp[1 - self.comp_i].use(2)
        set_uniform(sc.prog, "uSpec", 0)
        set_uniform(sc.prog, "uWave", 1)
        set_uniform(sc.prog, "uPrev", 2)
        sc.vao.render(moderngl.TRIANGLE_STRIP)

    def frame(self):
        self._alloc()
        now = time.perf_counter()
        snap = self.analyzer.snapshot()
        beat = snap["beat"] + (now - snap["beat_time"] + self.latency) * snap["bpm"] / 60.0
        dt = 1.0 / max(self.fps, 1)
        self.director.update(snap, beat, now)
        self.palette.update(snap, dt)

        self.spec_tex.write(snap["spec"].astype(np.float32).tobytes())
        self.wave_tex.write(snap["wave"].astype(np.float32).tobytes())
        u = self.uniforms(snap, beat, now)

        d = self.director
        self.render_scene(d.cur, self.fbo_a, u)
        mix = 0.0
        if d.nxt is not None:
            self.render_scene(d.nxt, self.fbo_b, u)
            mix = d.mix

        # composite into the feedback buffer
        cur = self.comp_i
        self.comp_fbo[cur].use()
        self.tex_a.use(0)
        self.tex_b.use(1)
        set_uniform(self.mix_prog, "uA", 0)
        set_uniform(self.mix_prog, "uB", 1)
        set_uniform(self.mix_prog, "uMix", mix if d.nxt is not None else 0.0)
        set_uniform(self.mix_prog, "uStyle", d.style)
        set_uniform(self.mix_prog, "uRes", self.rsize)
        self.mix_vao.render(moderngl.TRIANGLE_STRIP)
        self.comp[cur].build_mipmaps()

        # flashes: on the drop, and (if strobe is on) on beats right after the drop / end of build-up
        flash = d.flash
        if self.strobe:
            since_drop = now - d.section_seen if snap["section"] == "drop" else 99
            if since_drop < 8 * 4 * 60 / snap["bpm"] / 2:  # first 4 bars after the drop
                flash = max(flash, 0.35 * math.exp(-((beat % 1.0) * 60 / snap["bpm"]) / 0.06))
            if snap["section"] == "buildup" and snap["build"] > 0.7:
                flash = max(flash, 0.25 * snap["build"] * math.exp(-((beat * 2 % 1.0) * 30 / snap["bpm"]) / 0.05))
        else:
            flash *= 0.4

        # post-process to the screen
        self.ctx.screen.use()
        self.ctx.viewport = (0, 0, *self.size)
        self.comp[cur].use(0)
        self.hud.tex.use(1)
        if self.hud_on and now - self.hud.last > 0.1:
            self.hud.last = now
            name = self.scenes[d.nxt if d.nxt is not None else d.cur].name
            self.hud.draw(snap, beat, name, d.locked, self.strobe, int(round(self.latency * 1000)), self.fps,
                          bars=d.bars_needed(snap["section"]))
        pp = self.post_prog
        set_uniform(pp, "uTex", 0)
        set_uniform(pp, "uHud", 1)
        set_uniform(pp, "uHudOn", 1.0 if self.hud_on else 0.0)
        set_uniform(pp, "uHudSize", (float(Hud.W), float(Hud.H)))
        set_uniform(pp, "uRes", self.size)
        set_uniform(pp, "uKick", u["uKick"])
        set_uniform(pp, "uEnergy", u["uEnergy"])
        set_uniform(pp, "uFlash", flash)
        set_uniform(pp, "uFlashCol", tuple(0.6 + 0.4 * self.palette.cols[1]))
        set_uniform(pp, "uTime", u["uTime"])
        set_uniform(pp, "uBloom", 0.6 + 0.6 * snap["energy"])
        set_uniform(pp, "uExposure", 1.3)
        self.post_vao.render(moderngl.TRIANGLE_STRIP)
        self.comp_i = 1 - cur

    def run(self):
        last_title = 0.0
        last_t = time.perf_counter()
        next_shot = self.args.autoshot or 0
        while not glfw.window_should_close(self.win):
            glfw.poll_events()
            if glfw.get_window_attrib(self.win, glfw.ICONIFIED):
                time.sleep(0.05)
                continue
            self.frame()
            glfw.swap_buffers(self.win)
            now = time.perf_counter()
            self.fps += ((1.0 / max(now - last_t, 1e-4)) - self.fps) * 0.05
            last_t = now
            el = now - self.t0
            if now - last_title > 0.5:
                last_title = now
                s = self.analyzer.snapshot()
                glfw.set_window_title(self.win, f"Rekordbox Visualizer - {s['bpm']:.1f} BPM - {s['camelot_str']} - {s['section']}")
            if self.args.autoshot and el > next_shot:
                next_shot += self.args.autoshot
                self.screenshot(HERE / "screenshots" / f"auto_{int(el):04d}.png")
            if self.args.quit_after and el > self.args.quit_after:
                break
        self.analyzer.stop()
        if getattr(self, "library", None):
            self.library.stop()
        glfw.terminate()


def main():
    ap = argparse.ArgumentParser(description="Audio-reactive visuals for rekordbox DJ sets")
    ap.add_argument("--device", help="part of the audio device name to listen to, or a .wav file to test with")
    ap.add_argument("--list-devices", action="store_true", help="list audio sources with their current level and exit")
    ap.add_argument("--fullscreen", action="store_true")
    ap.add_argument("--monitor", type=int, default=0, help="monitor index for fullscreen (0 = primary)")
    ap.add_argument("--scale", type=float, default=1.0, help="render resolution scale (0.5 = faster)")
    ap.add_argument("--sensitivity", type=float, default=1.0, help="input gain multiplier")
    ap.add_argument("--latency", type=int, default=0, help="shift visuals vs. audio in ms (+ = earlier beat)")
    ap.add_argument("--pace", type=float, default=1.0,
                    help="multiply how long scenes stay (0.5 = twice as many changes); see vibes.toml")
    ap.add_argument("--no-strobe", action="store_true", help="disable beat strobes (flashing)")
    ap.add_argument("--no-link", action="store_true", help="don't use Ableton Link for tempo")
    ap.add_argument("--no-library", action="store_true",
                    help="don't read the playing track's key/BPM from the rekordbox library")
    ap.add_argument("--no-hud", action="store_true")
    ap.add_argument("--scene", help="start on this scene (name or file) and lock it")
    ap.add_argument("--autoshot", type=float, default=0, help=argparse.SUPPRESS)
    ap.add_argument("--quit-after", type=float, default=0, help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.list_devices:
        print("Measuring the level of every audio source for a moment...\n")
        for rms, dev in audio.probe_devices(audio.list_devices()):
            lvl = "error" if rms < 0 else (f"{20 * math.log10(rms + 1e-9):6.1f} dB" if rms > 0 else "silent")
            print(f"  {lvl:>10}   {audio.device_label(dev)}")
        print("\nUse e.g.  --device \"DDJ\"  to pick one.")
        return
    try:
        App(args).run()
    except (Exception, SystemExit) as e:
        if isinstance(e, SystemExit) and not e.code:
            raise
        import traceback
        traceback.print_exc()
        if WINDOWLESS:  # no console to show the error in: tell the user with a popup
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                None, f"{e}\n\nDetails: {LOG_PATH}", "Rekordbox Visualizer stopped", 0x10)
        raise


# Started with pythonw.exe (no console window): send all messages to a log file instead.
WINDOWLESS = sys.stdout is None
LOG_PATH = HERE / "visualizer.log"
if WINDOWLESS:
    _log = open(LOG_PATH, "w", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = _log


if __name__ == "__main__":
    main()

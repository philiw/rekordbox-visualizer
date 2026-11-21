"""Loads vibes.toml: scene timing, which scenes fit which part of a song, and which
scenes fit which genre. Re-read automatically when the file changes."""
from __future__ import annotations

import time
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover
    import tomli as tomllib

MOODS = ("calm", "groove", "build", "peak")
DEFAULT_BARS = {"groove": 16, "peak": 8, "build": 8, "calm": 16}
DEFAULT_TRANSITIONS = {"groove": 1, "peak": 0, "build": 1, "calm": 4}  # beats; 0 = hard cut


class Vibes:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.bars_cfg = dict(DEFAULT_BARS)
        self.min_seconds = 8.0
        self.trans_cfg = dict(DEFAULT_TRANSITIONS)
        self.scene_moods: dict[str, set[str]] = {}
        self.genres: dict[str, set[str]] = {}
        self.error = ""
        self._mtime = None
        self._checked = 0.0
        self.reload(force=True)

    # ------------------------------------------------------------------ loading
    def reload(self, force=False):
        """Re-read the file if it changed. Returns True when new settings were applied."""
        now = time.perf_counter()
        if not force and now - self._checked < 2.0:
            return False
        self._checked = now
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            if self._mtime is not None or force:
                print(f"[vibes] {self.path.name} not found - using built-in defaults")
            self._mtime = None
            return False
        if not force and mtime == self._mtime:
            return False
        self._mtime = mtime
        try:
            with open(self.path, "rb") as f:
                data = tomllib.load(f)
        except Exception as e:
            self.error = f"{self.path.name}: {e}"
            print(f"[vibes] could not read {self.path.name}, keeping the previous settings:\n  {e}")
            return False

        timing = data.get("timing", {})
        bars = dict(DEFAULT_BARS)
        for mood in MOODS:
            if mood in timing:
                bars[mood] = max(1, int(timing[mood]))
        self.bars_cfg = bars
        self.min_seconds = float(timing.get("min_seconds", 8))
        trans = dict(DEFAULT_TRANSITIONS)
        for mood, beats in data.get("transitions", {}).items():
            if mood in MOODS:
                trans[mood] = max(0.0, float(beats))
        self.trans_cfg = trans
        self.scene_moods = {k.lower(): {m.lower() for m in v} for k, v in data.get("scenes", {}).items()}
        self.genres = {k.lower(): {s.lower() for s in v} for k, v in data.get("genres", {}).items()}
        self.error = ""
        unknown = {m for ms in self.scene_moods.values() for m in ms} - set(MOODS)
        if unknown:
            print(f"[vibes] unknown moods ignored: {', '.join(sorted(unknown))} (use {', '.join(MOODS)})")
        print(f"[vibes] loaded {self.path.name}: bars per scene {bars}, "
              f"{len(self.scene_moods)} scene entries, {len(self.genres)} genres")
        return True

    # ------------------------------------------------------------------ queries
    def bars(self, mood: str, pace: float = 1.0) -> int:
        return max(1, int(round(self.bars_cfg.get(mood, 16) * pace)))

    def transition(self, mood: str) -> float:
        """Length of the fade into a new scene, in beats (0 = hard cut on the beat)."""
        return self.trans_cfg.get(mood, 1)

    def moods_for(self, scene) -> set[str]:
        """Moods of a scene: vibes.toml wins over the @moods tag in the shader file."""
        for key in (scene.path.stem.lower(), scene.name.lower()):
            if key in self.scene_moods:
                return self.scene_moods[key]
        return scene.moods

    def genre_pool(self, genre: str | None) -> set[str] | None:
        """Scene keys allowed for a genre, or None if the genre isn't configured."""
        if not genre:
            return None
        g = genre.lower()
        if g in self.genres:
            return self.genres[g]
        # longest configured name contained in the genre ("techno" in "hard techno")
        hits = [k for k in self.genres if k and k in g]
        return self.genres[max(hits, key=len)] if hits else None

    @staticmethod
    def in_pool(scene, pool) -> bool:
        return pool is None or scene.path.stem.lower() in pool or scene.name.lower() in pool

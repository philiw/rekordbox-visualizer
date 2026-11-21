"""Read the track that is playing from rekordbox's own library (read-only).

rekordbox adds every track you play to its history in master.db while you DJ,
together with its analysed BPM and key. We poll the newest history entry and
hand it to the analyzer: the key replaces the audio key estimate, and the BPM
steers the tempo tracker. Needs the optional `pyrekordbox` package.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
import threading
import time
import warnings

# Camelot <-> pitch class (C=0), same tables as audio.py
CAMELOT_MAJOR = [8, 3, 10, 5, 12, 7, 2, 9, 4, 11, 6, 1]
CAMELOT_MINOR = [5, 12, 7, 2, 9, 4, 11, 6, 1, 8, 3, 10]
NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
PITCH_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def parse_key(name: str | None):
    """'6A' / '11B' (Camelot) or 'F#m' / 'Db' / 'Abmin' (classic) -> (camelot, minor, label)."""
    if not name:
        return None
    s = name.strip().replace("♯", "#").replace("♭", "b")
    m = re.fullmatch(r"(\d{1,2})\s*([ABab])", s)
    if m:
        num, minor = int(m.group(1)), m.group(2).upper() == "A"
        if not 1 <= num <= 12:
            return None
        pc = (CAMELOT_MINOR if minor else CAMELOT_MAJOR).index(num)
        return num, minor, PITCH_NAMES[pc] + ("m" if minor else "")
    m = re.fullmatch(r"([A-Ga-g])([#b]?)\s*(m|min|minor|maj|major)?", s)
    if m:
        pc = NOTE[m.group(1).upper()] + {"#": 1, "b": -1, "": 0}[m.group(2)]
        pc %= 12
        minor = (m.group(3) or "").lower() in ("m", "min", "minor")
        num = (CAMELOT_MINOR if minor else CAMELOT_MAJOR)[pc]
        return num, minor, PITCH_NAMES[pc] + ("m" if minor else "")
    return None


class RekordboxLibrary:
    """Background poller for the newest rekordbox history entry."""

    def __init__(self, poll_seconds: float = 2.0, max_age_minutes: float = 20.0):
        self.poll = poll_seconds
        self.max_age = dt.timedelta(minutes=max_age_minutes)
        self.track = None          # dict with title, artist, bpm, key, camelot, minor, since
        self.ok = False
        self.error = ""
        self._stop = threading.Event()
        try:
            import pyrekordbox  # noqa: F401
        except Exception:
            self.error = "pyrekordbox not installed"
            print("[library] pyrekordbox not installed - key/BPM come from the audio only")
            return
        threading.Thread(target=self._run, daemon=True, name="rekordbox-db").start()

    def stop(self):
        self._stop.set()

    def current(self):
        """The newest history track if it is recent enough to be what's playing."""
        t = self.track
        if t is None:
            return None
        if dt.datetime.now() - t["played_at"] > self.max_age:
            return None
        return t

    def _open(self):
        warnings.filterwarnings("ignore")
        logging.getLogger("pyrekordbox").setLevel(logging.ERROR)
        from pyrekordbox import MasterDatabase
        db = MasterDatabase()
        # some libraries contain titles with broken UTF-8, which would make every query
        # on that track fail - decode leniently instead
        raw = db.session.connection().connection.dbapi_connection
        raw.text_factory = lambda b: b.decode("utf-8", "replace")
        return db

    def _run(self):
        from pyrekordbox.masterdb import models as M
        db = None
        while not self._stop.is_set():
            try:
                if db is None:
                    db = self._open()
                    self.ok = True
                    self.error = ""
                    print("[library] reading the playing track from rekordbox's history")
                db.session.rollback()  # end the old read transaction so we see new rows
                h = (db.session.query(M.DjmdSongHistory)
                     .order_by(M.DjmdSongHistory.created_at.desc()).first())
                c = h.Content if h is not None else None
                if c is not None:
                    key_name = c.Key.ScaleName if c.Key is not None else None
                    parsed = parse_key(key_name)
                    played_at = h.created_at
                    if isinstance(played_at, str):
                        played_at = dt.datetime.fromisoformat(played_at)
                    new = {
                        "id": c.ID,
                        "title": c.Title or "",
                        "artist": getattr(c, "ArtistName", "") or "",
                        "genre": getattr(c, "GenreName", "") or "",
                        "bpm": (c.BPM or 0) / 100.0 or None,
                        "key_raw": key_name,
                        "camelot": parsed[0] if parsed else None,
                        "minor": parsed[1] if parsed else None,
                        "key": parsed[2] if parsed else None,
                        "played_at": played_at.replace(tzinfo=None),
                    }
                    if self.track is None or self.track["id"] != new["id"] or self.track["played_at"] != new["played_at"]:
                        print(f"[library] now playing: {new['artist']} - {new['title']}  "
                              f"({new['bpm']} BPM, {key_name})")
                        self.track = new
            except Exception as e:
                self.ok = False
                self.error = f"{type(e).__name__}: {e}"[:120]
                print(f"[library] cannot read rekordbox library: {self.error}; retrying in 10 s")
                try:
                    if db is not None:
                        db.close()
                except Exception:
                    pass
                db = None
                self._stop.wait(10)
                continue
            self._stop.wait(self.poll)

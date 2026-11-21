"""Audio capture (WASAPI loopback / input) and real-time music analysis.

Everything here runs in a background thread. The renderer reads a snapshot
of `Analyzer.state` once per frame.
"""
from __future__ import annotations

import threading
import time
import warnings

import numpy as np

warnings.filterwarnings("ignore", module="soundcard")
import soundcard as sc  # noqa: E402

SR = 48000
HOP = 512                      # ~10.7 ms analysis step
FPS = SR / HOP                 # 93.75 analysis frames per second
NFFT = 2048
NCHROMA = 8192
NSPEC = 128                    # spectrum bins sent to the shaders
NWAVE = 256

PITCH_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
# Camelot wheel numbers indexed by pitch class (C=0)
CAMELOT_MAJOR = [8, 3, 10, 5, 12, 7, 2, 9, 4, 11, 6, 1]
CAMELOT_MINOR = [5, 12, 7, 2, 9, 4, 11, 6, 1, 8, 3, 10]
# Krumhansl-Kessler key profiles
KK_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KK_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


# --------------------------------------------------------------------------- devices
def list_devices():
    """All capture endpoints, including loopback of every output device."""
    try:
        return list(sc.all_microphones(include_loopback=True))
    except Exception:
        return []


def device_label(dev) -> str:
    return f"{dev.name}{' [loopback]' if getattr(dev, 'isloopback', False) else ''}"


def probe_devices(devices, seconds=0.35):
    """Return [(rms, dev)] measured over a short window, loudest first."""
    results = []
    for dev in devices:
        try:
            with dev.recorder(samplerate=SR, blocksize=HOP) as rec:
                data = rec.record(numframes=int(SR * seconds))
            rms = float(np.sqrt(np.mean(np.square(data)))) if data.size else 0.0
        except Exception:
            rms = -1.0
        results.append((rms, dev))
    results.sort(key=lambda x: x[0], reverse=True)
    return results


def pick_device(query: str | None = None, exclude=()):
    """Choose a capture device.

    With a query: first device whose name contains it (case-insensitive).
    Otherwise: the loudest device right now; ties are broken in favour of the
    DJ controller (DDJ / rekordbox / Pioneer) and then the default speaker loopback.
    Devices whose label is in `exclude` (e.g. locked by another app) are skipped.
    """
    devices = list_devices()
    if not devices:
        raise RuntimeError("No audio capture devices found")
    usable = [d for d in devices if device_label(d) not in exclude]
    devices = usable or devices
    if query:
        q = query.lower()
        for dev in devices:
            if q in device_label(dev).lower():
                return dev
        print(f"[audio] no device matches '{query}', auto-selecting")

    def preference(dev):
        n = dev.name.lower()
        score = 0
        if any(k in n for k in ("ddj", "rekordbox", "pioneer", "alphatheta", "xdj", "djm")):
            score += 2
        try:
            if dev.isloopback and dev.name == sc.default_speaker().name:
                score += 1
        except Exception:
            pass
        return score

    probed = probe_devices(devices)
    loud = [(r, d) for r, d in probed if r > 1e-4]
    if loud:
        best = max(loud, key=lambda x: (x[0] > loud[0][0] * 0.5, preference(x[1]), x[0]))
        return best[1]
    return max(devices, key=preference)


# --------------------------------------------------------------------------- helpers
class EMA:
    def __init__(self, seconds: float, value: float = 0.0):
        self.a = 1.0 - np.exp(-1.0 / (seconds * FPS))
        self.v = value

    def __call__(self, x):
        self.v += (x - self.v) * self.a
        return self.v


def _ar(v, target, attack, release):
    """Attack/release smoothing."""
    k = attack if target > v else release
    return v + (target - v) * k


# --------------------------------------------------------------------------- analyzer
class Analyzer:
    """Captures audio and derives tempo, beat phase, kicks, bands, key and song section."""

    BANDS = {  # Hz
        "sub": (25, 60), "bass": (60, 160), "lowmid": (160, 600),
        "mid": (600, 3000), "high": (3000, 16000),
    }

    def __init__(self, device_query: str | None = None, sensitivity: float = 1.0):
        self.clock = time.perf_counter
        self.device_query = device_query
        self.sensitivity = sensitivity
        self.lock = threading.Lock()
        self._stop = threading.Event()
        self._switch_to = None
        self.device = None
        self.external_clock = None  # set to LinkClock by main if available
        self.busy = {}              # device label -> time it failed to open
        self.status = ""            # problem with the audio source, shown in the HUD

        self.freqs = np.fft.rfftfreq(NFFT, 1.0 / SR)
        self.window = np.hanning(NFFT).astype(np.float32)
        self.band_idx = {k: (self.freqs >= lo) & (self.freqs < hi) for k, (lo, hi) in self.BANDS.items()}
        self.kick_idx = (self.freqs >= 35) & (self.freqs < 150)

        # log-spaced spectrum bins for shaders
        edges = np.geomspace(30, 16000, NSPEC + 1)
        self.spec_bins = [(max(1, int(np.searchsorted(self.freqs, edges[i]))),
                           max(int(np.searchsorted(self.freqs, edges[i])) + 1, int(np.searchsorted(self.freqs, edges[i + 1]))))
                          for i in range(NSPEC)]
        self.spec_lo = np.array([b[0] for b in self.spec_bins])
        self.spec_hi = np.array([b[1] for b in self.spec_bins])

        # chroma mapping
        cf = np.fft.rfftfreq(NCHROMA, 1.0 / SR)
        valid = (cf >= 55) & (cf <= 2000)
        self.chroma_bins = np.where(valid)[0]
        self.chroma_pc = (np.round(12 * np.log2(cf[valid] / 440.0)).astype(int) + 9) % 12
        self.chroma_window = np.hanning(NCHROMA).astype(np.float32)

        self.buf = np.zeros(NCHROMA, np.float32)
        self.prev_log = np.zeros(len(self.freqs), np.float32)
        self.prev_kick_mag = np.zeros(int(self.kick_idx.sum()), np.float32)

        # onset envelopes for tempo (8 s history)
        self.hist_len = int(8 * FPS)
        self.onset_hist = np.zeros(self.hist_len, np.float32)
        self.kick_hist = np.zeros(self.hist_len, np.float32)
        self.frame = 0

        # adaptive normalisation
        self.band_peak = {k: -40.0 for k in self.BANDS}
        self.band_val = {k: 0.0 for k in self.BANDS}
        self.spec_peak = np.full(NSPEC, -40.0, np.float32)
        self.spec_val = np.zeros(NSPEC, np.float32)
        self.level_peak = -40.0

        # kick detection
        self.kick_mean = EMA(1.0)
        self.kick_var = EMA(1.0, 1.0)
        self.kick_prev = [0.0, 0.0]
        self.last_kick_t = 0.0
        self.kick_env = 0.0
        self.kick_count = 0
        self.kicks_recent = EMA(2.0)
        self.kick_peak_ref = 1e-4
        self.pulse_slow = EMA(1.5)
        self.pulse_quick = EMA(0.3)
        self.pulse_ref = 1e-4
        self.pulse_ratio = 0.0
        self.pulse_quick_ratio = 0.0

        # tempo / phase
        self.bpm = 124.0
        self.bpm_conf = 0.0
        self.beat = 0.0             # continuous beat counter
        self.beat_time = self.clock()
        self.bar_offset = 0         # which beat index is a downbeat (user resync)
        self._cand_bpm = None
        self._cand_count = 0

        # sections
        self.bass_fast = EMA(1.2, -60)
        self.bass_quick = EMA(0.12, -60)
        self.bass_ref = -30.0       # slowly decaying peak of bass_fast = "full groove" level
        self.level_fast = EMA(0.8, -60)
        self.high_fast = EMA(1.0, -60)
        self.high_slow = EMA(5.0, -60)
        self.onset_fast = EMA(1.5)
        self.onset_slow = EMA(8.0)
        self.section = "idle"
        self.section_since = self.clock()
        self.low_bass_time = 0.0
        self.return_time = 0.0
        self.drop_env = 0.0
        self.drop_count = 0
        self.build = 0.0
        self.energy = 0.0
        self.silence_time = 10.0

        # key
        self.chroma = np.zeros(12, np.float32)
        self.key_name = "--"
        self.camelot = 8
        self.camelot_str = "--"
        self.minor = True

        self.centroid = 0.0
        self.wave = np.zeros(NWAVE, np.float32)
        self.state = self._snapshot()

    # ------------------------------------------------------------------ control
    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True, name="audio")
        self.thread.start()

    def stop(self):
        self._stop.set()

    def next_device(self):
        devices = list_devices()
        if not devices:
            return
        names = [device_label(d) for d in devices]
        cur = device_label(self.device) if self.device else None
        i = (names.index(cur) + 1) % len(devices) if cur in names else 0
        self._switch_to = devices[i]

    def resync_downbeat(self):
        """User pressed the downbeat key: make the nearest beat beat 1 of a bar/phrase."""
        with self.lock:
            b = int(round(self._beat_now()))
            self.bar_offset = b % 32

    def _beat_now(self, t=None):
        t = self.clock() if t is None else t
        return self.beat + (t - self.beat_time) * self.bpm / 60.0

    # ------------------------------------------------------------------ thread
    def _run_file(self, path):
        """Feed a WAV file in real time (testing without rekordbox). Loops forever."""
        import wave
        with wave.open(path, "rb") as w:
            ch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            raw = w.readframes(n)
        dt = {1: np.int8, 2: np.int16, 4: np.int32}[sw]
        x = np.frombuffer(raw, dt).astype(np.float32) / float(np.iinfo(dt).max)
        x = x.reshape(-1, ch).mean(axis=1)
        if sr != SR:
            x = np.interp(np.arange(0, len(x), sr / SR), np.arange(len(x)), x).astype(np.float32)
        self.device = type("FileDevice", (), {"name": f"file: {path}", "isloopback": False})()
        print(f"[audio] playing file into analyzer: {path}")
        t0 = time.perf_counter()
        i = 0
        while not self._stop.is_set():
            target = (time.perf_counter() - t0) * SR
            while i + HOP <= target and not self._stop.is_set():
                self._process(x[i % (len(x) - HOP):][:HOP] * self.sensitivity)
                i += HOP
            time.sleep(0.003)

    def _hunt(self, current):
        """Probe other sources; return one that is clearly playing audio (mics last)."""
        others = [d for d in list_devices() if device_label(d) != device_label(current)]
        probed = probe_devices(others, seconds=0.25)
        is_mic = lambda d: (not getattr(d, "isloopback", False)) and any(
            k in d.name.lower() for k in ("microphone", "mikrofon", "mic ", "headset", "webcam"))
        for want_mic in (False, True):
            for rms, d in probed:
                if is_mic(d) == want_mic and rms > (3e-3 if want_mic else 1e-3):
                    print(f"[audio] current source is silent - switching to {device_label(d)}")
                    return d
        return None

    def _run(self):
        if self.device_query and self.device_query.lower().endswith(".wav"):
            return self._run_file(self.device_query)
        last_hunt = time.perf_counter()
        while not self._stop.is_set():
            now = time.perf_counter()
            busy = {lbl for lbl, t in self.busy.items() if now - t < 30}
            dev = self._switch_to or self.device or pick_device(self.device_query, exclude=busy)
            manual = self._switch_to is not None
            self._switch_to = None
            self.device = dev
            print(f"[audio] listening to: {device_label(dev)}")
            try:
                with dev.recorder(samplerate=SR, blocksize=HOP) as rec:
                    while not self._stop.is_set() and self._switch_to is None:
                        # auto-hunt: if our source stays silent, look for one that carries music
                        if (not self.device_query and not manual and self.silence_time > 6
                                and time.perf_counter() - last_hunt > 8):
                            last_hunt = time.perf_counter()
                            alt = self._hunt(dev)
                            if alt is not None:
                                self._switch_to = alt
                                break
                        data = rec.record(numframes=HOP)
                        if data.ndim == 2:
                            mono = data.mean(axis=1)
                        else:
                            mono = data
                        self._process(mono.astype(np.float32) * self.sensitivity)
            except Exception as e:  # device unplugged, or locked by another app
                label = device_label(dev)
                self.busy[label] = time.perf_counter()
                if "8889000a" in str(e).lower():
                    # AUDCLNT_E_DEVICE_IN_USE: opened in exclusive mode (rekordbox does this
                    # with DJ controllers), so nobody else can record it
                    self.status = f"{dev.name} is locked by another app (rekordbox?)"
                    print(f"[audio] {label} is in exclusive use by another program "
                          f"(rekordbox's controller driver?) - trying another source")
                else:
                    self.status = f"{dev.name}: {e}"
                    print(f"[audio] device error on {label}: {e!r} - trying another source")
                self.device = None
                time.sleep(3.0 if self.device_query else 0.5)

    # ------------------------------------------------------------------ analysis
    def _process(self, x: np.ndarray):
        n = len(x)
        if n == 0:
            return
        now = self.clock()
        self.buf = np.roll(self.buf, -n)
        self.buf[-n:] = x[-NCHROMA:]
        self.frame += 1

        frame = self.buf[-NFFT:] * self.window
        mag = np.abs(np.fft.rfft(frame)) / (NFFT / 4)
        power = mag * mag

        # ---- loudness / silence
        rms = float(np.sqrt(np.mean(self.buf[-NFFT:] ** 2)) + 1e-9)
        level_db = 20 * np.log10(rms)
        silent = level_db < -62
        self.silence_time = self.silence_time + 1 / FPS if silent else 0.0
        if not silent and self.status:
            self.status = ""  # we're getting audio now - the earlier problem no longer matters

        # ---- bands (adaptive gain, 30 dB window under a decaying peak)
        bands_db = {}
        for k, idx in self.band_idx.items():
            db = 10 * np.log10(power[idx].mean() + 1e-12)
            bands_db[k] = db
            self.band_peak[k] = max(db, self.band_peak[k] - 2.0 / FPS, -70)
            norm = np.clip((db - (self.band_peak[k] - 30)) / 30, 0, 1) ** 1.5
            if silent:
                norm = 0.0
            self.band_val[k] = _ar(self.band_val[k], norm, 0.5, 0.12)

        self.level_peak = max(level_db, self.level_peak - 1.5 / FPS, -70)
        level = 0.0 if silent else float(np.clip((level_db - (self.level_peak - 24)) / 24, 0, 1))

        # ---- log spectrum for shaders
        cs = np.concatenate([[0.0], np.cumsum(power)])
        spec = (cs[self.spec_hi] - cs[self.spec_lo]) / np.maximum(self.spec_hi - self.spec_lo, 1)
        spec_db = 10 * np.log10(spec + 1e-12)
        self.spec_peak = np.maximum(spec_db, np.maximum(self.spec_peak - 3.0 / FPS, -75))
        target = np.clip((spec_db - (self.spec_peak - 36)) / 36, 0, 1)
        if silent:
            target[:] = 0
        k = np.where(target > self.spec_val, 0.6, 0.15)
        self.spec_val += (target - self.spec_val) * k

        # ---- spectral centroid (brightness)
        tot = power.sum() + 1e-12
        cen = float((power * self.freqs).sum() / tot)
        self.centroid = _ar(self.centroid, np.clip(np.log2(max(cen, 100) / 300) / 5, 0, 1), 0.05, 0.05)

        # ---- onset (spectral flux)
        logm = np.log1p(mag * 1000).astype(np.float32)
        diff = np.maximum(logm - self.prev_log, 0)
        self.prev_log = logm
        onset = float(diff.mean())
        # kick flux in the linear domain so that quiet noise (risers) can't fake kicks
        km = mag[self.kick_idx]
        kick_flux = float(np.maximum(km - self.prev_kick_mag, 0).sum()) * 10
        self.prev_kick_mag = km
        self.onset_hist[:-1] = self.onset_hist[1:]
        self.onset_hist[-1] = onset
        self.kick_hist[:-1] = self.kick_hist[1:]
        self.kick_hist[-1] = kick_flux

        # ---- pulse = how strongly a kick pattern is present (volume independent)
        pulse = self.pulse_slow(kick_flux)
        pq = self.pulse_quick(kick_flux)
        self.pulse_ref = max(pulse, self.pulse_ref * np.exp(-1.0 / (45 * FPS)), 1e-4)
        self.pulse_ratio = pulse / self.pulse_ref
        self.pulse_quick_ratio = pq / self.pulse_ref

        # ---- kick detection: local peak above adaptive threshold
        m = self.kick_mean(kick_flux)
        v = self.kick_var((kick_flux - m) ** 2)
        thr = m + 1.4 * np.sqrt(v) + 0.05
        p1, p2 = self.kick_prev
        kicked = False
        self._strong_kick = False
        if self.section not in ("breakdown", "buildup"):  # remember groove level through breakdowns
            self.kick_peak_ref = max(self.kick_peak_ref * np.exp(-1.0 / (20 * FPS)), 1e-4)
        if (p1 > thr and p1 >= kick_flux and p1 > p2 and p1 > 0.3 * self.kick_peak_ref
                and (now - self.last_kick_t) > 0.22 and not silent):
            kicked = True
            self._strong_kick = p1 > 0.5 * self.kick_peak_ref
            self.kick_peak_ref = max(self.kick_peak_ref, p1)
            self.last_kick_t = now
            self.kick_count += 1
            self.kick_env = 1.0
        self.kick_prev = [kick_flux, p1]
        self.kick_env *= np.exp(-1.0 / (0.16 * FPS))
        kick_rate = self.kicks_recent(1.0 if kicked else 0.0) * FPS  # kicks per second

        # ---- tempo + phase (every ~0.25 s)
        if self.frame % 24 == 0:
            self._update_tempo()
        self._advance_beat(now)

        # ---- key (every 4 frames)
        if self.frame % 4 == 0 and not silent:
            self._update_chroma()

        # ---- song structure
        self._update_section(now, bands_db, level_db, onset, kick_rate, silent)

        # ---- waveform for shaders
        w = self.buf[-NWAVE * 2::2]
        peak = np.abs(w).max()
        self.wave = w / max(peak, 0.02)

        snap = self._snapshot(level=level, kicked=kicked)
        with self.lock:
            self.state = snap

    def _update_tempo(self):
        if self.pulse_ratio < 0.5 or self.section in ("breakdown", "buildup", "idle"):
            return  # freewheel through breakdowns: keep the last good tempo & phase
        env = self.onset_hist + 0.7 * self.kick_hist
        env = env - env.mean()
        if np.abs(env).max() < 1e-4:
            self.bpm_conf *= 0.9
            return
        # autocorrelation via FFT
        n = len(env)
        f = np.fft.rfft(env, 2 * n)
        ac = np.fft.irfft(f * np.conj(f))[:n]
        ac /= ac[0] + 1e-9
        bpms = np.arange(70.0, 185.0, 0.1)
        lags = 60.0 * FPS / bpms
        score = np.zeros_like(bpms)
        for mult, wgt in ((1, 1.0), (2, 0.8), (4, 0.6), (8, 0.4)):
            l = lags * mult
            ok = l < n - 2
            li = l.astype(int)
            fr = l - li
            li = np.clip(li, 0, n - 2)
            val = ac[li] * (1 - fr) + ac[li + 1] * fr
            score += np.where(ok, val, 0) * wgt
        prior = np.exp(-0.5 * (np.log2(bpms / 126.0) / 0.55) ** 2)
        score = score * (0.5 + prior)
        i = int(np.argmax(score))
        cand = float(bpms[i])
        conf = float(np.clip(score[i] / 1.5, 0, 1))

        if abs(cand - self.bpm) / self.bpm < 0.025:
            self.bpm += (cand - self.bpm) * 0.25
            self._cand_count = 0
        else:
            if self._cand_bpm is not None and abs(cand - self._cand_bpm) / cand < 0.02:
                self._cand_count += 1
            else:
                self._cand_bpm, self._cand_count = cand, 1
            if self._cand_count >= (8 if self.bpm_conf > 0.3 else 2):
                self._rebase(self.bpm)
                self.bpm = cand
                self._cand_count = 0
        self.bpm_conf += (conf - self.bpm_conf) * 0.3

        # phase alignment: fold the onset envelope of the last ~4 s onto one beat
        lag = 60.0 * FPS / self.bpm
        span = int(4 * FPS)
        e = (self.kick_hist * 1.0 + self.onset_hist * 0.4)[-span:]
        t_idx = np.arange(span) - (span - 1)  # frames relative to now (<= 0)
        # account for the analysis window delay (centre of the FFT frame)
        delay_frames = (NFFT / 2) / HOP
        ph = ((t_idx - delay_frames) / lag) % 1.0
        nb = 32
        hist = np.bincount((ph * nb).astype(int) % nb, weights=e, minlength=nb)
        hist = np.convolve(np.r_[hist[-2:], hist, hist[:2]], [0.25, 0.5, 1, 0.5, 0.25], "same")[2:-2]
        best = int(np.argmax(hist))
        strength = hist[best] / (hist.mean() + 1e-9)
        if strength > 1.5:
            # beats happen where frame phase == best/nb; so at "now" the beat phase is (0 - best/nb)
            target_phase = (-(best + 0.5) / nb) % 1.0
            now = self.clock()
            cur = self._beat_now(now)
            err = ((target_phase - cur % 1.0 + 0.5) % 1.0) - 0.5
            self._rebase(self.bpm, now)
            self.beat += err * 0.35

    def _rebase(self, bpm, now=None):
        now = self.clock() if now is None else now
        self.beat = self.beat + (now - self.beat_time) * bpm / 60.0
        self.beat_time = now

    def _advance_beat(self, now):
        clk = self.external_clock
        if clk is not None and clk.active():
            b, bpm = clk.read()
            self.beat, self.bpm, self.beat_time, self.bpm_conf = b, bpm, now, 1.0
        else:
            self._rebase(self.bpm, now)

    def _update_chroma(self):
        x = self.buf * self.chroma_window
        mag = np.abs(np.fft.rfft(x))[self.chroma_bins]
        c = np.bincount(self.chroma_pc, weights=np.sqrt(mag), minlength=12).astype(np.float32)
        c /= c.sum() + 1e-9
        self.chroma += (c - self.chroma) * 0.006  # ~ 7 s memory
        if self.chroma.sum() < 1e-6:
            return
        best, best_r = None, -2
        cz = self.chroma - self.chroma.mean()
        for tonic in range(12):
            for minor, prof in ((False, KK_MAJOR), (True, KK_MINOR)):
                p = np.roll(prof, tonic)
                p = p - p.mean()
                r = float(np.dot(cz, p) / (np.linalg.norm(cz) * np.linalg.norm(p) + 1e-9))
                if r > best_r:
                    best_r, best = r, (tonic, minor)
        tonic, minor = best
        self.minor = minor
        self.camelot = (CAMELOT_MINOR if minor else CAMELOT_MAJOR)[tonic]
        self.camelot_str = f"{self.camelot}{'A' if minor else 'B'}"
        self.key_name = PITCH_NAMES[tonic] + ("m" if minor else "")

    def _update_section(self, now, bands_db, level_db, onset, kick_rate, silent):
        bass_db = 10 * np.log10(10 ** (bands_db["sub"] / 10) + 10 ** (bands_db["bass"] / 10))
        bf = self.bass_fast(bass_db)
        lf = self.level_fast(level_db)
        self.bass_ref = max(bf, self.bass_ref - 0.15 / FPS)  # decays 0.15 dB/s
        hf, hs = self.high_fast(bands_db["high"]), self.high_slow(bands_db["high"])
        of, os_ = self.onset_fast(onset), self.onset_slow(onset)

        bass_drop = self.bass_ref - bf            # dB below the groove level
        riser = np.clip((hf - hs) / 6.0, 0, 1)    # hi-freq energy rising
        density = np.clip((of / (os_ + 1e-6) - 1.0) / 1.0, 0, 1)
        e = 0.5 * np.clip(1.0 - bass_drop / 14.0, 0, 1) + 0.5 * np.clip(self.pulse_ratio, 0, 1)
        self.energy = _ar(self.energy, float(e) * (0 if silent else 1), 0.02, 0.01)

        bq = self.bass_quick(bass_db)
        prev = self.section
        if self.silence_time > 2.0:
            sec = "idle"
        elif (prev in ("breakdown", "buildup") and self.low_bass_time > 4.0 and self._strong_kick
              and self.bass_ref - bq < 8.0):
            # bass slams back in after a breakdown -> DROP (fast detector, ~0.1 s)
            sec = "drop"
            self.drop_env = 1.0
            self.drop_count += 1
            self.low_bass_time = 0.0
            self.build = 0.0
        elif bass_drop > 8.0 or self.pulse_ratio < 0.35:
            self.low_bass_time += 1 / FPS
            self.return_time = 0.0
            sec ="breakdown" if self.low_bass_time > 1.5 else prev
            if sec in ("breakdown", "buildup"):
                tension = max(riser, density * 0.8)
                self.build = _ar(self.build, tension, 0.03, 0.01)
                sec = "buildup" if self.build > 0.45 else "breakdown"
        else:
            back = self.pulse_ratio > 0.55 and bass_drop < 6.0
            self.return_time = self.return_time + 1 / FPS if (back and prev in ("breakdown", "buildup")) else 0.0
            if prev in ("breakdown", "buildup") and self.low_bass_time > 4.0 and self.return_time < 2.0:
                sec = prev  # wait a moment for the kick that marks the drop
            elif prev == "drop" and now - self.section_since < 30:
                sec = "drop"
            elif self.pulse_ratio > 0.55 and bass_drop < 6.0:
                sec = "groove"
            else:
                sec = prev if prev != "idle" else "groove"
            if sec not in ("breakdown", "buildup") and self.pulse_ratio > 0.55 and bass_drop < 6.0:
                self.low_bass_time = 0.0
            self.build = _ar(self.build, 0.0, 0.05, 0.05)
        if prev == "idle" and sec != "idle":
            self.bass_ref = bf  # new session: reset groove reference
        self.drop_env *= np.exp(-1.0 / (6.0 * FPS))
        if sec != prev:
            self.section = sec
            self.section_since = now

    def _snapshot(self, level=0.0, kicked=False):
        return {
            "t": self.clock(),
            "beat": self.beat, "beat_time": self.beat_time, "bpm": self.bpm,
            "bpm_conf": self.bpm_conf, "bar_offset": self.bar_offset,
            "kick": self.kick_env, "kick_count": self.kick_count, "kicked": kicked,
            "bands": dict(self.band_val), "level": level,
            "spec": self.spec_val.copy(), "wave": self.wave.copy(),
            "centroid": self.centroid, "energy": self.energy, "build": self.build,
            "drop": self.drop_env, "drop_count": self.drop_count,
            "section": self.section, "section_since": self.section_since,
            "camelot": self.camelot, "camelot_str": self.camelot_str,
            "key": self.key_name, "minor": self.minor,
            "device": device_label(self.device) if self.device else "--",
            "status": self.status,
            "link": bool(self.external_clock and self.external_clock.active()),
        }

    def snapshot(self):
        with self.lock:
            return self.state


# --------------------------------------------------------------------------- Ableton Link
class LinkClock:
    """Optional tempo/beat source from Ableton Link (rekordbox: LINK button)."""

    def __init__(self):
        self._beat = 0.0
        self._bpm = 120.0
        self._t = 0.0
        self._peers = 0
        self.ok = False
        try:
            import aalink  # noqa: F401
            threading.Thread(target=self._run, daemon=True, name="link").start()
            self.ok = True
        except Exception as e:
            print(f"[link] Ableton Link unavailable: {e!r}")

    def _run(self):
        import asyncio
        import aalink

        async def main():
            link = aalink.Link(120)
            link.quantum = 4
            link.enabled = True
            while True:
                self._beat, self._bpm, self._peers = link.beat, link.tempo, link.num_peers
                self._t = time.perf_counter()
                await asyncio.sleep(0.005)

        try:
            asyncio.run(main())
        except Exception as e:
            print(f"[link] stopped: {e!r}")
            self._peers = 0

    def active(self):
        return self._peers > 0

    def read(self):
        dt = time.perf_counter() - self._t
        return self._beat + dt * self._bpm / 60.0, self._bpm

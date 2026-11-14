"""French voice lines ("La patate ...") + pop sounds, mixed onto the merge timeline.

Voices come from Google Translate's French TTS (via gTTS) and are cached.
Each tier is pitch-shifted with ffmpeg: small potatoes squeak, big ones rumble.
Drop your own recordings in the voice folder as `<tier>_<name>.wav`/`.mp3`
(e.g. `9_Royale.mp3`) to use them instead of the generated ones.
"""
import os
import subprocess
import unicodedata
import wave

import numpy as np

from .characters import CHARACTERS, MAX_TIER

SR = 44100


def _slug(text):
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return "".join(c if c.isalnum() else "_" for c in s).strip("_")


def _decode(path, filters=None):
    cmd = ["ffmpeg", "-v", "error", "-i", path]
    if filters:
        cmd += ["-af", filters]
    cmd += ["-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def _source_rate(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                          "stream=sample_rate", "-of", "csv=p=0", path],
                         check=True, capture_output=True, text=True).stdout.strip()
    return int(out or 24000)


def _custom_recording(ch, voice_dir):
    for ext in (".wav", ".mp3", ".m4a"):
        p = os.path.join(voice_dir, f"{ch.tier}_{_slug(ch.name)}{ext}")
        if os.path.exists(p):
            return p
    return None


def voice_clip(ch, voice_dir):
    """Mono float32 clip of 'La patate <name>' at this tier's pitch."""
    os.makedirs(voice_dir, exist_ok=True)
    custom = _custom_recording(ch, voice_dir)
    if custom:
        clip = _decode(custom)
    else:
        src = os.path.join(voice_dir, f"tts_{_slug(ch.line)}.mp3")
        if not os.path.exists(src):
            from gtts import gTTS
            gTTS(ch.line, lang="fr").save(src)
        sr = _source_rate(src)
        p = ch.pitch
        tempo = min(2.0, max(0.5, p ** -0.55))   # big = slower and deeper
        trim = "silenceremove=start_periods=1:start_threshold=-50dB"
        chain = [trim, f"asetrate={int(sr * p)}", f"aresample={SR}", f"atempo={tempo:.4f}",
                 "areverse", trim, "areverse"]
        if ch.tier >= MAX_TIER - 1:
            chain.append("aecho=0.8:0.6:60|120:0.3|0.18")
        clip = _decode(src, ",".join(chain))
    peak = float(np.max(np.abs(clip))) or 1.0
    return clip / peak * 0.9


def pop_sound(tier):
    """Short synthetic 'bloop', lower and longer for bigger potatoes."""
    dur = 0.08 + 0.025 * tier
    t = np.arange(int(dur * SR)) / SR
    f0 = 1150 * 0.84 ** tier
    freq = f0 * (1.7 - 0.7 * t / dur)
    y = np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t * 26 / (1 + 0.15 * tier))
    click = int(0.004 * SR)
    y[:click] += np.random.default_rng(tier).normal(0, 0.3, click) * np.linspace(1, 0, click)
    if tier >= 6:
        y += 0.8 * np.sin(2 * np.pi * 55 * t) * np.exp(-t * 7)
    return (y / np.max(np.abs(y)) * 0.8).astype(np.float32)


def drop_sound():
    """Soft 'plop' when the player lets go of a potato."""
    t = np.arange(int(0.07 * SR)) / SR
    y = np.sin(2 * np.pi * np.cumsum(420 - 2500 * t) / SR) * np.exp(-t * 55)
    return (y / np.max(np.abs(y)) * 0.8).astype(np.float32)


def build_track(events, duration, voice_dir, with_voice=True):
    """Mix voices + pops for all merge events; returns stereo int16 samples."""
    n = int((duration + 1.0) * SR)
    track = np.zeros(n, dtype=np.float32)

    def add(clip, t, gain):
        i = int(t * SR)
        if i >= n:
            return
        j = min(n, i + len(clip))
        track[i:j] += clip[: j - i] * gain

    voices = {ch.tier: voice_clip(ch, voice_dir) for ch in CHARACTERS} if with_voice else {}
    pops = {ch.tier: pop_sound(ch.tier) for ch in CHARACTERS}
    last_t, last_tier, last_len = -9.0, 0, 0.0
    plop = drop_sound()
    for e in events:
        if e.kind == "drop":
            add(plop, e.t, 0.18)
            continue
        if e.kind != "merge":
            continue
        add(pops[e.tier], e.t, 0.35 + 0.03 * e.tier)
        if not with_voice:
            continue
        # Avoid a wall of overlapping voices: skip a line while the previous one
        # is still mostly playing, unless this potato is bigger (chains build up).
        if e.t - last_t < 0.6 * last_len and e.tier <= last_tier:
            continue
        clip = voices[e.tier]
        add(clip, e.t + 0.02, 1.0 if e.tier < MAX_TIER else 1.25)
        last_t, last_tier, last_len = e.t, e.tier, len(clip) / SR

    peak = float(np.max(np.abs(track))) or 1.0
    track = np.tanh(track / peak * 1.6) / np.tanh(1.6) * 0.92
    track = track[: int(duration * SR)]
    stereo = np.repeat((track * 32767).astype(np.int16)[:, None], 2, axis=1)
    return stereo


def write_wav(path, stereo):
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo.tobytes())

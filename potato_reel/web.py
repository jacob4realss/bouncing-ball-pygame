"""Build the playable browser version: one self-contained HTML file with the
potato sprites (WebP) and pitched French voice lines (MP3) embedded.

    python -m potato_reel.web            # writes output/potato_game.html
"""
import base64
import io
import json
import os
import subprocess
import sys

import numpy as np

from .audio import SR, voice_clip
from .characters import CHARACTERS, HALF, render_sprite

TEMPLATE = os.path.join(os.path.dirname(__file__), "web_template.html")


def _webp_uri(img):
    buf = io.BytesIO()
    img.save(buf, "WEBP", quality=88, method=6)
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()


def _mp3_uri(clip):
    pcm = np.asarray(clip, dtype=np.float32).tobytes()
    mp3 = subprocess.run(["ffmpeg", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-",
                          "-b:a", "64k", "-f", "mp3", "-"], input=pcm, check=True,
                         capture_output=True).stdout
    return "data:audio/mpeg;base64," + base64.b64encode(mp3).decode()


def build(out="output/potato_game.html", voice_dir="output/voices",
          hook="Attends la dernière patate 👀", teaser=None):
    chars = []
    for ch in CHARACTERS:
        chars.append({
            "tier": ch.tier, "name": ch.name, "line": ch.line, "radius": ch.radius,
            "points": ch.points, "skin": list(ch.skin),
            "sprite": _webp_uri(render_sprite(ch)),
            "voice": _mp3_uri(voice_clip(ch, voice_dir)),
        })
    silence = _mp3_uri(np.zeros(int(SR * 0.3), dtype=np.float32))
    data = {"characters": chars, "half": HALF, "hook": hook, "silence": silence,
            "teaser": teaser or f"NOUVEAU : {CHARACTERS[-1].line}"}
    html = open(TEMPLATE, encoding="utf-8").read().replace("__POTATO_DATA__", json.dumps(data))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    return out


if __name__ == "__main__":
    print(build(*sys.argv[1:2]))

"""Reel cover image (1080x1920), in the same style as the video.

    python -m potato_reel.thumbnail            # writes output/thumbnail.png

Key content stays inside the middle 1080x1440 so the profile-grid crop keeps it.
"""
import math
import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from PIL import Image, ImageDraw, ImageFilter

from .characters import CHARACTERS, render_sprite
from .physics import Arena, H, W
from .render import YELLOW, _eyes_emoji, _pil_font, _text_img, build_background


def _glow(size, color, radius):
    g = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(g).ellipse([size / 2 - radius, size / 2 - radius, size / 2 + radius, size / 2 + radius],
                              fill=color)
    return g.filter(ImageFilter.GaussianBlur(radius * 0.45))


def build(out="output/thumbnail.png", hook="Attends la dernière patate", teaser=None):
    arena = Arena()
    img = build_background(arena)
    last = CHARACTERS[-1]
    teaser = teaser or f"NOUVEAU : {last.line}"

    # the last potato, big and glowing, in the middle of the ring
    cx, cy = arena.cx, arena.cy + 150
    g = _glow(1100, (255, 214, 90, 120), 330)
    img.alpha_composite(g, (int(cx - 550), int(cy - 550)))
    rng = random.Random(3)
    d = ImageDraw.Draw(img)
    for _ in range(46):                                   # sparkles
        a, rr = rng.uniform(0, 2 * math.pi), rng.uniform(250, 430)
        x, y, s = cx + rr * math.cos(a), cy + rr * math.sin(a) * 0.9, rng.uniform(3, 9)
        d.ellipse([x - s, y - s, x + s, y + s], fill=(255, 236, 150, rng.randint(140, 255)))
    big = render_sprite(last, radius=250)
    img.alpha_composite(big, (int(cx - big.width / 2), int(cy - big.height / 2)))

    # the smaller ones around it
    spots = [(250, 880, 62, -12), (835, 850, 72, 10), (215, 1270, 84, 8), (868, 1290, 96, -8)]
    for ch, (x, y, r, tilt) in zip(CHARACTERS[:-1], spots):
        spr = render_sprite(ch, radius=r).rotate(tilt, resample=Image.BICUBIC)
        img.alpha_composite(spr, (int(x - spr.width / 2), int(y - spr.height / 2)))

    # hook box, like the video, but bigger
    d = ImageDraw.Draw(img)
    box = (60, 262, 1020, 396)
    d.rounded_rectangle(box, radius=28, fill=(255, 255, 255, 255))
    eyes = _eyes_emoji(76)
    size = 84
    while size > 40:
        font = _pil_font(size)
        if font.getlength(hook) + 18 + eyes.width <= box[2] - box[0] - 60:
            break
        size -= 2
    tw = font.getlength(hook)
    x0 = W / 2 - (tw + 18 + eyes.width) / 2
    ym = (box[1] + box[3]) / 2
    d.text((x0, ym), hook, font=font, fill=(12, 12, 12), anchor="lm")
    img.alpha_composite(eyes, (int(x0 + tw + 18), int(ym - eyes.height / 2)))
    t = _text_img(teaser, 74, YELLOW + (255,), stroke=6)
    while t.width > W - 60:
        t = t.resize((int(t.width * 0.95), int(t.height * 0.95)), Image.LANCZOS)
    img.alpha_composite(t, ((W - t.width) // 2, 452 - t.height // 2))

    # the ladder, smallest to biggest, with arrows
    n = len(CHARACTERS)
    step = 190
    xs = [W / 2 + (i - (n - 1) / 2) * step for i in range(n)]
    y = 1610
    for i, ch in enumerate(CHARACTERS):
        icon = render_sprite(ch, radius=46 + 6 * i)
        img.alpha_composite(icon, (int(xs[i] - icon.width / 2), int(y - icon.height / 2 + 10 - 4 * i)))
        if i < n - 1:
            ax = (xs[i] + xs[i + 1]) / 2 + 6
            d.polygon([(ax - 14, y - 16), (ax + 14, y), (ax - 14, y + 16)], fill=(247, 229, 104, 255))

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    img.convert("RGB").save(out, quality=95)
    return out


if __name__ == "__main__":
    print(build(*sys.argv[1:2]))

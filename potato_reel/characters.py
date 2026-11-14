"""The potato cast: one character per merge tier, drawn procedurally with Pillow.

Each tier is bigger than the last, and its voice line ("La patate <name>") is
pitched deeper. Edit CAST to rename, recolour or reorder characters; the
drawing for each `style` lives in the `_draw_<style>` functions below.
"""
import colorsys
import math
import random
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageChops, ImageDraw

SS = 4          # supersampling factor for smooth edges
HALF = 1.9      # sprite canvas half-size, in body radii (room for hats/horns)

# (display name, skin RGB, style key)
CAST = [
    ("Bébé",    (230, 186, 128), "bebe"),
    ("Douce",   (184,  92, 108), "douce"),
    ("Pirate",  (190, 138,  82), "pirate"),
    ("Chef",    (214, 164, 100), "chef"),
    ("Mamie",   (204, 156, 110), "mamie"),
    ("Rappeur", (168, 116,  66), "rappeur"),
    ("Ninja",   (194, 142,  82), "ninja"),
    ("Viking",  (198, 140,  84), "viking"),
    ("Royale",  (222, 172,  84), "royale"),
]
RADII = [34, 42, 52, 64, 79, 97, 119, 146, 180]
PITCH_SMALLEST, PITCH_BIGGEST = 1.45, 0.58


@dataclass(frozen=True)
class Character:
    tier: int        # 1-based
    name: str
    skin: tuple
    radius: int      # physics radius in px (1080x1920 video)
    pitch: float     # voice pitch factor (>1 higher, <1 deeper)
    points: int      # score for creating one
    style: str

    @property
    def line(self) -> str:
        return f"La patate {self.name}"


def _build_cast():
    n = len(CAST)
    out = []
    for i, (name, skin, style) in enumerate(CAST):
        pitch = PITCH_SMALLEST * (PITCH_BIGGEST / PITCH_SMALLEST) ** (i / (n - 1))
        out.append(Character(i + 1, name, skin, RADII[i], round(pitch, 3),
                             (i + 1) * (i + 2) // 2, style))
    return out


CHARACTERS = _build_cast()
MAX_TIER = len(CHARACTERS)

# ---------------------------------------------------------------- drawing kit
INK = (48, 30, 18, 255)
WHITE = (255, 255, 255, 255)
GOLD = (246, 196, 52, 255)
GOLD_DARK = (150, 100, 10, 255)


def _shade(rgb, k, a=255):
    return tuple(max(0, min(255, int(c * k))) for c in rgb[:3]) + (a,)


class Pen:
    """Draws in body-radius units: (0, 0) is the body centre, y points down."""

    def __init__(self, img, c, u):
        self.d = ImageDraw.Draw(img)
        self.c, self.u = c, u

    def p(self, x, y):
        return (self.c + x * self.u, self.c + y * self.u)

    def w(self, t):
        return max(1, int(round(t * self.u)))

    def _box(self, x, y, rx, ry):
        return [self.p(x - rx, y - ry), self.p(x + rx, y + ry)]

    def ellipse(self, x, y, rx, ry, fill=None, outline=None, width=0.0):
        self.d.ellipse(self._box(x, y, rx, ry), fill=fill, outline=outline,
                       width=self.w(width) if outline else 0)

    def circle(self, x, y, r, **kw):
        self.ellipse(x, y, r, r, **kw)

    def poly(self, pts, fill=None, outline=None, width=0.0):
        self.d.polygon([self.p(*q) for q in pts], fill=fill, outline=outline,
                       width=self.w(width) if outline else 0)

    def line(self, pts, fill, width):
        self.d.line([self.p(*q) for q in pts], fill=fill, width=self.w(width), joint="curve")
        for q in (pts[0], pts[-1]):          # round caps
            self.circle(*q, width / 2, fill=fill)

    def arc(self, x, y, rx, ry, start, end, fill, width):
        self.d.arc(self._box(x, y, rx, ry), start, end, fill=fill, width=self.w(width))

    def chord(self, x, y, rx, ry, start, end, fill=None, outline=None, width=0.0):
        self.d.chord(self._box(x, y, rx, ry), start, end, fill=fill, outline=outline,
                     width=self.w(width) if outline else 0)

    def rrect(self, x0, y0, x1, y1, rad, fill=None, outline=None, width=0.0):
        self.d.rounded_rectangle([self.p(x0, y0), self.p(x1, y1)], radius=rad * self.u,
                                 fill=fill, outline=outline,
                                 width=self.w(width) if outline else 0)


def _tapered(spine, w0, w1):
    """Polygon around a polyline whose width goes from w0 to w1."""
    left, right = [], []
    n = len(spine)
    for i, (x, y) in enumerate(spine):
        x0, y0 = spine[max(0, i - 1)]
        x1, y1 = spine[min(n - 1, i + 1)]
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy) or 1
        nx, ny = -dy / L, dx / L
        w = (w0 + (w1 - w0) * i / (n - 1)) / 2
        left.append((x + nx * w, y + ny * w))
        right.append((x - nx * w, y - ny * w))
    return left + right[::-1]


def _eye(pen, x, y, rx, ry, look=(0, 0), lid=0.0, skin=None, pupil=0.5):
    pen.ellipse(x, y, rx, ry, fill=WHITE, outline=INK, width=0.025)
    pr = min(rx, ry) * pupil
    px = x + look[0] * (rx - pr) * 0.85
    py = y + look[1] * (ry - pr) * 0.85
    pen.circle(px, py, pr, fill=(70, 44, 26, 255))
    pen.circle(px, py, pr * 0.6, fill=(10, 8, 8, 255))
    pen.circle(px - pr * 0.35, py - pr * 0.4, pr * 0.3, fill=WHITE)
    if lid > 0 and skin is not None:
        s = 2 * lid - 1
        a = math.degrees(math.asin(max(-1, min(1, s))))
        pen.chord(x, y, rx * 1.04, ry * 1.06, 180 - a, 360 + a,
                  fill=_shade(skin, 0.86), outline=INK, width=0.03)


def _angry_lid(pen, x, y, rx, ry, side, skin, depth=0.55):
    """Slanted lid: lower on the inner side (towards the nose)."""
    xi, xo = x - side * (rx + 0.03), x + side * (rx + 0.03)
    top = y - ry - 0.06
    pen.poly([(xo, top), (xi, top), (xi, y - ry + 2 * ry * depth), (xo, y - ry + 0.04)],
             fill=_shade(skin, 0.86))
    pen.line([(xi, y - ry + 2 * ry * depth), (xo, y - ry + 0.04)], INK, 0.045)


def _brow(pen, x, y, side, w, angle, thick, color=INK):
    """angle > 0 = angry (inner end low); angle < 0 = worried/raised."""
    xi, xo = x - side * w / 2, x + side * w / 2
    yi, yo = y + angle * w / 2, y - angle * w / 2
    pen.line([(xo, yo), (x, y - 0.03), (xi, yi)], color, thick)


def _eyes(pen, skin, rx=0.19, ry=0.21, y=-0.1, dx=0.31, look=(0, 0), lid=0.0):
    for side in (-1, 1):
        _eye(pen, side * dx, y, rx, ry, look, lid, skin)


def _blush(pen, alpha=90, y=0.2, dx=0.56):
    for side in (-1, 1):
        pen.ellipse(side * dx, y, 0.14, 0.08, fill=(240, 100, 100, alpha))


def _leaf(pen, base, ang, length, width, fill, outline):
    bx, by = base
    dx, dy = math.cos(ang), math.sin(ang)
    pts_l, pts_r = [], []
    for i in range(13):
        t = i / 12
        hw = width * math.sin(math.pi * t) / 2
        cx, cy = bx + dx * length * t, by + dy * length * t
        pts_l.append((cx - dy * hw, cy + dx * hw))
        pts_r.append((cx + dy * hw, cy - dx * hw))
    pen.poly(pts_l + pts_r[::-1], fill=fill, outline=outline, width=0.025)


# ---------------------------------------------------------------- characters
def _draw_bebe(pen, back, clip, skin):
    """clip draws are masked to the body; back draws go behind it."""
    _blush(clip, 110)
    _eyes(pen, skin, rx=0.25, ry=0.28, y=-0.08, dx=0.3, look=(0.1, 0.2))
    for side in (-1, 1):
        _brow(pen, side * 0.3, -0.48, side, 0.22, -0.3, 0.04)
    # hair curl
    spiral = [(0.06 + (0.02 + 0.07 * t / 7) * math.cos(t), -1.08 + (0.02 + 0.07 * t / 7) * math.sin(t))
              for t in np.linspace(0, 7, 30)]
    pen.line([(0.0, -0.94)] + spiral[::-1], (90, 55, 30, 255), 0.045)
    # pacifier
    pen.ellipse(0, 0.66, 0.13, 0.12, outline=(110, 190, 240, 255), width=0.06)
    pen.ellipse(0, 0.42, 0.28, 0.16, fill=(245, 150, 186, 255), outline=(170, 70, 110, 255), width=0.03)
    pen.circle(0, 0.42, 0.07, fill=(255, 220, 232, 255))


def _draw_douce(pen, back, clip, skin):
    _blush(clip, 140)
    for side in (-1, 1):
        pen.arc(side * 0.3, -0.06, 0.17, 0.14, 200, 340, INK, 0.06)
        _brow(pen, side * 0.3, -0.38, side, 0.2, -0.15, 0.04)
    pen.chord(0, 0.26, 0.3, 0.27, 0, 180, fill=(92, 22, 34, 255), outline=INK, width=0.03)
    pen.ellipse(0, 0.45, 0.14, 0.07, fill=(238, 112, 128, 255))
    green, dk = (90, 170, 70, 255), (40, 95, 35, 255)
    pen.line([(0, -0.93), (0.02, -1.12)], dk, 0.05)
    _leaf(pen, (0.02, -1.1), math.radians(-150), 0.32, 0.16, green, dk)
    _leaf(pen, (0.02, -1.1), math.radians(-35), 0.36, 0.18, green, dk)


def _draw_pirate(pen, back, clip, skin):
    red, red_dk = (205, 32, 44, 255), (110, 10, 20, 255)
    pen.chord(0, 0, 1.02, 1.03, 210, 330, fill=red, outline=red_dk, width=0.03)
    for (x, y) in [(-0.45, -0.72), (0.05, -0.86), (0.5, -0.68), (-0.08, -0.62), (0.28, -0.8)]:
        pen.circle(x, y, 0.05, fill=(255, 245, 235, 255))
    pen.poly([(0.84, -0.6), (1.28, -0.8), (1.22, -0.5)], fill=red, outline=red_dk, width=0.03)
    pen.poly([(0.84, -0.52), (1.24, -0.36), (1.08, -0.2)], fill=red, outline=red_dk, width=0.03)
    _eye(pen, -0.3, -0.1, 0.19, 0.2, look=(0.4, 0.1), skin=skin)
    _angry_lid(pen, -0.3, -0.1, 0.19, 0.2, -1, skin)
    _brow(pen, -0.3, -0.38, -1, 0.26, 0.5, 0.075)
    pen.line([(0.12, -0.24), (-0.5, -0.56)], (20, 20, 22, 255), 0.05)
    pen.line([(0.5, -0.04), (0.96, 0.14)], (20, 20, 22, 255), 0.05)
    pen.ellipse(0.32, -0.1, 0.22, 0.2, fill=(22, 22, 26, 255))
    pen.poly([(0.0, 0.38), (0.11, 0.385), (0.105, 0.48), (0.005, 0.475)], fill=GOLD, outline=GOLD_DARK, width=0.02)
    pen.line([(-0.26, 0.43), (-0.06, 0.37), (0.16, 0.4), (0.3, 0.33)], INK, 0.06)
    pen.ellipse(-0.97, 0.24, 0.08, 0.1, outline=GOLD, width=0.04)


def _draw_chef(pen, back, clip, skin):
    w, g = (252, 252, 252, 255), (170, 170, 182, 255)
    for (x, y, r) in [(-0.42, -1.32, 0.36), (0.42, -1.32, 0.36), (0, -1.5, 0.44)]:
        pen.circle(x, y, r, fill=w, outline=g, width=0.03)
    pen.poly([(-0.6, -1.34), (0.6, -1.34), (0.6, -0.92), (-0.6, -0.92)], fill=w)
    pen.rrect(-0.66, -1.08, 0.66, -0.8, 0.08, fill=w, outline=g, width=0.03)
    _eyes(pen, skin, look=(0, -0.2))
    for side in (-1, 1):
        _brow(pen, side * 0.31, -0.44, side, 0.22, -0.2, 0.06)
    pen.arc(0, 0.38, 0.16, 0.1, 20, 160, INK, 0.05)
    blk = (36, 26, 20, 255)
    for side in (-1, 1):
        pen.ellipse(side * 0.2, 0.25, 0.23, 0.1, fill=blk)
        pen.arc(side * 0.45, 0.17, 0.09, 0.09, 90 if side < 0 else -90, 330 if side < 0 else 150, blk, 0.06)
    pen.poly([(-0.36, 0.86), (0.36, 0.86), (0, 1.12)], fill=(215, 40, 50, 255), outline=(120, 15, 25, 255), width=0.03)


def _draw_mamie(pen, back, clip, skin):
    hair, hair_dk = (210, 210, 218, 255), (140, 140, 152, 255)
    pen.circle(0, -1.18, 0.3, fill=hair, outline=hair_dk, width=0.03)
    pen.arc(0, -1.18, 0.18, 0.16, 200, 340, hair_dk, 0.025)
    pen.chord(0, 0, 1.03, 1.04, 205, 335, fill=hair, outline=hair_dk, width=0.03)
    for side in (-1, 1):
        pen.line([(side * 0.55, -0.5), (side * 0.3, -0.8), (side * 0.02, -0.96)], (172, 172, 184, 255), 0.03)
    _blush(clip, 110, y=0.22)
    _eyes(pen, skin, rx=0.14, ry=0.15, y=-0.08, look=(0, 0.1), lid=0.25)
    frame = (70, 44, 100, 255)
    for side in (-1, 1):
        pen.circle(side * 0.31, -0.08, 0.25, outline=frame, width=0.055)
        pen.line([(side * 0.56, -0.12), (side * 0.92, -0.22)], frame, 0.04)
        _brow(pen, side * 0.31, -0.42, side, 0.2, -0.15, 0.035, (150, 150, 160, 255))
    pen.arc(0, -0.1, 0.07, 0.06, 200, 340, frame, 0.045)
    pen.arc(0, 0.3, 0.17, 0.12, 20, 160, (200, 55, 90, 255), 0.065)
    for a in np.linspace(48, 132, 10):
        r = math.radians(a)
        pen.circle(0.86 * math.cos(r), 0.86 * math.sin(r), 0.07, fill=(250, 248, 240, 255),
                   outline=(170, 165, 160, 255), width=0.015)


def _draw_rappeur(pen, back, clip, skin):
    red, red_dk = (222, 36, 46, 255), (120, 10, 20, 255)
    bp = Pen(back, pen.c, pen.u)
    bp.ellipse(-0.98, -0.66, 0.42, 0.12, fill=(196, 26, 36, 255), outline=red_dk, width=0.03)
    pen.chord(0, 0, 1.03, 1.04, 205, 335, fill=red, outline=red_dk, width=0.03)
    pen.chord(0, -0.44, 0.18, 0.16, 180, 360, fill=_shade(skin, 0.8), outline=red_dk, width=0.03)
    pen.line([(-0.16, -0.5), (0.16, -0.5)], (240, 240, 240, 255), 0.03)
    pen.circle(0, -1.02, 0.06, fill=red, outline=red_dk, width=0.02)
    for side in (-1, 1):
        _brow(pen, side * 0.31, -0.38, side, 0.24, 0.12, 0.06)
    lens = (16, 16, 22, 255)
    for side in (-1, 1):
        pen.ellipse(side * 0.31, -0.1, 0.27, 0.17, fill=lens, outline=(0, 0, 0, 255), width=0.03)
        pen.line([(side * 0.58, -0.14), (side * 0.93, -0.22)], lens, 0.04)
        pen.line([(side * 0.31 - 0.14, -0.17), (side * 0.31 - 0.06, -0.05)], (255, 255, 255, 170), 0.035)
    pen.line([(-0.06, -0.15), (0.06, -0.15)], lens, 0.05)
    pen.line([(-0.18, 0.38), (0.05, 0.4), (0.24, 0.31)], INK, 0.055)
    for a in np.linspace(40, 140, 15):
        r = math.radians(a)
        pen.ellipse(0.84 * math.cos(r), 0.84 * math.sin(r), 0.05, 0.035, fill=GOLD, outline=GOLD_DARK, width=0.015)
    pen.circle(0, 0.93, 0.14, fill=GOLD, outline=GOLD_DARK, width=0.025)
    pen.circle(0, 0.93, 0.08, outline=GOLD_DARK, width=0.02)


def _draw_ninja(pen, back, clip, skin):
    cloth, cloth_dk = (34, 36, 50, 255), (14, 14, 22, 255)
    cp = clip
    cp.poly([(-1.2, 0.14), (-0.5, 0.1), (0, 0.16), (0.5, 0.1), (1.2, 0.14), (1.2, 1.3), (-1.2, 1.3)], fill=cloth)
    for x in (-0.35, 0.0, 0.35):
        cp.line([(x - 0.05, 0.3), (x + 0.05, 0.7)], cloth_dk, 0.03)
    band, band_dk = (200, 34, 44, 255), (110, 12, 20, 255)
    cp.poly([(-1.2, -0.52), (1.2, -0.52), (1.2, -0.3), (-1.2, -0.3)], fill=band)
    pen.poly([(0.9, -0.5), (1.25, -0.66), (1.55, -0.56), (1.3, -0.5), (0.95, -0.34)], fill=band, outline=band_dk, width=0.025)
    pen.poly([(0.92, -0.42), (1.3, -0.32), (1.5, -0.12), (1.24, -0.2), (0.95, -0.32)], fill=band, outline=band_dk, width=0.025)
    pen.rrect(-0.2, -0.5, 0.2, -0.32, 0.03, fill=(178, 182, 194, 255), outline=(90, 92, 104, 255), width=0.025)
    pen.line([(-0.1, -0.41), (0.1, -0.41)], (90, 92, 104, 255), 0.025)
    for side in (-1, 1):
        _eye(pen, side * 0.3, -0.1, 0.18, 0.15, look=(0.25 * -side, 0.1), skin=skin)
        _angry_lid(pen, side * 0.3, -0.1, 0.18, 0.15, side, skin, 0.6)


def _horn(pen, side):
    spine = [(side * (0.62 + 0.75 * t ** 0.8), -0.74 - 0.2 * t - 0.55 * t ** 2) for t in np.linspace(0, 1, 16)]
    pen.poly(_tapered(spine, 0.26, 0.02), fill=(242, 230, 198, 255), outline=(150, 128, 92, 255), width=0.03)


def _draw_viking(pen, back, clip, skin):
    for side in (-1, 1):
        _horn(pen, side)
    metal, metal_dk = (152, 158, 170, 255), (80, 86, 98, 255)
    pen.chord(0, 0, 1.04, 1.05, 205, 335, fill=metal, outline=metal_dk, width=0.03)
    pen.line([(0, -1.0), (0, -0.48)], (122, 128, 140, 255), 0.11)
    pen.line([(-0.92, -0.45), (0.92, -0.45)], (122, 128, 140, 255), 0.13)
    for x in np.linspace(-0.75, 0.75, 6):
        pen.circle(x, -0.45, 0.03, fill=(210, 214, 222, 255))
    for side in (-1, 1):
        _eye(pen, side * 0.3, -0.12, 0.17, 0.18, look=(0, 0.1), skin=skin)
        _angry_lid(pen, side * 0.3, -0.12, 0.17, 0.18, side, skin, 0.5)
        _brow(pen, side * 0.3, -0.33, side, 0.3, 0.5, 0.09, (170, 80, 30, 255))
    beard, beard_dk = (218, 112, 40, 255), (140, 60, 20, 255)
    pen.poly([(-0.92, -0.02), (-0.82, 0.5), (-0.56, 0.95), (-0.26, 1.24), (0, 1.32), (0.26, 1.24),
              (0.56, 0.95), (0.82, 0.5), (0.92, -0.02), (0.62, 0.24), (0.3, 0.3), (0, 0.26),
              (-0.3, 0.3), (-0.62, 0.24)], fill=beard, outline=beard_dk, width=0.03)
    for x in (-0.5, -0.2, 0.2, 0.5):
        pen.line([(x, 0.55), (x * 0.9, 0.85)], beard_dk, 0.025)
    pen.ellipse(0, 0.5, 0.15, 0.07, fill=(70, 20, 15, 255))
    for side in (-1, 1):
        pen.poly([(0, 0.28), (side * 0.25, 0.26), (side * 0.48, 0.38), (side * 0.5, 0.52), (side * 0.2, 0.4)],
                 fill=(230, 125, 50, 255), outline=beard_dk, width=0.025)
        pen.rrect(side * 0.16 - 0.07, 1.04, side * 0.16 + 0.07, 1.14, 0.03, fill=GOLD, outline=GOLD_DARK, width=0.015)


def _draw_royale(pen, back, clip, skin):
    bp = Pen(back, pen.c, pen.u)
    bp.poly([(-0.95, 0.3), (0.95, 0.3), (1.1, 0.85), (0.7, 1.08), (0, 1.15), (-0.7, 1.08), (-1.1, 0.85)],
            fill=(170, 20, 44, 255), outline=(90, 8, 20, 255), width=0.03)
    pts = [(-0.62, -0.86), (-0.66, -1.38), (-0.38, -1.10), (-0.2, -1.48), (0, -1.16),
           (0.2, -1.48), (0.38, -1.10), (0.66, -1.38), (0.62, -0.86)]
    pen.poly(pts, fill=GOLD, outline=GOLD_DARK, width=0.03)
    pen.rrect(-0.66, -0.96, 0.66, -0.72, 0.05, fill=(232, 178, 36, 255), outline=GOLD_DARK, width=0.03)
    for (x, y) in [(-0.66, -1.38), (-0.2, -1.48), (0.2, -1.48), (0.66, -1.38)]:
        pen.circle(x, y, 0.06, fill=(255, 236, 150, 255), outline=GOLD_DARK, width=0.015)
    pen.circle(0, -0.84, 0.075, fill=(220, 30, 50, 255), outline=(110, 10, 20, 255), width=0.02)
    for side in (-1, 1):
        pen.circle(side * 0.4, -0.84, 0.06, fill=(50, 110, 230, 255), outline=(20, 40, 110, 255), width=0.02)
    _eyes(pen, skin, rx=0.18, ry=0.19, y=-0.1, look=(0.5, 0.15), lid=0.45)
    _brow(pen, -0.3, -0.42, -1, 0.24, -0.35, 0.06)
    _brow(pen, 0.31, -0.36, 1, 0.24, 0.1, 0.06)
    pen.circle(0.31, -0.1, 0.25, outline=GOLD, width=0.04)
    pen.line([(0.52, 0.02), (0.6, 0.3), (0.72, 0.55)], GOLD, 0.02)
    fur, fur_dk = (248, 248, 248, 255), (186, 186, 194, 255)
    xs = [-0.42, -0.28, -0.14, 0.14, 0.28, 0.42]
    for x in xs:
        pen.circle(x, 0.3 + 0.05 * abs(x), 0.12, fill=fur, outline=fur_dk, width=0.02)
    for x in xs:
        pen.circle(x, 0.3 + 0.05 * abs(x), 0.1, fill=fur)
    for a in np.linspace(35, 145, 12):
        r = math.radians(a)
        pen.circle(0.9 * math.cos(r), 0.9 * math.sin(r), 0.13, fill=fur)
    for a in np.linspace(45, 135, 5):
        r = math.radians(a)
        pen.ellipse(0.9 * math.cos(r), 0.9 * math.sin(r), 0.025, 0.05, fill=(20, 20, 20, 255))


_STYLES = {k[len("_draw_"):]: v for k, v in globals().items() if k.startswith("_draw_")}


# ---------------------------------------------------------------- body + sprite
def _body_outline(rng, n=180):
    ph = [rng.uniform(0, 2 * math.pi) for _ in range(3)]
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        rr = 0.965 + 0.025 * math.sin(2 * t + ph[0]) + 0.018 * math.sin(3 * t + ph[1]) + 0.01 * math.sin(5 * t + ph[2])
        pts.append((rr * math.cos(t), rr * math.sin(t) * 1.02))
    return pts


def render_sprite(ch: Character, radius=None) -> Image.Image:
    """Return an RGBA sprite whose body centre is the image centre."""
    r = radius or ch.radius
    u = r * SS
    size = int(2 * HALF * u)
    c = size / 2
    rng = random.Random(ch.tier * 7919)

    mask = Image.new("L", (size, size), 0)
    Pen(mask, c, u).poly(_body_outline(rng), fill=255)

    # Shaded skin (simple Lambert lighting from the top-left + soft highlight).
    ax = (np.arange(size) - c) / u
    nx, ny = np.meshgrid(ax, ax)
    nz = np.sqrt(np.clip(1 - nx ** 2 - ny ** 2, 0, 1))
    L = np.array([-0.45, -0.6, 0.66]); L /= np.linalg.norm(L)
    diff = np.clip(nx * L[0] + ny * L[1] + nz * L[2], 0, 1)
    shade = 0.42 + 0.7 * diff
    spec = diff ** 24 * 60
    rgb = np.clip(np.array(ch.skin)[None, None, :] * shade[..., None] + spec[..., None], 0, 255).astype(np.uint8)
    body = Image.fromarray(rgb, "RGB").convert("RGBA")
    body.putalpha(mask)

    back = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    clip = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    top = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    cpen = Pen(clip, c, u)
    for _ in range(16):     # potato eyes / spots
        a, d = rng.uniform(0, 2 * math.pi), math.sqrt(rng.uniform(0.02, 0.8))
        sx, sy, s = d * math.cos(a), d * math.sin(a), rng.uniform(0.03, 0.065)
        cpen.ellipse(sx, sy, s * 1.3, s, fill=_shade(ch.skin, 0.66, 210))
        cpen.ellipse(sx - s * 0.3, sy - s * 0.35, s * 0.5, s * 0.3, fill=_shade(ch.skin, 1.25, 120))

    pen = Pen(top, c, u)
    _STYLES[ch.style](pen, back, cpen, ch.skin)

    clip.putalpha(ImageChops.multiply(clip.getchannel("A"), mask))
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.alpha_composite(back)
    out.alpha_composite(body)
    out.alpha_composite(clip)
    Pen(out, c, u).poly(_body_outline(random.Random(ch.tier * 7919)), outline=_shade(ch.skin, 0.42), width=0.035)
    out.alpha_composite(top)
    final = int(round(size / SS))
    return out.resize((final, final), Image.LANCZOS)


def character_sheet(path, cols=3):
    """Save a labelled poster of the whole cast."""
    from PIL import ImageFont
    from .assets import font_path
    cell = 360
    rows = math.ceil(MAX_TIER / cols)
    sheet = Image.new("RGB", (cols * cell, rows * cell), (10, 10, 16))
    font = ImageFont.truetype(font_path(), 30) if font_path() else ImageFont.load_default()
    d = ImageDraw.Draw(sheet)
    for i, ch in enumerate(CHARACTERS):
        spr = render_sprite(ch, radius=85)
        x, y = (i % cols) * cell, (i // cols) * cell
        sheet.paste(spr, (x + (cell - spr.width) // 2, y + (cell - spr.height) // 2 - 22), spr)
        label = f"{ch.tier}. {ch.line}"
        tw = d.textlength(label, font=font)
        d.text((x + (cell - tw) / 2, y + cell - 52), label, font=font, fill=(245, 228, 110))
    sheet.save(path)
    return path

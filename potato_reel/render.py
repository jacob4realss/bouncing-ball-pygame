"""Draws the reel frame by frame with pygame and encodes it with ffmpeg."""
import colorsys
import math
import os
import random
import shutil
import subprocess
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import audio
from .assets import font_path
from .characters import CHARACTERS, MAX_TIER, render_sprite
from .bot import Bot, landing
from .physics import H, W, World

YELLOW = (247, 229, 104)


# ---------------------------------------------------------------- helpers
def _surf(img):
    img = img.convert("RGBA")
    return pygame.image.frombytes(img.tobytes(), img.size, "RGBA").convert_alpha()


def _pil_font(size):
    p = font_path()
    return ImageFont.truetype(p, size) if p else ImageFont.load_default()


def _pg_font(size):
    return pygame.font.Font(font_path(), size)


def _text_img(text, size, fill, stroke=0, stroke_fill=(0, 0, 0)):
    font = _pil_font(size)
    l, t, r, b = font.getbbox(text, stroke_width=stroke)
    img = Image.new("RGBA", (r - l + 8, b - t + 8), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((4 - l, 4 - t), text, font=font, fill=fill,
                             stroke_width=stroke, stroke_fill=stroke_fill)
    return img


def _eyes_emoji(h):
    """Hand-drawn 👀 (emoji fonts are rarely available to Pillow)."""
    s = 4
    ew, eh = int(h * 0.42) * s, int(h * 0.56) * s
    img = Image.new("RGBA", (ew * 2 + 6 * s, eh + 4 * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i in range(2):
        x0 = i * (ew + 4 * s) + 2 * s
        d.ellipse([x0, 2 * s, x0 + ew, 2 * s + eh], fill="white", outline="black", width=3 * s)
        pw, ph = ew * 0.48, eh * 0.46
        px, py = x0 + ew * 0.08, 2 * s + eh * 0.27
        d.ellipse([px, py, px + pw, py + ph], fill="black")
    return img.resize((img.width // s, img.height // s), Image.LANCZOS)


def build_background(arena):
    img = Image.new("RGBA", (W, H), (7, 7, 12, 255))
    k = 3                                    # supersample the ring for a smooth edge
    ring = Image.new("RGBA", (W * k, H * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(ring)
    width = 14
    Rr = arena.R + width / 2
    a_gap = math.radians(arena.open_deg)                  # ring is open at the top
    N = 1400
    pts = []
    for i in range(N + 1):
        t = i / N
        th = a_gap + t * (2 * math.pi - 2 * a_gap)        # counter-clockwise from the top
        hue = (1.0 - 0.92 * t) % 1.0                       # red > magenta > blue > green > orange
        col = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.85, 1.0)) + (255,)
        pts.append(((arena.cx - Rr * math.sin(th), arena.cy - Rr * math.cos(th)), col))
    hw = width * k / 2
    for i in range(N + 1):                   # overlapping dots give a clean round stroke
        (x, y), col = pts[i]
        d.ellipse([x * k - hw, y * k - hw, x * k + hw, y * k + hw], fill=col)
    for i in range(N):
        (x0, y0), col = pts[i]
        (x1, y1), _ = pts[i + 1]
        d.line([(x0 * k, y0 * k), (x1 * k, y1 * k)], fill=col, width=int(width * k))
    ring = ring.resize((W, H), Image.LANCZOS)

    glow = ring.filter(ImageFilter.GaussianBlur(18))
    img.alpha_composite(glow)
    img.alpha_composite(glow)
    img.alpha_composite(ring)
    return img


def build_overlay(hook, teaser):
    """Static captions drawn above the potatoes: the white hook box + yellow teaser."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    box = (78, 186, 1002, 292)
    d.rounded_rectangle(box, radius=22, fill=(255, 255, 255, 255))
    eyes = _eyes_emoji(58)
    room = box[2] - box[0] - 60
    size = 66
    while size > 30:
        font = _pil_font(size)
        if font.getlength(hook) + 16 + eyes.width <= room:
            break
        size -= 2
    tw = font.getlength(hook)
    total = tw + 16 + eyes.width
    x0 = (box[0] + box[2]) / 2 - total / 2
    cy = (box[1] + box[3]) / 2
    d.text((x0, cy), hook, font=font, fill=(12, 12, 12), anchor="lm")
    img.alpha_composite(eyes, (int(x0 + tw + 16), int(cy - eyes.height / 2)))
    if teaser:
        t = _text_img(teaser, 66, YELLOW + (255,), stroke=5)
        while t.width > W - 60:
            t = t.resize((int(t.width * 0.95), int(t.height * 0.95)), Image.LANCZOS)
        img.alpha_composite(t, ((W - t.width) // 2, 352 - t.height // 2))
    return img


# ---------------------------------------------------------------- effects
class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max", "col", "size")


class Effects:
    def __init__(self, rng):
        self.rng = rng
        self.particles, self.waves, self.labels = [], [], []
        self.shake = 0.0
        self.flash = 0.0

    def burst(self, x, y, tier, first, label_surf):
        ch = CHARACTERS[tier - 1]
        n = 10 + 3 * tier
        for _ in range(n):
            p = Particle()
            a = self.rng.uniform(0, 2 * math.pi)
            sp = self.rng.uniform(250, 650 + 60 * tier)
            p.x, p.y = x, y
            p.vx, p.vy = math.cos(a) * sp, math.sin(a) * sp - 200
            p.life = p.max = self.rng.uniform(0.35, 0.7)
            p.col = ch.skin if self.rng.random() < 0.6 else (255, 236, 150)
            p.size = self.rng.uniform(4, 7 + tier)
            self.particles.append(p)
        self.waves.append([x, y, ch.radius, 0.0])
        if tier >= 6:
            self.shake = max(self.shake, 4.0 * (tier - 5))
        if tier == MAX_TIER:
            self.flash = 1.0
            self.shake = max(self.shake, 26.0)
        if first and label_surf is not None:
            self.labels.append([x, y - ch.radius - 30, 0.0, label_surf])

    def update(self, dt):
        for p in self.particles:
            p.life -= dt
            p.vy += 1600 * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
        self.particles = [p for p in self.particles if p.life > 0]
        for w in self.waves:
            w[3] += dt
        self.waves = [w for w in self.waves if w[3] < 0.3]
        for lb in self.labels:
            lb[2] += dt
        self.labels = [lb for lb in self.labels if lb[2] < 1.4]
        self.shake *= 0.86
        self.flash = max(0.0, self.flash - dt * 1.6)

    def offset(self):
        if self.shake < 0.5:
            return 0, 0
        return (self.rng.uniform(-self.shake, self.shake), self.rng.uniform(-self.shake, self.shake))

    def draw_world(self, screen, ox, oy):
        for w in self.waves:
            x, y, r, t = w
            k = t / 0.3
            rad = int(r * (1.0 + 0.9 * k))
            size = rad * 2 + 8
            s = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(s, (255, 255, 255, int(220 * (1 - k))), (size // 2, size // 2), rad,
                               max(2, int(10 * (1 - k))))
            screen.blit(s, (x + ox - size / 2, y + oy - size / 2))
        for p in self.particles:
            k = p.life / p.max
            pygame.draw.circle(screen, p.col, (int(p.x + ox), int(p.y + oy)), max(1, int(p.size * k)))

    def draw_ui(self, screen):
        for x, y, t, surf in self.labels:
            k = min(1.0, t / 0.15)
            alpha = 255 if t < 1.0 else int(255 * (1 - (t - 1.0) / 0.4))
            sc = 0.6 + 0.4 * k + 0.08 * math.sin(min(1, t / 0.3) * math.pi)
            img = pygame.transform.rotozoom(surf, 0, sc)
            img.set_alpha(max(0, alpha))
            screen.blit(img, (x - img.get_width() / 2, y - 70 * min(1, t) - img.get_height() / 2))


# ---------------------------------------------------------------- renderer
class Renderer:
    def __init__(self, world, hook, teaser):
        pygame.init()
        pygame.display.set_mode((1, 1))
        self.world = world
        self.screen = pygame.Surface((W, H))
        self.bg = _surf(build_background(world.arena))
        self.overlay = _surf(build_overlay(hook, teaser))
        self.sprites = {c.tier: _surf(render_sprite(c)) for c in CHARACTERS}
        self.icons = {c.tier: _surf(render_sprite(c, radius=33)) for c in CHARACTERS}
        self.labels = {c.tier: _surf(_text_img(c.line + " !", 46, YELLOW + (255,), stroke=4))
                       for c in CHARACTERS}
        self.next_label = _surf(_text_img("SUIVANT", 34, (235, 235, 240, 255)))
        self.score_font = _pg_font(104)
        self.q_font = _pg_font(44)
        self.fx = Effects(random.Random(world.seed * 31 + 7))
        self.revealed = {}       # tier -> video time revealed
        self.shown_score = 0.0
        self.score_pop = 0.0
        self.flash = pygame.Surface((W, H))
        self.flash.fill((255, 255, 255))

    def on_events(self, events, vt):
        for e in events:
            if e.tier not in self.revealed:
                self.revealed[e.tier] = vt
            if e.kind == "merge":
                self.fx.burst(e.x, e.y, e.tier, e.first, self.labels[e.tier] if e.tier >= 3 else None)
                self.score_pop = 1.0

    def draw(self, vt, dt, aim=None):
        s = self.screen
        self.fx.update(dt)
        ox, oy = self.fx.offset()
        s.fill((7, 7, 12))
        s.blit(self.bg, (ox, oy))
        for b in sorted(self.world.bodies, key=lambda b: b.r):
            spr = self.sprites[b.tier]
            scale = b.r / b.rt
            if b.age < 0.22:
                scale *= 1.0 + 0.14 * math.sin(math.pi * b.age / 0.22)
            img = pygame.transform.rotozoom(spr, -math.degrees(b.ang), scale)
            s.blit(img, (b.x + ox - img.get_width() / 2, b.y + oy - img.get_height() / 2))
        self.fx.draw_world(s, ox, oy)
        if aim is not None:
            self._draw_dropper(aim, ox, oy)
        s.blit(self.overlay, (0, 0))
        self._draw_next()
        self._draw_score()
        self._draw_tiers(vt)
        self.fx.draw_ui(s)
        if self.fx.flash > 0:
            self.flash.set_alpha(int(200 * self.fx.flash ** 2))
            s.blit(self.flash, (0, 0))

    def _draw_dropper(self, aim, ox, oy):
        w = self.world
        if w.game_over or w.top_time is not None:
            return
        tier = w.current
        ch = CHARACTERS[tier - 1]
        lo, hi = w.arena.aim_range(ch.radius)
        x = max(lo, min(hi, aim))
        y = w.arena.drop_y
        land_y, _ = landing(w, x, ch.radius)
        for yy in range(int(y + ch.radius + 10), int(land_y), 26):      # dashed aim line
            pygame.draw.line(self.screen, (120, 120, 132), (x + ox, yy + oy), (x + ox, min(land_y, yy + 13) + oy), 4)
        if not w.can_drop:              # next potato pops in after the cooldown
            return
        since = w.time - w.ready_at
        scale = min(1.0, 0.4 + since / 0.12)
        img = pygame.transform.rotozoom(self.sprites[tier], 0, scale)
        self.screen.blit(img, (x + ox - img.get_width() / 2, y + oy - img.get_height() / 2))

    def _draw_next(self):
        w = self.world
        if w.top_time is not None:
            return
        cx, cy = 968, 505
        self.screen.blit(self.next_label, (cx - self.next_label.get_width() / 2, cy - 78))
        pygame.draw.circle(self.screen, (30, 30, 40), (cx, cy), 50)
        pygame.draw.circle(self.screen, (90, 90, 104), (cx, cy), 50, 3)
        img = self.icons[w.next]
        self.screen.blit(img, (cx - img.get_width() / 2, cy - img.get_height() / 2))

    def _draw_score(self):
        target = self.world.score
        self.shown_score += (target - self.shown_score) * 0.3
        if abs(target - self.shown_score) < 0.5:
            self.shown_score = target
        self.score_pop *= 0.82
        img = self.score_font.render(f"SCORE: {int(round(self.shown_score))}", True, (255, 255, 255))
        if self.score_pop > 0.02:
            img = pygame.transform.rotozoom(img, 0, 1 + 0.08 * self.score_pop)
        self.screen.blit(img, ((W - img.get_width()) / 2, 1562 - img.get_height() / 2))

    def _draw_tiers(self, vt):
        n = MAX_TIER
        step = 112
        x0 = W / 2 - step * (n - 1) / 2
        y = 1676
        for i, ch in enumerate(CHARACTERS):
            x = x0 + i * step
            t_rev = self.revealed.get(ch.tier)
            if t_rev is None:
                pygame.draw.circle(self.screen, (34, 34, 42), (int(x), y), 38)
                pygame.draw.circle(self.screen, (110, 110, 124), (int(x), y), 38, 3)
                q = self.q_font.render("?", True, (190, 190, 200))
                self.screen.blit(q, (x - q.get_width() / 2, y - q.get_height() / 2))
                continue
            age = vt - t_rev
            sc = 1.0 + 0.6 * math.exp(-age * 7) * (1 if age > 0 else 0)
            img = self.icons[ch.tier] if sc < 1.01 else pygame.transform.rotozoom(self.icons[ch.tier], 0, sc)
            self.screen.blit(img, (x - img.get_width() / 2, y - img.get_height() / 2))

    def frame_bytes(self):
        return pygame.image.tobytes(self.screen, "RGB")


def render_video(seed, out_path, fps=30, outro=4.5, max_len=150.0,
                 hook="Attends la dernière patate", teaser=None, voice=True,
                 voice_dir="output/voices", stills=(), preset="medium", log=print):
    """Play one game with the bot and render it. Returns a dict with timing info."""
    world = World(seed, fps)
    bot = Bot(world, seed)
    if teaser is None:
        teaser = f"NOUVEAU : {CHARACTERS[-1].line}"
    r = Renderer(world, hook, teaser)
    seen_events = 0

    out_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(out_dir, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="potato_reel_")
    silent = os.path.join(tmp, "video.mp4")
    enc = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", preset, "-crf", "19",
         "-pix_fmt", "yuv420p", silent], stdin=subprocess.PIPE)

    stills = sorted(stills)
    saved_stills = []
    dt = 1.0 / fps
    frame = 0
    end_at = None
    while True:
        vt = frame * dt
        if frame > 0:                      # same order as bot.play(), so seeds replay exactly
            bot.update(dt)
            world.advance_frame()
        new = world.events[seen_events:]
        seen_events = len(world.events)
        r.on_events(new, vt)
        r.draw(vt, dt, aim=bot.aim)
        enc.stdin.write(r.frame_bytes())
        while stills and vt >= stills[0]:
            p = os.path.join(out_dir, f"still_{stills.pop(0):05.1f}s.png")
            pygame.image.save(r.screen, p)
            saved_stills.append(p)
        if end_at is None and (world.top_time is not None or world.game_over):
            end_at = world.time + outro
        frame += 1
        if (end_at is not None and vt >= end_at) or vt >= max_len:
            break
        if frame % (fps * 10) == 0:
            log(f"  rendered {vt:5.1f}s  score {world.score}")
    enc.stdin.close()
    if enc.wait() != 0:
        raise RuntimeError("ffmpeg video encode failed")
    final_still = os.path.join(out_dir, "still_end.png")
    pygame.image.save(r.screen, final_still)
    saved_stills.append(final_still)

    duration = frame * dt
    wav = os.path.join(tmp, "audio.wav")
    audio.write_wav(wav, audio.build_track(world.events, duration, voice_dir, with_voice=voice))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", silent, "-i", wav, "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
                    out_path], check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    return {"duration": duration, "top_time": world.top_time, "score": world.score,
            "drops": world.drops, "won": world.top_time is not None,
            "merges": sum(e.kind == "merge" for e in world.events), "stills": saved_stills}

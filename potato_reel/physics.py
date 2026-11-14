"""Merge physics: circles fall through a funnel into a ring; equal tiers fuse.

Deterministic for a given seed and frame rate, so a run can be searched
headlessly for a good seed and then replayed identically while rendering.
"""
import math
import random
from dataclasses import dataclass, field

from .characters import CHARACTERS, MAX_TIER

W, H = 1080, 1920


@dataclass
class Arena:
    cx: float = 540.0
    cy: float = 975.0
    R: float = 490.0          # inner radius of the ring
    gap: float = 164.0        # funnel width

    @property
    def gap_y(self):          # y where the funnel walls meet the ring
        return self.cy - math.sqrt(self.R ** 2 - (self.gap / 2) ** 2)

    @property
    def corners(self):
        return [(self.cx - self.gap / 2, self.gap_y), (self.cx + self.gap / 2, self.gap_y)]


@dataclass
class Tuning:
    gravity: float = 2600.0
    restitution: float = 0.12
    friction: float = 0.25
    air: float = 0.9996
    correction: float = 0.85
    iterations: int = 2
    merge_slop: float = 1.5      # px of gap that still counts as touching
    min_merge_age: float = 0.06
    grow_time: float = 0.14      # s for a merged potato to reach full size
    magnet: float = 1000.0       # gentle pull between equal tiers (keeps merges flowing)
    magnet_range: float = 2.4    # in multiples of (ra + rb)
    spawn_max_tier: int = 4
    spawn_interval: tuple = (0.18, 0.26)
    first_spawn: float = 0.5
    match_bias: float = 0.65     # chance the next drop matches a small potato already inside
    spawn_weights: tuple = (2, 3, 3, 3)   # odds of dropping tier 1..spawn_max_tier


class Body:
    __slots__ = ("id", "x", "y", "vx", "vy", "r", "rt", "tier", "ang", "age", "alive", "contact")

    def __init__(self, bid, tier, x, y, vx=0.0, vy=0.0, r=None):
        self.id, self.tier = bid, tier
        self.rt = float(CHARACTERS[tier - 1].radius)
        self.r = self.rt if r is None else r
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.ang = 0.0
        self.age = 0.0
        self.alive = True
        self.contact = False


@dataclass
class Event:
    t: float
    kind: str          # "spawn" | "merge"
    tier: int
    x: float
    y: float
    first: bool = False   # first time this tier appears


@dataclass
class World:
    seed: int
    fps: int = 30
    arena: Arena = field(default_factory=Arena)
    tune: Tuning = field(default_factory=Tuning)

    def __post_init__(self):
        self.rng = random.Random(self.seed)
        self.substeps = max(1, round(240 / self.fps))
        self.dt = 1.0 / (self.fps * self.substeps)
        self.bodies = []
        self.events = []
        self.time = 0.0
        self.score = 0
        self.seen = set()
        self.top_time = None
        self.overflow = False
        self.next_spawn = self.tune.first_spawn
        self._next_id = 0

    # ------------------------------------------------------------ public
    def advance_frame(self):
        for _ in range(self.substeps):
            self._maybe_spawn()
            self._step(self.dt)
            self.time += self.dt

    @property
    def stopped_spawning(self):
        return self.top_time is not None

    # ------------------------------------------------------------ spawning
    def _new_body(self, tier, x, y, vx=0.0, vy=0.0, r=None):
        b = Body(self._next_id, tier, x, y, vx, vy, r)
        self._next_id += 1
        self.bodies.append(b)
        first = tier not in self.seen
        self.seen.add(tier)
        return b, first

    def _choose_tier(self):
        t = self.tune
        inside = sorted(b.tier for b in self.bodies
                        if b.alive and b.y > self.arena.gap_y and b.tier <= t.spawn_max_tier)
        if inside and self.rng.random() < t.match_bias:
            # favour the smallest potatoes so leftovers get cleaned up
            return inside[min(int(self.rng.expovariate(1.2)), len(inside) - 1)]
        return self.rng.choices(range(1, t.spawn_max_tier + 1), weights=t.spawn_weights[:t.spawn_max_tier])[0]

    def _maybe_spawn(self):
        if self.stopped_spawning or self.time < self.next_spawn:
            return
        if any(b.y - b.r < 60 for b in self.bodies):   # top of the funnel still busy
            return
        tier = self._choose_tier()
        r = CHARACTERS[tier - 1].radius
        slack = max(0.0, self.arena.gap / 2 - r) * 0.6
        x = self.arena.cx + self.rng.uniform(-slack, slack)
        _, first = self._new_body(tier, x, -r - 5, vy=650.0)
        self.events.append(Event(self.time, "spawn", tier, x, -r, first))
        self.next_spawn = self.time + self.rng.uniform(*self.tune.spawn_interval)

    # ------------------------------------------------------------ simulation
    def _step(self, dt):
        t, A = self.tune, self.arena
        g = t.gravity * dt
        for b in self.bodies:
            b.age += dt
            if b.r < b.rt:
                b.r = min(b.rt, b.r + b.rt * dt / t.grow_time)
            b.vy += g
            b.vx *= t.air
            b.vy *= t.air
            b.x += b.vx * dt
            b.y += b.vy * dt
            b.contact = False
        if t.magnet:
            self._magnet(dt)
        born = []
        for _ in range(t.iterations):
            self._collide(born)
            self._bounds()
        if born or any(not b.alive for b in self.bodies):
            self.bodies = [b for b in self.bodies if b.alive]
        for b in self.bodies:
            # Visual tilt only (not used by the physics): roll a little, then
            # settle back upright so faces stay readable.
            if b.contact:
                b.ang += 0.4 * b.vx / b.r * dt
            b.ang -= b.ang * 1.5 * dt
            if b.age > 1.5 and b.y < A.gap_y and not self.stopped_spawning:
                self.overflow = True

    def _magnet(self, dt):
        t, gy = self.tune, self.arena.gap_y
        B = self.bodies
        for i in range(len(B)):
            a = B[i]
            if a.y < gy or a.age < 0.3 or a.tier >= MAX_TIER:
                continue
            for j in range(i + 1, len(B)):
                b = B[j]
                if b.tier != a.tier or b.y < gy or b.age < 0.3:
                    continue
                dx, dy = b.x - a.x, b.y - a.y
                rng = t.magnet_range * (a.r + b.r)
                d = math.hypot(dx, dy)
                if d >= rng or d < 1e-6:
                    continue
                k = t.magnet * (1 - d / rng) * dt / d
                a.vx += dx * k; a.vy += dy * k
                b.vx -= dx * k; b.vy -= dy * k

    def _merge(self, a, b, born):
        a.alive = b.alive = False
        ma, mb = a.r * a.r, b.r * b.r
        m = ma + mb
        x, y = (a.x * ma + b.x * mb) / m, (a.y * ma + b.y * mb) / m
        vx, vy = (a.vx * ma + b.vx * mb) / m, (a.vy * ma + b.vy * mb) / m
        tier = a.tier + 1
        nb, first = self._new_body(tier, x, y, vx, vy, r=max(a.r, b.r))
        nb.ang = (a.ang + b.ang) / 2
        born.append(nb)
        self.score += CHARACTERS[tier - 1].points
        self.events.append(Event(self.time, "merge", tier, x, y, first))
        if tier == MAX_TIER and self.top_time is None:
            self.top_time = self.time

    def _collide(self, born):
        t = self.tune
        B = self.bodies
        n = len(B)
        for i in range(n):
            a = B[i]
            if not a.alive:
                continue
            for j in range(i + 1, n):
                b = B[j]
                if not b.alive:
                    continue
                rs = a.r + b.r
                dx = b.x - a.x
                if dx > rs or dx < -rs:
                    continue
                dy = b.y - a.y
                if dy > rs or dy < -rs:
                    continue
                d2 = dx * dx + dy * dy
                if (a.tier == b.tier and a.tier < MAX_TIER and a.age > t.min_merge_age
                        and b.age > t.min_merge_age and d2 < (rs + t.merge_slop) ** 2):
                    self._merge(a, b, born)
                    break
                if d2 >= rs * rs:
                    continue
                d = math.sqrt(d2) or 1e-6
                nx, ny = dx / d, dy / d
                ia, ib = 1.0 / (a.r * a.r), 1.0 / (b.r * b.r)
                s = ia + ib
                corr = (rs - d) * t.correction / s
                a.x -= nx * corr * ia; a.y -= ny * corr * ia
                b.x += nx * corr * ib; b.y += ny * corr * ib
                rvx, rvy = b.vx - a.vx, b.vy - a.vy
                vn = rvx * nx + rvy * ny
                if vn < 0:
                    jn = -(1 + t.restitution) * vn / s
                    vt = -rvx * ny + rvy * nx
                    jt = max(-t.friction * jn, min(t.friction * jn, -vt / s))
                    px, py = jn * nx - jt * ny, jn * ny + jt * nx
                    a.vx -= px * ia; a.vy -= py * ia
                    b.vx += px * ib; b.vy += py * ib
                a.contact = b.contact = True

    def _bounds(self):
        t, A = self.tune, self.arena
        half = A.gap / 2
        gy = A.gap_y
        for b in self.bodies:
            if not b.alive:
                continue
            dx, dy = b.x - A.cx, b.y - A.cy
            d = math.hypot(dx, dy) or 1e-6
            nx, ny = dx / d, dy / d
            in_opening = ny < 0 and abs(nx * A.R) < half
            if not in_opening:
                pen = d + b.r - A.R
                if pen > 0:
                    b.x -= nx * pen; b.y -= ny * pen
                    vn = b.vx * nx + b.vy * ny
                    if vn > 0:
                        b.vx -= (1 + t.restitution) * vn * nx
                        b.vy -= (1 + t.restitution) * vn * ny
                        b.vx *= 0.985
                    b.contact = True
            if b.y < gy:   # inside the funnel: vertical walls
                lo, hi = A.cx - half + b.r, A.cx + half - b.r
                if lo > hi:
                    b.x, b.vx = A.cx, 0.0
                elif b.x < lo:
                    b.x, b.vx = lo, abs(b.vx) * t.restitution
                elif b.x > hi:
                    b.x, b.vx = hi, -abs(b.vx) * t.restitution
            for (px, py) in A.corners:    # the two ends of the ring
                ex, ey = b.x - px, b.y - py
                e = math.hypot(ex, ey)
                if 1e-6 < e < b.r:
                    ux, uy = ex / e, ey / e
                    b.x += ux * (b.r - e); b.y += uy * (b.r - e)
                    vn = b.vx * ux + b.vy * uy
                    if vn < 0:
                        b.vx -= (1 + t.restitution) * vn * ux
                        b.vy -= (1 + t.restitution) * vn * uy


def simulate(seed, fps=30, max_time=90.0, tune=None):
    """Run headlessly; return (world, seconds until the last potato or None)."""
    w = World(seed, fps, tune=tune or Tuning())
    frames = int(max_time * fps)
    for _ in range(frames):
        w.advance_frame()
        if w.overflow or w.top_time is not None:
            break
    return w, w.top_time

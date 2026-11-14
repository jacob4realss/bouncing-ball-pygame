"""Merge-game physics: only the smallest potato is ever dropped, from above the
screen into an open ring. Two potatoes of the same kind that touch fuse into
the next, bigger one, so every other character is made inside the ring.

There are no hidden helpers: merges only happen when potatoes really touch,
and the game is lost if the pile stays above the rim. Deterministic for a
given seed, so a run can be searched headlessly and replayed while rendering.
"""
import math
import random
from dataclasses import dataclass, field

from .characters import CHARACTERS, MAX_TIER

W, H = 1080, 1920


@dataclass
class Arena:
    cx: float = 540.0
    cy: float = 1000.0
    R: float = 490.0          # inner radius of the ring
    open_deg: float = 42.0    # half-angle of the opening at the top

    @property
    def corners(self):
        a = math.radians(self.open_deg)
        dx, dy = self.R * math.sin(a), self.R * math.cos(a)
        return [(self.cx - dx, self.cy - dy), (self.cx + dx, self.cy - dy)]

    @property
    def rim_y(self):          # the "don't fill above this" line
        return self.corners[0][1]

    @property
    def drop_y(self):         # where the held potato hangs
        return self.rim_y - 100

    def aim_range(self, r):
        (lx, _), (rx, _) = self.corners
        return lx + r + 6, rx - r - 6


@dataclass
class Tuning:
    gravity: float = 3200.0
    restitution: float = 0.45    # bounciness of a hard hit
    bounce_min: float = 140.0    # px/s: softer contacts don't bounce (keeps piles calm)
    friction: float = 0.25
    air: float = 0.9996
    correction: float = 0.85
    iterations: int = 2
    merge_slop: float = 1.5      # px of gap that still counts as touching
    min_merge_age: float = 0.06
    grow_time: float = 0.14      # s for a merged potato to reach full size
    drop_speed: float = 700.0    # px/s downward when a potato enters at the top
    min_gap: float = 0.1         # s between two drops
    lose_time: float = 2.5       # s a potato may sit above the rim before game over


class Body:
    __slots__ = ("id", "x", "y", "vx", "vy", "r", "rt", "tier", "ang", "age", "alive",
                 "contact", "over")

    def __init__(self, bid, tier, x, y, vx=0.0, vy=0.0, r=None):
        self.id, self.tier = bid, tier
        self.rt = float(CHARACTERS[tier - 1].radius)
        self.r = self.rt if r is None else r
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.ang = 0.0
        self.age = 0.0
        self.alive = True
        self.contact = False
        self.over = 0.0


@dataclass
class Event:
    t: float
    kind: str          # "drop" | "merge"
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
        self.drops = 0
        self.seen = set()
        self.top_time = None
        self.game_over = False
        self.ready_at = 0.0
        self._next_id = 0

    # ------------------------------------------------------------ player API
    @property
    def can_drop(self):
        return not self.game_over and self.time >= self.ready_at

    def drop(self, x, vx=0.0):
        """Drop the smallest potato from above the screen at x (clamped to the opening)."""
        if not self.can_drop:
            return False
        r = CHARACTERS[0].radius
        lo, hi = self.arena.aim_range(r)
        x = max(lo, min(hi, x))
        _, first = self._new_body(1, x, -r - 10, vx=vx, vy=self.tune.drop_speed)
        self.events.append(Event(self.time, "drop", 1, x, -r, first))
        self.ready_at = self.time + self.tune.min_gap
        self.drops += 1
        return True

    def advance_frame(self):
        for _ in range(self.substeps):
            self._step(self.dt)
            self.time += self.dt

    # ------------------------------------------------------------ internals
    def _new_body(self, tier, x, y, vx=0.0, vy=0.0, r=None):
        b = Body(self._next_id, tier, x, y, vx, vy, r)
        self._next_id += 1
        self.bodies.append(b)
        first = tier not in self.seen
        self.seen.add(tier)
        return b, first

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
        born = []
        for _ in range(t.iterations):
            self._collide(born)
            self._bounds()
        if born or any(not b.alive for b in self.bodies):
            self.bodies = [b for b in self.bodies if b.alive]
        rim = A.rim_y
        for b in self.bodies:
            # Visual tilt only (not used by the physics): roll a little, then
            # settle back upright so faces stay readable.
            if b.contact:
                b.ang += 0.4 * b.vx / b.r * dt
            b.ang -= b.ang * 1.5 * dt
            if b.age > 1.0 and b.y - b.r < rim:
                b.over += dt
                if b.over > t.lose_time and self.top_time is None:
                    self.game_over = True
            else:
                b.over = 0.0

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
                    e = t.restitution if -vn > t.bounce_min else 0.0
                    jn = -(1 + e) * vn / s
                    vt = -rvx * ny + rvy * nx
                    jt = max(-t.friction * jn, min(t.friction * jn, -vt / s))
                    px, py = jn * nx - jt * ny, jn * ny + jt * nx
                    a.vx -= px * ia; a.vy -= py * ia
                    b.vx += px * ib; b.vy += py * ib
                a.contact = b.contact = True

    def _bounds(self):
        t, A = self.tune, self.arena
        cos_open = math.cos(math.radians(A.open_deg))
        for b in self.bodies:
            if not b.alive:
                continue
            dx, dy = b.x - A.cx, b.y - A.cy
            d = math.hypot(dx, dy) or 1e-6
            nx, ny = dx / d, dy / d
            if -ny < cos_open:            # facing the ring, not the opening
                pen = d + b.r - A.R
                if pen > 0:
                    b.x -= nx * pen; b.y -= ny * pen
                    vn = b.vx * nx + b.vy * ny
                    if vn > 0:
                        e = t.restitution if vn > t.bounce_min else 0.0
                        b.vx -= (1 + e) * vn * nx
                        b.vy -= (1 + e) * vn * ny
                        b.vx *= 0.985
                    b.contact = True
            for (px, py) in A.corners:    # the two ends of the ring
                ex, ey = b.x - px, b.y - py
                e = math.hypot(ex, ey)
                if 1e-6 < e < b.r:
                    ux, uy = ex / e, ey / e
                    b.x += ux * (b.r - e); b.y += uy * (b.r - e)
                    vn = b.vx * ux + b.vy * uy
                    if vn < 0:
                        e = t.restitution if -vn > t.bounce_min else 0.0
                        b.vx -= (1 + e) * vn * ux
                        b.vy -= (1 + e) * vn * uy
                    b.contact = True

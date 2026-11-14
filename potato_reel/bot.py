"""A player that aims like a person: it looks for a matching potato to land on,
slides the dropper over, hesitates a moment, and drops. It is good, not perfect."""
import math
import random

from .characters import CHARACTERS


def landing(world, x, r):
    """Where a potato of radius r dropped at x first touches something.
    Returns (y_center_at_contact, body_or_None)."""
    A = world.arena
    best_y, best_b = None, None
    for b in world.bodies:
        dx = abs(b.x - x)
        rs = r + b.r
        if dx < rs:
            y = b.y - math.sqrt(rs * rs - dx * dx)
            if best_y is None or y < best_y:
                best_y, best_b = y, b
    floor = A.cy + math.sqrt(max(0.0, (A.R - r) ** 2 - (x - A.cx) ** 2))
    if best_y is None or floor < best_y:
        return floor, None
    return best_y, best_b


def score_spot(world, x, tier):
    r = CHARACTERS[tier - 1].radius
    y, b = landing(world, x, r)
    s = y / 40.0                                   # lower is safer
    if b is None:
        s += 4
    elif b.tier == tier:
        s += 60                                    # direct merge
    else:
        diff = b.tier - tier
        s -= 6 * abs(diff) + (8 if diff < 0 else 0)   # don't bury small ones
        # a same-tier potato next to the landing spot may still get bumped into
        for o in world.bodies:
            if o.tier == tier and math.hypot(o.x - x, o.y - y) < (o.r + r) * 1.35:
                s += 18
                break
    if y - r < world.arena.rim_y + 40:
        s -= 80                                    # about to overflow
    return s


class Bot:
    def __init__(self, world, seed=0, skill=0.85):
        self.w = world
        self.rng = random.Random(seed * 7717 + 3)
        self.skill = skill
        self.aim = world.arena.cx
        self.target = None
        self.hold = 0.0

    def choose(self):
        w = self.w
        tier = w.current
        r = CHARACTERS[tier - 1].radius
        lo, hi = w.arena.aim_range(r)
        xs = [lo + (hi - lo) * i / 40 for i in range(41)]
        scored = [(score_spot(w, x, tier) + self.rng.gauss(0, 4), x) for x in xs]
        scored.sort(reverse=True)
        if self.rng.random() > self.skill:          # an imperfect, human choice
            pick = self.rng.choice(scored[:8])[1]
        else:
            pick = scored[0][1]
        return max(lo, min(hi, pick + self.rng.gauss(0, 5)))

    def update(self, dt):
        w = self.w
        if not w.can_drop:
            return
        if self.target is None:
            self.target = self.choose()
            self.hold = self.rng.uniform(0.12, 0.45)
        d = self.target - self.aim
        step = max(250.0, abs(d) * 9.0) * dt          # ease towards the target
        self.aim = self.target if abs(d) <= step else self.aim + math.copysign(step, d)
        if abs(self.target - self.aim) < 1.0:
            self.hold -= dt
            if self.hold <= 0:
                w.drop(self.aim)
                self.target = None


def play(seed, fps=30, max_time=150.0, tune=None):
    """Play headlessly; returns the finished world."""
    from .physics import World, Tuning
    w = World(seed, fps, tune=tune or Tuning())
    bot = Bot(w, seed)
    dt = 1.0 / fps
    for _ in range(int(max_time * fps)):
        bot.update(dt)
        w.advance_frame()
        if w.game_over or w.top_time is not None:
            break
    return w

"""Auto-dropper: Bébés rain in from the top at random spots and random times,
the way a player tapping quickly would drop them. Nothing is aimed; whether
two potatoes meet depends on how they bounce and roll."""
import random

from .characters import CHARACTERS


class Rain:
    def __init__(self, world, seed=0, rate=3.4):
        self.w = world
        self.rng = random.Random(seed * 7717 + 3)
        self.rate = rate                  # average drops per second
        self.x = world.arena.cx
        self.next_t = 0.25

    def update(self, dt):
        w = self.w
        if w.game_over or w.top_time is not None or w.time < self.next_t or not w.can_drop:
            return
        lo, hi = w.arena.aim_range(CHARACTERS[0].radius)
        if self.rng.random() < 0.3:       # jump somewhere new
            self.x = self.rng.uniform(lo, hi)
        else:                             # or drift, like a finger moving across the screen
            self.x = min(hi, max(lo, self.x + self.rng.gauss(0, 90)))
        w.drop(self.x, vx=self.rng.gauss(0, 110))
        gap = self.rng.expovariate(self.rate)
        if self.rng.random() < 0.08:      # the occasional pause
            gap += self.rng.uniform(0.4, 0.9)
        self.next_t = w.time + max(w.tune.min_gap, gap)


def play(seed, fps=30, max_time=200.0, tune=None, rate=3.4):
    """Play headlessly; returns the finished world."""
    from .physics import World, Tuning
    w = World(seed, fps, tune=tune or Tuning())
    rain = Rain(w, seed, rate)
    dt = 1.0 / fps
    for _ in range(int(max_time * fps)):
        rain.update(dt)
        w.advance_frame()
        if w.game_over or w.top_time is not None:
            break
    return w

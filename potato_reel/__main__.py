"""Make a potato-merge reel.

    python -m potato_reel                       # auto-pick a seed, render output/potato_reel.mp4
    python -m potato_reel --seed 12 --out my.mp4
    python -m potato_reel --characters          # just save the cast poster
"""
import argparse
import os
import time

from .bot import play


def find_seed(start, fps, lo, hi, tries=80):
    """First seed whose game reaches the last potato between lo and hi seconds."""
    for seed in range(start, start + tries):
        w = play(seed, fps, max_time=hi + 1)
        if w.top_time is not None and lo <= w.top_time <= hi:
            return seed, w.top_time
    raise SystemExit(f"No seed in {start}..{start + tries - 1} wins between {lo}s and {hi}s; "
                     f"widen --min-len/--max-len.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="output/potato_reel.mp4")
    ap.add_argument("--seed", type=int, help="fixed seed (default: search for one that fits the length)")
    ap.add_argument("--search-from", type=int, default=1)
    ap.add_argument("--min-len", type=float, default=40, help="earliest the last potato may appear (s)")
    ap.add_argument("--max-len", type=float, default=170, help="latest the last potato may appear (s)")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--hook", default="Attends la dernière patate")
    ap.add_argument("--teaser", default=None, help='yellow line (default "NOUVEAU : La patate <last>")')
    ap.add_argument("--no-voice", action="store_true")
    ap.add_argument("--voice-dir", default="output/voices")
    ap.add_argument("--stills", default="", help="comma-separated seconds to save PNG frames at")
    ap.add_argument("--preset", default="medium", help="x264 preset (ultrafast..slow)")
    ap.add_argument("--characters", action="store_true", help="save output/characters.png and exit")
    a = ap.parse_args()

    if a.characters:
        from .characters import character_sheet
        os.makedirs("output", exist_ok=True)
        print(character_sheet("output/characters.png"))
        return

    if a.seed is None:
        seed, top = find_seed(a.search_from, a.fps, a.min_len, a.max_len)
        print(f"seed {seed}: last potato at {top:.1f}s")
    else:
        seed = a.seed
    from .render import render_video
    t0 = time.time()
    stills = [float(s) for s in a.stills.split(",") if s.strip()]
    info = render_video(seed, a.out, fps=a.fps, hook=a.hook, teaser=a.teaser,
                        voice=not a.no_voice, voice_dir=a.voice_dir, stills=stills, preset=a.preset)
    print(f"wrote {a.out}: {info['duration']:.1f}s, {info['drops']} drops, {info['merges']} merges, score {info['score']}, "
          f"last potato at {info['top_time'] and round(info['top_time'], 1)}s "
          f"(rendered in {time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()

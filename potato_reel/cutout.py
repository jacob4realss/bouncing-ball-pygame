"""Cut a character picture out of a plain grey studio background and round its bottom.

    python -m potato_reel.cutout <folder of .png renders> <output folder>

Then convert/copy the results into art/ as <size>_<Name>.png or .webp.
"""
import sys, glob, os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
src, dst = sys.argv[1], sys.argv[2]
os.makedirs(dst, exist_ok=True)
for f in sorted(glob.glob(os.path.join(src, "*.png"))):
    im = Image.open(f).convert("RGB")
    w, h = im.size
    a = np.asarray(im).astype(np.float32)
    mx, mn = a.max(-1), a.min(-1)
    sat = mx - mn
    lum = a.mean(-1)
    def box(x, r=3):
        p = np.pad(x, r + 1, mode="edge").cumsum(0).cumsum(1)
        k = 2 * r + 1
        return (p[k:, k:] - p[:-k, k:] - p[k:, :-k] + p[:-k, :-k])[:x.shape[0], :x.shape[1]] / (k * k)
    m1 = box(lum); m2 = box(lum * lum)
    std = np.sqrt(np.clip(m2 - m1 * m1, 0, None))
    bgish = (sat < 22) & (lum > 95) & (lum < 215) & (std < 7)
    bgish = (sat < 24) & (lum > 90) & (lum < 220) & (std < 11)
    m = Image.fromarray((bgish * 255).astype(np.uint8))
    m = m.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))     # fill the grain speckles
    mask = m.point(lambda v: 255 if v > 128 else 0).convert("RGB")
    # keep only background regions connected to the top / sides
    for s in [(x, 1) for x in range(0, w, 20)] + [(1, y) for y in range(0, h, 15)] + [(w - 2, y) for y in range(0, h, 15)]:
        if mask.getpixel(s) == (255, 255, 255):
            ImageDraw.floodfill(mask, s, (128, 0, 0))
    bg = np.asarray(mask)[..., 1] == 0
    bg &= np.asarray(mask)[..., 0] == 128
    alpha = Image.fromarray(((~bg) * 255).astype(np.uint8))
    alpha = alpha.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(7))   # close tiny gaps, trim the halo
    # drop leftover specks: keep the component under the image centre
    keep = alpha.point(lambda v: 255 if v > 128 else 0).convert("RGB")
    ImageDraw.floodfill(keep, (w // 2, int(h * 0.55)), (100, 0, 0))
    alpha = np.where(np.asarray(keep)[..., 0] == 100, 255, 0).astype(np.uint8)
    alpha = np.asarray(Image.fromarray(alpha).filter(ImageFilter.GaussianBlur(1.3))).astype(np.float32)
    ys, xs = np.nonzero(alpha[: int(h * 0.5)] > 128)
    cx = int(np.median(xs)); top = int(ys.min())
    gy, gx = np.mgrid[0:h, 0:w]
    ry = (h - top) * 0.5; rx = ry * 1.12; cy = top + ry
    e = ((gx - cx) / rx) ** 2 + ((gy - cy) / ry) ** 2
    alpha *= np.clip((1.08 - e) / 0.08, 0, 1)
    out = im.convert("RGBA"); out.putalpha(Image.fromarray(alpha.astype(np.uint8)))
    out = out.crop(out.getchannel("A").getbbox())
    out.save(os.path.join(dst, os.path.basename(f)))
    print(os.path.basename(f), out.size)

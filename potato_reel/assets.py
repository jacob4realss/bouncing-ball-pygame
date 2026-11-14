"""Font lookup shared by the renderer and the character sheet."""
import os

_FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/inter/Inter-Black.otf",
    "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf",
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",          # macOS
    "/Library/Fonts/Arial Black.ttf",
    "C:/Windows/Fonts/ariblk.ttf",                                  # Windows
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]


def font_path():
    """Heavy font for captions; set POTATO_FONT to override. None = pygame default."""
    env = os.environ.get("POTATO_FONT")
    if env and os.path.exists(env):
        return env
    for p in _FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    return None

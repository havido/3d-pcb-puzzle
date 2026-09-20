#!/usr/bin/env python3
"""Generate the tiny rotated-text images Goose Doctor's ui.lua uses in place
of labels, for text whose content is fixed at build time.

Why this exists: LVGL labels can't rotate, but the goose plate holds the
badge rotated a quarter turn (app/CLAUDE.md), so every screen's art is drawn
portrait and rotated clockwise into the 320x240 framebuffer (see
goose/UI_NOTES.md "Rotated art"). Any text ui.lua draws needs the same
treatment. For a FIXED string (not a live value like the countdown) the
simplest fix is to render it once, offline, and ship it as an image:

  1. draw the string upright and horizontal (easy to read, like a normal
     label) with Pillow and a bundled DejaVu font,
  2. rotate that image clockwise with the exact transform badge.py's
     `img --rotate cw` uses (`Image.ROTATE_270`, i.e. 270 deg CCW = 90 deg
     CW), so it lands in framebuffer space already reading right-side up to
     a player looking at the mounted plate,
  3. write it straight to an indexed .bin in app/goose/img/, same format as
     the screen art (see badge.py's `_indexed_bin`).

Run whenever a string, font, size or colour changes:

  app/.venv/bin/python app/tools/make_text_art.py

then rebuild/push as usual. The countdown itself is NOT done this way --
its value changes at runtime, so ui.lua builds it out of seven-segment
`badge.ui.box` widgets instead (see ui.lua's segment-digit comment).
"""

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from badge import _indexed_bin  # reuse the exact indexed .bin writer

from PIL import Image, ImageDraw, ImageFont

FONT_REGULAR = TOOLS / "fonts" / "DejaVuSans.ttf"
FONT_BOLD = TOOLS / "fonts" / "DejaVuSans-Bold.ttf"
IMG_DIR = TOOLS.parent / "goose" / "img"

INK = (0x11, 0x11, 0x11, 255)      # matches ui.lua's INK, for text on the art's yellow/green
WHITE = (0xff, 0xff, 0xff, 255)    # for text on the red penalty flash
PAD = 4                             # transparent margin baked into the image, each side

# name -> (text, font, size, colour). Sizes are chosen so the rotated image
# fits the free background strip each is placed over -- see ui.lua for the
# exact x/y and UI_NOTES.md for how that strip was found.
STRINGS = {
    "stage_goal1": ("Reach the TAIL loop", FONT_BOLD, 20, INK),
    "stage_goal2": ("Now the BELLY loop", FONT_BOLD, 20, INK),
    "ouch": ("OUCH!", FONT_BOLD, 34, WHITE),
}


def render(text, font_path, size, color):
    font = ImageFont.truetype(str(font_path), size)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    x0, y0, x1, y1 = probe.textbbox((0, 0), text, font=font)
    w, h = x1 - x0, y1 - y0
    im = Image.new("RGBA", (w + 2 * PAD, h + 2 * PAD), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((PAD - x0, PAD - y0), text, font=font, fill=color)
    return im


def main():
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    for name, (text, font_path, size, color) in STRINGS.items():
        upright = render(text, font_path, size, color)
        rotated = upright.transpose(Image.ROTATE_270)   # same CW turn as badge.py img --rotate cw
        data = _indexed_bin(rotated, colors=4)
        out = IMG_DIR / f"{name}.bin"
        out.write_bytes(data)
        print(f"{name}: {text!r} {upright.size[0]}x{upright.size[1]} -> "
              f"rotated {rotated.size[0]}x{rotated.size[1]} -> {out} ({len(data)} B)")


if __name__ == "__main__":
    main()

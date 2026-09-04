"""Build-time assets: the app icon and the Microsoft Store tiles.

Run once:  python make_icon.py
Pillow is used here only. The app itself loads the finished PNG/ICO through
tkinter and runs on the standard library alone.
"""

import os

from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "sticky.ico")
PAPER = (255, 216, 102, 255)
SHADE = (232, 189, 74, 255)
FOLD = (247, 232, 178, 255)
LINE = (110, 92, 40, 255)
LIMB = (92, 76, 30, 255)


def render(size):
    """Draw at 8x and downsample, so the fold and the figure stay crisp.

    The icon is the mascot: a square face with arms and legs coming straight
    out of it - no body - standing in shoes at the bottom-left corner of a
    note, one arm reaching in behind it. Below 32px the limbs turn to mush, so
    those sizes keep only the shapes that still read: the sheet, the face, and
    two eyes.
    """
    s = size * 8
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # The sheet no longer fills the square: the figure needs the lower left.
    left, right = int(s * 0.360), int(s * 0.975)
    top, bottom = int(s * 0.105), int(s * 0.720)
    cut = int((right - left) * 0.32)
    stroke = max(1, s // 80)
    detailed = size >= 32

    face = s * 0.280
    half = face / 2.0
    ground = s * 0.945
    face_bottom = ground - s * 0.150
    face_top = face_bottom - face
    hx = left - face * 0.62

    def bone(points, width):
        d.line(points, fill=PAPER, width=width + max(2, int(s * 0.022)),
               joint="curve")
        d.line(points, fill=LIMB, width=width, joint="curve")

    if detailed:
        limb_w = max(2, int(s * 0.028))
        arm_y = face_top + face * 0.66
        # the arm that reaches in behind the sheet
        bone([(hx + half, arm_y), (left + s * 0.02, arm_y - s * 0.030),
              (left + s * 0.11, arm_y - s * 0.055)], limb_w)
        # the free arm
        bone([(hx - half, arm_y), (hx - half - s * 0.055, arm_y + s * 0.040),
              (hx - half - s * 0.085, arm_y + s * 0.090)], limb_w)
        # legs straight out of the bottom of the face, and a shoe on each
        for side in (-1, 1):
            leg_x = hx + side * face * 0.24
            toe = leg_x + side * s * 0.030
            bone([(leg_x, face_bottom), (leg_x, ground - s * 0.030)], limb_w)
            shoe = s * 0.042
            d.pieslice([min(leg_x, toe) - shoe, ground - s * 0.055,
                        max(leg_x, toe) + shoe, ground + s * 0.055],
                       start=180, end=360, fill=LIMB)

    # the face: a box, because he is a box man
    d.rectangle([hx - half, face_top, hx + half, face_bottom],
                fill=PAPER, outline=LIMB, width=max(2, int(s * 0.026)))
    eye_r = face * 0.130
    for side in (-1, 1):
        ex = hx + side * face * 0.215
        ey = face_top + face * 0.42
        d.ellipse([ex - eye_r, ey - eye_r, ex + eye_r, ey + eye_r], fill=LINE)

    # the sheet, drawn last so it covers the arm where it goes behind
    body = [(left, top), (right - cut, top), (right, top + cut),
            (right, bottom), (left, bottom)]
    d.polygon(body, fill=PAPER)
    d.line(body + [body[0]], fill=SHADE, width=stroke)
    # the corner peeled back off the pad
    d.polygon([(right - cut, top), (right, top + cut), (right - cut, top + cut)],
              fill=FOLD)
    d.line([(right - cut, top), (right - cut, top + cut), (right, top + cut)],
           fill=SHADE, width=stroke)

    if detailed:                 # ruled lines only where they can be seen
        width = max(1, s // 46)
        span = right - left
        for frac in (0.44, 0.66):
            y = top + (bottom - top) * frac
            d.line([(left + span * 0.16, y), (right - span * 0.16, y)],
                   fill=LINE, width=width)

    return img.resize((size, size), Image.LANCZOS)


# Microsoft Store / MSIX tiles. Transparent PNGs; the Store composites them
# on its own plate colour, so the glyph must not carry its own background.
STORE_TILES = {
    "Square44x44Logo.png": (44, 44),
    "Square71x71Logo.png": (71, 71),
    "Square150x150Logo.png": (150, 150),
    "Square310x310Logo.png": (310, 310),
    "Wide310x150Logo.png": (310, 150),
    "StoreLogo.png": (50, 50),
}


def store_tiles(out_dir):
    """Write every tile the Store manifest references."""
    os.makedirs(out_dir, exist_ok=True)
    for name, (tw, th) in STORE_TILES.items():
        glyph_size = int(min(tw, th) * 0.86)
        glyph = render(glyph_size)
        tile = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        tile.alpha_composite(glyph, ((tw - glyph_size) // 2, (th - glyph_size) // 2))
        tile.save(os.path.join(out_dir, name))
    return len(STORE_TILES)


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    sizes = (256, 128, 64, 48, 40, 32, 24, 20, 16)
    images = [render(n) for n in sizes]
    images[0].save(OUT, format="ICO", sizes=[(n, n) for n in sizes],
                   append_images=images[1:])
    print("wrote %s (%d bytes)" % (OUT, os.path.getsize(OUT)))
    tiles = os.path.join(os.path.dirname(os.path.abspath(__file__)), "packaging", "Images")
    print("wrote %d Store tiles in %s" % (store_tiles(tiles), tiles))


if __name__ == "__main__":
    main()

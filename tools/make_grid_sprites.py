# The things that cross the Grid room now and then: little light cycles side-on, and the big flying M. Flat colour, white
# outlines, a soft glow, like everything else out there. Drawn big and scaled down; each faces right, the launcher flips it.
import os
from PIL import Image, ImageDraw, ImageFilter
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace('\\', '/') + '/'

OUT = ROOT + 'app/src/main/assets/scenes/grid/'
SS = 4


def glowing(im, radius):
    """The picture over a blurred copy of itself."""
    im = im.resize((im.width // SS, im.height // SS), Image.LANCZOS)
    pad = radius * 3
    big = Image.new('RGBA', (im.width + pad * 2, im.height + pad * 2), (0, 0, 0, 0))
    big.alpha_composite(im, (pad, pad))
    halo = big.filter(ImageFilter.GaussianBlur(radius))
    out = Image.new('RGBA', big.size, (0, 0, 0, 0))
    out.alpha_composite(halo)
    out.alpha_composite(halo)
    out.alpha_composite(big)
    return out


def scaled(pts, x0, y0, k):
    return [(x0 + x * k, y0 + y * k) for x, y in pts]


def cycle(name, main, dark, trim):
    """Side on, and almost all black: the shape is told by a bright line round it and a coloured stripe."""
    W, H = 240 * SS, 110 * SS
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    k = SS * 1.0
    INK = (4, 6, 12, 255)

    def poly(pts, fill, line=None, w=2):
        p = scaled(pts, 0, 0, k)
        d.polygon(p, fill=fill)
        if line:
            d.line(p + [p[0]], fill=line, width=int(w * SS), joint='curve')

    def wheel(cx):
        r, rr = 30 * k, 21 * k
        cy = 76 * k
        d.ellipse((cx * k - r, cy - r, cx * k + r, cy + r), fill=INK, outline=main, width=int(3 * SS))
        d.ellipse((cx * k - rr, cy - rr, cx * k + rr, cy + rr), outline=trim, width=int(1.6 * SS))
    wheel(52)
    wheel(188)
    poly([(20, 52), (64, 22), (128, 12), (176, 24), (222, 56), (196, 70), (160, 58), (84, 58), (44, 70)], INK, main, 2.6)
    poly([(66, 26), (128, 16), (148, 24), (116, 40), (84, 42)], (10, 20, 40, 255), trim, 1.5)      # the canopy
    d.line(scaled([(44, 54), (88, 46), (160, 46), (206, 56)], 0, 0, k), fill=trim, width=int(2 * SS))
    glowing(im, 4).save(OUT + name + '.png')


def recognizer():
    """The M. Dark faces, drawn in hot lines, the way it looks hanging over the plain."""
    W, H = 320 * SS, 260 * SS
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    k = SS * 1.0
    FACE, FACE2, HOT, GOLD = (28, 6, 8, 255), (52, 10, 10, 255), (255, 64, 30, 255), (255, 190, 70, 255)

    def poly(pts, fill, line=HOT, w=2.6):
        p = scaled(pts, 0, 0, k)
        d.polygon(p, fill=fill)
        d.line(p + [p[0]], fill=line, width=int(w * SS), joint='curve')

    for flip in (False, True):
        m = (lambda x: 320 - x) if flip else (lambda x: x)
        poly([(m(16), 42), (m(70), 42), (m(70), 190), (m(42), 250), (m(16), 190)], FACE)
        poly([(m(70), 42), (m(100), 62), (m(100), 176), (m(70), 190)], FACE2)
        poly([(m(16), 190), (m(42), 250), (m(70), 190), (m(42), 206)], FACE2, GOLD, 2)
    poly([(10, 12), (310, 12), (292, 46), (28, 46)], FACE2)
    poly([(104, 4), (216, 4), (226, 26), (94, 26)], FACE, GOLD, 2)
    poly([(112, 46), (208, 46), (192, 112), (160, 134), (128, 112)], FACE2)
    poly([(124, 62), (196, 62), (188, 84), (132, 84)], (6, 2, 4, 255), GOLD, 2)
    d.line(scaled([(138, 73), (182, 73)], 0, 0, k), fill=GOLD, width=int(3 * SS))
    glowing(im, 6).save(OUT + 'recognizer.png')


cycle('cycle_blue', (90, 200, 255, 255), (6, 24, 90, 255), (200, 240, 255, 255))
cycle('cycle_yellow', (255, 176, 32, 255), (120, 70, 6, 255), (255, 232, 170, 255))
recognizer()
print({f: os.path.getsize(OUT + f) // 1024 for f in ('cycle_blue.png', 'cycle_yellow.png', 'recognizer.png')})

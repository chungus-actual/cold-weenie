# Cold Weenie's shelf plank and UI sounds. The banner and icon come from tools/make_brand.py. The rooms come from render/scene.py + tools/bake_room.py.
import math, wave
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace('\\', '/') + '/'

rng = np.random.default_rng(1994)
ROOT = ROOT + 'app/src/main/'
A, R = ROOT + 'assets/', ROOT + 'res/drawable-xhdpi/'
W, H = 1920, 1080


def lerp(a, b, t):
    t = np.clip(t, 0, 1)[..., None]
    return np.array(a, np.float32) * (1 - t) + np.array(b, np.float32) * t


# --- shelf plank with a lit front edge, plus its cast shadow
ph = 34
sa = np.zeros((ph + 40, W, 4), np.uint8)
plank = np.zeros((ph, W, 3), np.float32)
plank[:] = lerp((44, 20, 74), (20, 8, 38), np.linspace(0, 1, ph)[:, None])
plank[:2] = (230, 96, 226)
plank[2:9] = (84, 38, 128)
sa[:ph, :, :3] = np.clip(plank, 0, 255)
sa[:ph, :, 3] = 255
sa[ph:, :, 3] = (np.linspace(1, 0, 40) ** 2 * 190)[:, None]
Image.fromarray(sa, 'RGBA').save(A + 'shelf.png')

# --- the channel selector: 2x tile size. Faceplate, then the knob on its own layer so it can turn under a fixed highlight.
SS = 4
DW, DH = 408 * SS, 524 * SS
CX, CY = DW / 2, DH * .405
yy, xx = np.mgrid[0:DH, 0:DW].astype(np.float32)
dx, dy = xx - CX, yy - CY
rad = np.hypot(dx, dy)
ang = np.arctan2(dy, dx)
R_DISC, R_KNOB = DW * .445, DW * .285


def smooth(edge, soft, v):
    return np.clip((edge + soft - v) / (2 * soft), 0, 1)


def over(base, rgb, a):
    a = a[..., None]
    base[..., :3] = base[..., :3] * (1 - a) + rgb * a
    base[..., 3] = base[..., 3] * (1 - a[..., 0]) + 255 * a[..., 0]


# brushed aluminium plate, lit from above, with a rounded beveled edge
plate = np.zeros((DH, DW, 4), np.float32)
ex = np.minimum(xx, DW - 1 - xx)
ey = np.minimum(yy, DH - 1 - yy)
cr = 26 * SS
corner = np.where((ex < cr) & (ey < cr), cr - np.hypot(cr - ex, cr - ey), np.minimum(ex, ey))
streak = np.repeat(rng.normal(0, 1, (DH // 2, 1)).astype(np.float32), DW // 2, 1)
streak = np.asarray(Image.fromarray(((streak + 3) * 40).clip(0, 255).astype('uint8')).resize((DW, DH), Image.BILINEAR), np.float32) / 255 - .5
metal = 136 - 44 * yy / DH + streak * 26
base = np.stack((metal * 1.02, metal * .98, metal * .9), -1)
bev = np.clip(corner / (9 * SS), 0, 1)
light = (np.cos(np.pi * yy / DH) * 56 + np.cos(np.pi * xx / DW) * 20) * (1 - bev)
plate[..., :3] = base + light[..., None]
plate[..., 3] = np.clip(corner / 2, 0, 1) * 255
plate0 = plate.copy()
# a dark well for the dial, and the printed scale on a black ring
over(plate, np.array((20, 18, 18), np.float32), smooth(R_DISC, 3, rad))
ring_light = 34 + 20 * np.cos(ang * 2 + .6)
over(plate, np.stack((ring_light, ring_light * .98, ring_light * .94), -1), smooth(R_DISC - 7 * SS, 2, rad))
over(plate, np.array((10, 9, 9), np.float32), smooth(R_KNOB + 7 * SS, 3, rad))
pim = Image.fromarray(np.clip(plate, 0, 255).astype('uint8'), 'RGBA')
d = ImageDraw.Draw(pim)
num = ImageFont.truetype('C:/Windows/Fonts/ariblk.ttf', 19 * SS)
for pos, t in enumerate(('11', '7', 'K', '23', '?', '4', 'Z', '69', '&', '2', 'X', '9')):
    a = math.radians(pos * 30 - 90)
    rr = (R_DISC + R_KNOB) / 2 + 1 * SS
    tx, ty = CX + math.cos(a) * rr, CY + math.sin(a) * rr
    d.text((tx - d.textlength(t, font=num) / 2, ty - 13 * SS), t, font=num, fill=(238, 226, 196))
for k in range(60):
    a = math.radians(k * 6)
    r0, r1 = R_DISC - 5 * SS, R_DISC - (10 if k % 5 == 0 else 7) * SS
    d.line([(CX + math.cos(a) * r0, CY + math.sin(a) * r0), (CX + math.cos(a) * r1, CY + math.sin(a) * r1)], fill=(196, 188, 164), width=SS)
# two slotted screws
for sx, sy in ((36 * SS, DH * .79), (DW - 36 * SS, DH * .79)):
    d.ellipse([sx - 12 * SS, sy - 12 * SS, sx + 12 * SS, sy + 12 * SS], fill=(92, 88, 82), outline=(36, 34, 32), width=2 * SS)
    d.line([(sx - 9 * SS, sy - 3 * SS), (sx + 9 * SS, sy + 3 * SS)], fill=(24, 22, 20), width=3 * SS)
# masking tape with the marker on it
tape = Image.new('RGBA', (DW, 112 * SS), (0, 0, 0, 0))
td = ImageDraw.Draw(tape)
td.polygon([(0, 6 * SS), (DW - 26 * SS, 0), (DW - 20 * SS, 96 * SS), (5 * SS, 100 * SS)], fill=(227, 213, 174, 248))
fs = 68 * SS
mk = ImageFont.truetype(A + 'fonts/PermanentMarker.ttf', fs)
txt = 'Play random'
while td.textlength(txt, font=mk) > DW - 62 * SS:
    fs -= 2
    mk = ImageFont.truetype(A + 'fonts/PermanentMarker.ttf', fs)
td.text(((DW - 26 * SS - td.textlength(txt, font=mk)) / 2, 8 * SS), txt, font=mk, fill=(27, 23, 20))
tape = tape.rotate(-1.2, resample=Image.BICUBIC)
pim.alpha_composite(tape, (10 * SS, int(DH * .82)))
pim.resize((DW // SS, DH // SS), Image.LANCZOS).save(A + 'dial_plate.png', optimize=True)

# the knob: fluted bakelite skirt, spun aluminium cap, white pointer that reaches the numbers. Turns as a piece.
knob = np.zeros((DH, DW, 4), np.float32)
FLUTES = 22
flute = np.cos(ang * FLUTES) * .5 + .5
skirt_r = R_KNOB * (1 + .028 * flute)
skirt_c = 18 + 46 * flute ** 3
over(knob, np.stack((skirt_c, skirt_c * .96, skirt_c * .92), -1), smooth(0, 3, rad - skirt_r))
R_CAP = R_KNOB * .72
over(knob, np.array((26, 24, 24), np.float32), smooth(R_CAP + 4 * SS, 2, rad))
fine = np.cos(rad * .9) * 2.2
over(knob, np.stack((150 + fine, 148 + fine, 142 + fine), -1), smooth(R_CAP, 2, rad))
pointer = (np.abs(dx) < 5.5 * SS) & (dy < -R_CAP * .25) & (dy > -R_KNOB * 1.05)
over(knob, np.array((236, 232, 216), np.float32), pointer.astype(np.float32))
over(knob, np.array((84, 82, 78), np.float32), smooth(0, 3, rad - R_CAP * .2))
Image.fromarray(np.clip(knob, 0, 255).astype('uint8'), 'RGBA').resize((DW // SS, DH // SS), Image.LANCZOS).save(A + 'dial_knob.png', optimize=True)

# the light on it stays where the lamp is while the knob goes around: conic streaks on the cap, a lit top edge on the skirt
sh = np.zeros((DH, DW, 4), np.float32)
conic = np.clip(np.cos(ang * 2 + 1.1), 0, 1) ** 6 * 130 + np.clip(np.cos(ang * 2 - .9), 0, 1) ** 14 * 60
over(sh, np.array((255, 252, 240), np.float32), np.clip(conic / 255, 0, 1) * smooth(R_CAP - 2 * SS, 3, rad))
top = np.clip(-dy / R_KNOB, 0, 1) ** 2 * np.clip(1 - np.abs(rad - R_KNOB * .96) / (R_KNOB * .1), 0, 1) * .5
over(sh, np.array((255, 244, 220), np.float32), top)
under = np.clip(dy / R_KNOB, 0, 1) ** 1.5 * smooth(R_KNOB * 1.03, 3, rad) * .42
sh[..., :3] = np.where((under > sh[..., 3] / 255)[..., None], 0, sh[..., :3])
sh[..., 3] = np.maximum(sh[..., 3], under * 255)
Image.fromarray(np.clip(sh, 0, 255).astype('uint8'), 'RGBA').resize((DW // SS, DH // SS), Image.LANCZOS).save(A + 'dial_shine.png', optimize=True)

# the search tile: same plate, a chrome magnifying glass over the alphabet
pim = Image.fromarray(np.clip(plate0, 0, 255).astype('uint8'), 'RGBA')
d = ImageDraw.Draw(pim)
big = ImageFont.truetype('C:/Windows/Fonts/ariblk.ttf', 42 * SS)
for j, line in enumerate(('A B C', 'D E F', 'G H I')):
    d.text((CX - d.textlength(line, font=big) / 2 - 16 * SS, DH * .13 + j * 62 * SS), line, font=big, fill=(54, 50, 46))
LX, LY, LR = CX - 16 * SS, DH * .37, 106 * SS
d.line([(LX + LR * .68, LY + LR * .68), (LX + LR * 1.5, LY + LR * 1.5)], fill=(30, 26, 26), width=34 * SS)
d.line([(LX + LR * .72, LY + LR * .72), (LX + LR * 1.47, LY + LR * 1.47)], fill=(86, 40, 28), width=22 * SS)
pim = np.asarray(pim, np.float32).copy()
lr = np.hypot(xx - LX, yy - LY)
la = np.arctan2(yy - LY, xx - LX)
chrome = 150 + 90 * np.cos(la * 2 + 1.1)
over(pim, np.stack((chrome, chrome, chrome * .96), -1), smooth(LR, 3, lr))
# the lens shows the letters bigger and a little lighter
inner = smooth(LR - 13 * SS, 2, lr)
tint = np.array((226, 238, 240), np.float32)
pim[..., :3] = pim[..., :3] * (1 - inner[..., None]) + (tint * .78 + pim[..., :3] * .22) * inner[..., None]
pim = Image.fromarray(np.clip(pim, 0, 255).astype('uint8'), 'RGBA')
d = ImageDraw.Draw(pim)
lens = ImageFont.truetype('C:/Windows/Fonts/ariblk.ttf', 108 * SS)
d.text((LX - d.textlength('A?', font=lens) / 2, LY - 76 * SS), 'A?', font=lens, fill=(30, 26, 26))
for sx, sy in ((36 * SS, DH * .79), (DW - 36 * SS, DH * .79)):
    d.ellipse([sx - 12 * SS, sy - 12 * SS, sx + 12 * SS, sy + 12 * SS], fill=(92, 88, 82), outline=(36, 34, 32), width=2 * SS)
    d.line([(sx - 9 * SS, sy - 3 * SS), (sx + 9 * SS, sy + 3 * SS)], fill=(24, 22, 20), width=3 * SS)
tape = Image.new('RGBA', (DW, 112 * SS), (0, 0, 0, 0))
td = ImageDraw.Draw(tape)
td.polygon([(0, 6 * SS), (DW - 26 * SS, 0), (DW - 20 * SS, 96 * SS), (5 * SS, 100 * SS)], fill=(227, 213, 174, 248))
mk = ImageFont.truetype(A + 'fonts/PermanentMarker.ttf', 68 * SS)
td.text(((DW - 26 * SS - td.textlength('Search', font=mk)) / 2, 8 * SS), 'Search', font=mk, fill=(27, 23, 20))
pim.alpha_composite(tape.rotate(1.1, resample=Image.BICUBIC), (10 * SS, int(DH * .82)))
pim.resize((DW // SS, DH // SS), Image.LANCZOS).save(A + 'search_tile.png', optimize=True)

# the stats tile: same plate, a tape counter (the digits are live, Room draws them) over a small bar chart
pim = Image.fromarray(np.clip(plate0, 0, 255).astype('uint8'), 'RGBA')
d = ImageDraw.Draw(pim)
d.rounded_rectangle([DW * .08, DH * .15, DW * .92, DH * .33], radius=10 * SS, fill=(6, 12, 8), outline=(92, 88, 82), width=4 * SS)
d.line([(DW * .1, DH * .335), (DW * .9, DH * .335)], fill=(190, 186, 176), width=2 * SS)
bars = (.32, .55, .26, .74, .46, .9, .62)
bw = DW * .72 / len(bars)
floor = DH * .77
for k, v in enumerate(bars):
    bx = DW * .14 + k * bw
    d.rectangle([bx + 4 * SS, floor - v * DH * .36, bx + bw - 4 * SS, floor], fill=(232, 150, 58) if k == 5 else (70, 64, 58), outline=(30, 26, 26), width=2 * SS)
d.line([(DW * .12, floor + 2 * SS), (DW * .88, floor + 2 * SS)], fill=(30, 26, 26), width=4 * SS)
for sx, sy in ((36 * SS, DH * .08), (DW - 36 * SS, DH * .08)):
    d.ellipse([sx - 12 * SS, sy - 12 * SS, sx + 12 * SS, sy + 12 * SS], fill=(92, 88, 82), outline=(36, 34, 32), width=2 * SS)
    d.line([(sx - 9 * SS, sy + 3 * SS), (sx + 9 * SS, sy - 3 * SS)], fill=(24, 22, 20), width=3 * SS)
tape = Image.new('RGBA', (DW, 112 * SS), (0, 0, 0, 0))
td = ImageDraw.Draw(tape)
td.polygon([(4 * SS, 2 * SS), (DW - 22 * SS, 6 * SS), (DW - 26 * SS, 100 * SS), (0, 94 * SS)], fill=(227, 213, 174, 248))
td.text(((DW - 26 * SS - td.textlength('Stats', font=mk)) / 2, 8 * SS), 'Stats', font=mk, fill=(27, 23, 20))
pim.alpha_composite(tape.rotate(-.8, resample=Image.BICUBIC), (10 * SS, int(DH * .82)))
pim.resize((DW // SS, DH // SS), Image.LANCZOS).save(A + 'stats_tile.png', optimize=True)

# --- sounds, 22 kHz mono
def wav(name, s):
    v = np.clip(s, -1, 1)
    with wave.open(A + 'sfx/' + name + '.wav', 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes((v * 32000).astype('<i2').tobytes())


def t(sec):
    return np.arange(int(22050 * sec)) / 22050


x = t(.035)
wav('tick', np.sin(2 * np.pi * 1400 * x) * np.exp(-x * 170) * .28 + rng.normal(0, .05, x.size) * np.exp(-x * 240))
x = t(.13)
wav('thunk', np.sin(2 * np.pi * (130 - 300 * x) * x) * np.exp(-x * 34) * .7 + rng.normal(0, .18, x.size) * np.exp(-x * 110))
x = t(.34)
n = np.convolve(rng.normal(0, 1, x.size), [.5, -.5], 'same')
wav('static', n * .22 * np.minimum(1, x * 90) * np.minimum(1, (x[-1] - x) * 30))
x = t(.08)
wav('back', np.sin(2 * np.pi * (520 - 2400 * x) * x) * np.exp(-x * 42) * .34)
x = t(.42)
wav('power', np.sin(2 * np.pi * (260 + 1500 * x) * x) * np.exp(-x * 5) * .3 + rng.normal(0, .06, x.size) * np.exp(-x * 9))
print('art done')

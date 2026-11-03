# Textures for the 3D rooms: posters, fabrics, the wet street outside the window. All drawn here.
import math
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace('\\', '/') + '/'

OUT = ROOT + 'render/tex/'
os.makedirs(OUT, exist_ok=True)
rng = np.random.default_rng(1994)
FONT = ROOT + 'app/src/main/assets/fonts/PermanentMarker.ttf'


def memphis(name, bg, seed):
    r = np.random.default_rng(seed)
    w, h = 780, 1080
    im = Image.new('RGB', (w, h), bg)
    d = ImageDraw.Draw(im)
    for _ in range(90):
        x, y = int(r.integers(0, w)), int(r.integers(0, h))
        c = [(40, 230, 220), (255, 60, 170), (255, 214, 60), (130, 90, 255), (240, 240, 230)][int(r.integers(0, 5))]
        k = int(r.integers(0, 4))
        s = int(r.integers(22, 80))
        if k == 0:
            d.polygon([(x, y), (x + s, y + s // 3), (x + s // 3, y + s)], fill=c)
        elif k == 1:
            d.ellipse([x, y, x + s, y + s], outline=c, width=9)
        elif k == 2:
            d.line([(x + i * 20, y + (18 if i % 2 else -18)) for i in range(7)], fill=c, width=9)
        else:
            d.rectangle([x, y, x + s, y + s // 4], fill=c)
    im.save(OUT + name)


memphis('poster_memphis.png', (16, 40, 72), 1)
memphis('poster_memphis2.png', (44, 16, 60), 2)

# sunset, grid, nowhere to be
w, h = 860, 1200
im = Image.new('RGB', (w, h))
d = ImageDraw.Draw(im)
for y in range(h):
    t = y / h
    d.line([(0, y), (w, y)], fill=(int(30 + 200 * t), int(10 + 30 * t), int(90 + 30 * t)))
cx, cy, r = w // 2, int(h * .5), int(w * .32)
for y in range(cy - r, cy + r):
    half = int(math.sqrt(max(0, r * r - (y - cy) ** 2)))
    if y > cy and (y - cy) % 34 < 12:
        continue
    t = (y - cy + r) / (2 * r)
    d.line([(cx - half, y), (cx + half, y)], fill=(255, int(220 - 150 * t), int(70 + 60 * t)))
hz = int(h * .66)
d.rectangle([0, hz, w, h], fill=(14, 6, 40))
for i in range(-12, 13):
    d.line([(w // 2 + i * 18, hz), (w // 2 + i * 90, h)], fill=(50, 230, 240), width=3)
for j in range(1, 8):
    y = hz + int((j / 8) ** 2 * (h - hz))
    d.line([(0, y), (w, y)], fill=(50, 230, 240), width=3)
im.save(OUT + 'poster_sunset.png')

# a comet over a black field, in the manner of every dorm room
w, h = 620, 880
im = Image.new('RGB', (w, h), (8, 8, 22))
d = ImageDraw.Draw(im)
for _ in range(260):
    x, y = int(rng.integers(0, w)), int(rng.integers(0, h))
    v = int(rng.integers(80, 255))
    d.point((x, y), fill=(v, v, v))
for i in range(180):
    t = i / 180
    x, y = 90 + t * 430, 140 + t * 330
    rr = 6 + t * 44
    d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=(int(40 + 215 * t), int(90 + 165 * t), int(180 + 75 * t)))
im = im.filter(ImageFilter.GaussianBlur(2))
ImageDraw.Draw(im).text((70, 740), 'Keep Looking Up', font=ImageFont.truetype(FONT, 52), fill=(230, 226, 210))
im.save(OUT + 'poster_comet.png')

# zigzag
w, h = 920, 620
im = Image.new('RGB', (w, h), (20, 12, 40))
d = ImageDraw.Draw(im)
cols = [(255, 60, 170), (40, 230, 220), (255, 214, 60)]
for i in range(10):
    d.line([(x, 40 + i * 62 + (32 if (x // 70) % 2 else -32)) for x in range(0, w + 70, 70)], fill=cols[i % 3], width=16)
im.save(OUT + 'poster_zigzag.png')

# plaid: the only couch fabric
n = 512
pl = np.zeros((n, n, 3), np.float32)
base = np.array((104, 62, 34), np.float32)
pl[:] = base
for band, col, width in ((60, (46, 58, 40), 62), (190, (128, 96, 52), 44), (300, (40, 34, 30), 34), (420, (150, 52, 36), 16)):
    pl[band:band + width] = pl[band:band + width] * .45 + np.array(col, np.float32) * .55
    pl[:, band:band + width] = pl[:, band:band + width] * .45 + np.array(col, np.float32) * .55
thread = rng.normal(0, 7, (n, n))
pl += thread[..., None]
weave = (np.sin(np.arange(n)[:, None] * 1.4) * np.sin(np.arange(n)[None, :] * 1.4)) * 6
pl += weave[..., None]
Image.fromarray(np.clip(pl, 0, 255).astype('uint8')).save(OUT + 'plaid.png')

# chunky knit
n = 512
xx, yy = np.mgrid[0:n, 0:n].astype(np.float32)
kn = (np.sin(xx * .8 + np.sin(yy * .4) * 2.4) * .5 + .5) * (np.sin(yy * .8) * .5 + .5)
col = np.array((196, 164, 120), np.float32)
Image.fromarray(np.clip(col * (.55 + .55 * kn)[..., None], 0, 255).astype('uint8')).save(OUT + 'knit.png')

# kid's bed sheets: rockets, sort of
n = 512
im = Image.new('RGB', (n, n), (32, 52, 104))
d = ImageDraw.Draw(im)
for _ in range(60):
    x, y = int(rng.integers(0, n)), int(rng.integers(0, n))
    c = [(230, 70, 60), (250, 210, 70), (240, 240, 230)][int(rng.integers(0, 3))]
    d.polygon([(x, y - 18), (x + 8, y + 12), (x - 8, y + 12)], fill=c)
im.save(OUT + 'sheets.png')

# marquee and dartboard
w, h = 620, 160
im = Image.new('RGB', (w, h), (20, 8, 40))
d = ImageDraw.Draw(im)
for y in range(h):
    d.line([(0, y), (w, y)], fill=(int(250 - y), int(60 + y * .8), int(120 + y * .4)))
d.text((70, 18), 'QUARTERS', font=ImageFont.truetype(FONT, 100), fill=(255, 240, 80), stroke_width=4, stroke_fill=(30, 10, 60))
im.save(OUT + 'marquee.png')
n = 512
im = Image.new('RGB', (n, n), (12, 12, 12))
d = ImageDraw.Draw(im)
cx = cy = n // 2
for k, rad in enumerate((240, 214, 160, 134, 40, 18)):
    for a in range(20):
        col = (((36, 110, 60), (190, 30, 30)) if k % 2 == 0 else ((24, 24, 24), (220, 210, 180)))[a % 2]
        if k > 3:
            col = (190, 30, 30) if k == 5 else (36, 110, 60)
        d.pieslice([cx - rad, cy - rad, cx + rad, cy + rad], a * 18 - 9, a * 18 + 9, fill=col)
im.save(OUT + 'dart.png')

# the world outside: wet street, a house across the way, bare trees, all out of focus through rain
w, h = 2048, 1134
sky = np.zeros((h, w, 3), np.float32)
sky[:] = np.linspace(1, .62, h)[:, None, None] * np.array((206, 212, 218), np.float32)
im = Image.fromarray(sky.astype('uint8'))
d = ImageDraw.Draw(im)
gnd = int(h * .68)
for i in range(7):
    x = int(rng.integers(-100, w))
    bw, bh = int(rng.integers(220, 460)), int(rng.integers(180, 330))
    v = int(rng.integers(120, 158))
    d.rectangle([x, gnd - bh, x + bw, gnd], fill=(v, v + 2, v + 6))
    d.polygon([(x - 18, gnd - bh), (x + bw // 2, gnd - bh - bh // 3), (x + bw + 18, gnd - bh)], fill=(v - 34, v - 32, v - 30))
    for wx in range(x + 28, x + bw - 40, 82):
        lit = rng.random() < .35
        d.rectangle([wx, gnd - bh + 42, wx + 42, gnd - bh + 102], fill=(246, 214, 150) if lit else (76, 84, 92))
d.rectangle([0, gnd, w, h], fill=(86, 90, 96))
for _ in range(9):
    x = int(rng.integers(0, w))
    base_y = gnd + 20
    d.line([(x, base_y), (x, base_y - 420)], fill=(52, 54, 56), width=16)
    for _ in range(30):
        a = rng.uniform(-2.5, -.6)
        L = rng.uniform(70, 230)
        y0 = base_y - rng.uniform(190, 410)
        d.line([(x, y0), (x + math.cos(a) * L, y0 + math.sin(a) * L)], fill=(58, 60, 62), width=int(rng.integers(3, 8)))
for _ in range(16):
    # reflections of the lights in the road
    x = int(rng.integers(0, w))
    d.rectangle([x, gnd + 12, x + 22, h], fill=(150, 142, 118))
im = im.filter(ImageFilter.GaussianBlur(7))
im.save(OUT + 'rainy_street.png')
# ---- second pass ------------------------------------------------------------------------------

PHOTOS = ROOT + 'render/photos/'


def photo_print(im, stamp=None):
    """A drugstore print: slightly faded blacks, warm, fine grain."""
    a = np.asarray(im.convert('RGB'), np.float32)
    a = 14 + a * .92
    a *= np.array((1.03, 1.0, .93), np.float32)
    a += rng.normal(0, 3.5, a.shape[:2])[..., None]
    out = Image.fromarray(np.clip(a, 0, 255).astype('uint8'))
    if stamp:
        d = ImageDraw.Draw(out)
        f = ImageFont.truetype('C:/Windows/Fonts/consolab.ttf', out.height // 18)
        tw = d.textlength(stamp, font=f)
        d.text((out.width - tw - out.width * .05, out.height * .9), stamp, font=f, fill=(255, 150, 40))
    return out


# the thumbs up: the frame where the thumb is clearest
gif = Image.open(PHOTOS + 'thumbs_up.gif')
gif.seek(66)
photo_print(gif.convert('RGB').resize((1040, 780), Image.LANCZOS)).save(OUT + 'photo_kid.png')

# the cat, who knows what he did
cat = Image.open(PHOTOS + 'cat.jpg').convert('RGB')
photo_print(cat.crop((240, 640, 1240, 1890)).resize((800, 1000), Image.LANCZOS), "'94 6 12").save(OUT + 'photo_cat.png')

# hang in there: a drawing, shot on paper, flattened and printed on cream stock
w, h = 880, 1200
art = Image.open(PHOTOS + 'hang_in_there.jpg').convert('L')
art = art.crop((0, 40, art.width, art.height - 30))
sc = (w - 60) / art.width
art = art.resize((w - 60, int(art.height * sc)), Image.LANCZOS)
g = np.asarray(art, np.float32)
paper = np.asarray(art.filter(ImageFilter.GaussianBlur(60)), np.float32)
ink = np.clip((1 - g / np.maximum(paper, 1)) * 2.1, 0, 1)[..., None]
stock = np.array((244, 238, 220), np.float32)
pic = stock * (1 - ink) + np.array((34, 30, 30), np.float32) * ink
im = Image.new('RGB', (w, h), tuple(int(v) for v in stock))
pic = Image.fromarray(np.clip(pic, 0, 255).astype('uint8'))
im.paste(pic.crop((0, 0, pic.width, min(pic.height, 1000))), (30, 16))
d = ImageDraw.Draw(im)
f = ImageFont.truetype('C:/Windows/Fonts/COOPBL.TTF', 118)
t = 'Hang in there!'
fs = 118
while d.textlength(t, font=f) > w - 70:
    fs -= 2
    f = ImageFont.truetype('C:/Windows/Fonts/COOPBL.TTF', fs)
d.text(((w - d.textlength(t, font=f)) / 2, 1050), t, font=f, fill=(196, 58, 30))
a_ = np.asarray(im, np.float32) * np.array((1.0, .96, .86), np.float32)  # thirty years of sunlight and cigarettes
im = Image.fromarray(np.clip(a_, 0, 255).astype('uint8'))
im.save(OUT + 'poster_hang.png')


# the Game Boy ad: a scan, torn out of a magazine
photo_print(Image.open(PHOTOS + 'game_boy_ad.jpg').convert('RGB').resize((960, 1320), Image.LANCZOS)).save(OUT + 'poster_ferret.png')

# READ: a scan, up to frame size
photo_print(Image.open(PHOTOS + 'read.jpg').convert('RGB').resize((838, 1280), Image.LANCZOS)).save(OUT + 'poster_read.png')


def periodic_noise(n, m, sx, sy, seed):
    """Gaussian-filtered noise that tiles both ways. sx, sy are blur sizes in pixels."""
    r = np.random.default_rng(seed)
    f = np.fft.fft2(r.normal(0, 1, (m, n)))
    fy = np.fft.fftfreq(m)[:, None]
    fx = np.fft.fftfreq(n)[None, :]
    g = np.real(np.fft.ifft2(f * np.exp(-2 * (np.pi ** 2) * ((fx * sx) ** 2 + (fy * sy) ** 2))))
    return (g - g.mean()) / g.std()


# 1970s walnut sheet paneling: random-width planks, dark V grooves, cathedral grain running floor to ceiling.
# 2048 px = 2.4 m. Tiles both ways.
n = 2048
r = np.random.default_rng(1974)
xx, yy = np.meshgrid(np.arange(n, dtype=np.float32), np.arange(n, dtype=np.float32))
warp = periodic_noise(n, n, 90, 420, 11) * 26 + periodic_noise(n, n, 24, 140, 12) * 5
fine = periodic_noise(n, n, 1.1, 60, 13)
pore = periodic_noise(n, n, .7, 14, 14)
blotch = periodic_noise(n, n, 70, 240, 15)
edges = [0]
while edges[-1] < n - 90:
    edges.append(edges[-1] + int(r.choice((96, 128, 128, 160, 192))))
edges[-1] = n
col = np.zeros((n, n, 3), np.float32)
hgt = np.ones((n, n), np.float32)
dark, mid, light = np.array((44, 22, 10), np.float32), np.array((98, 56, 26), np.float32), np.array((142, 88, 44), np.float32)
for a, b in zip(edges, edges[1:]):
    roll = int(r.integers(0, n))
    w_ = np.roll(warp, roll, axis=1)[:, a:b]
    x_ = xx[:, a:b]
    lam = float(r.uniform(16, 26))
    rings = np.sin(2 * np.pi * (x_ - (a + b) / 2 + w_) / lam + 3 * np.roll(blotch, roll, axis=1)[:, a:b] * .3)
    rings = np.sign(rings) * np.abs(rings) ** .55
    g = .5 + rings * .17 + np.roll(fine, roll, axis=1)[:, a:b] * .13 + np.roll(pore, roll, axis=0)[:, a:b] * .05 + np.roll(blotch, roll, axis=1)[:, a:b] * .07
    g = np.clip(g + float(r.uniform(-.11, .11)), 0, 1)[..., None]
    col[:, a:b] = np.where(g < .5, dark + (mid - dark) * (g / .5), mid + (light - mid) * ((g - .5) / .5))
    # the groove, painted black, with the milled edge catching the light on one side
    col[:, a:a + 4] *= .13
    col[:, a + 4:a + 7] *= 1.22
    col[:, b - 3:b] *= .55
    hgt[:, a:a + 5] = np.array((.2, .1, 0, .1, .2), np.float32)[None, :]
    hgt[:, a + 5:a + 8] = np.array((.5, .8, .95), np.float32)[None, :]
hgt = hgt - np.clip(np.abs(fine) * .012, 0, .03)
Image.fromarray(np.clip(col, 0, 255).astype('uint8')).save(OUT + 'paneling.png')
Image.fromarray(np.clip(hgt * 255, 0, 255).astype('uint8')).save(OUT + 'paneling_h.png')

# granny's afghan: chevrons in every colour 1974 had
n = 1024
xx, yy = np.mgrid[0:n, 0:n].astype(np.float32)
zig = np.abs(((yy / 128) % 1) - .5) * 96
band = (((xx + zig) / 64).astype(np.int32)) % 6
pal = np.array(((156, 84, 28), (214, 158, 58), (226, 214, 180), (92, 110, 54), (120, 44, 26), (226, 214, 180)), np.float32)
af = pal[band]
st = (np.sin(xx * 1.57) * np.sin(yy * 1.57)) * .5 + .5
af *= (.72 + .36 * st)[..., None]
Image.fromarray(np.clip(af, 0, 255).astype('uint8')).save(OUT + 'afghan.png')

# oatmeal cable knit for the Sunday sofa
n = 1024
xx, yy = np.mgrid[0:n, 0:n].astype(np.float32)
cable = np.sin(yy * .098 + np.sin(xx * .049) * 2.2) * .5 + .5
purl = np.sin(xx * 1.05) * np.sin(yy * 1.05) * .5 + .5
kn = cable * .6 + purl * .4
Image.fromarray(np.clip(np.array((206, 192, 166), np.float32) * (.58 + .5 * kn)[..., None], 0, 255).astype('uint8')).save(OUT + 'cableknit.png')

# corrugated kraft with old grease
n = 512
pap = np.array((176, 134, 84), np.float32) + periodic_noise(n, n, 2, 2, 21)[..., None] * 6 + np.sin(np.arange(n)[None, :, None] * .9) * 3
gre = np.clip((periodic_noise(n, n, 26, 26, 22) - 1.0) * .8, 0, 1)[..., None]
Image.fromarray(np.clip(pap * (1 - gre * .22), 0, 255).astype('uint8')).save(OUT + 'kraft.png')
# the sodas: 2048 around, twice around the can, silver at the seams
def soda(file, top, bottom, word, fg, stroke, size, shape=None, shape_col=None):
    w, h = 2048, 1024
    g = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    im = Image.fromarray(np.clip(np.array(top, np.float32) * (1 - g) + np.array(bottom, np.float32) * g, 0, 255).repeat(w, 1).astype('uint8'))
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype('C:/Windows/Fonts/ariblk.ttf', size)
    for cx in (512, 1536):
        if shape:
            d.polygon([(cx + a * 1.1, 505 + b) for a, b in shape], fill=shape_col, outline=stroke)
        tw = d.textlength(word, font=f)
        d.text((cx - tw / 2, 505 - size * .68), word, font=f, fill=fg, stroke_width=14, stroke_fill=stroke)
    d.rectangle([0, 0, w, 140], fill=(186, 188, 196))
    d.rectangle([0, h - 70, w, h], fill=(170, 172, 180))
    im.save(OUT + file)


def burst(points, r0, r1):
    return [((r1 if i % 2 == 0 else r0) * math.cos(i * math.pi / points), (r1 if i % 2 == 0 else r0) * math.sin(i * math.pi / points)) for i in range(points * 2)]


BOLT = [(-90, -350), (130, -350), (30, -90), (190, -90), (-120, 360), (-30, 30), (-180, 30)]
FLAME = [(0, -350), (90, -210), (170, -60), (190, 90), (130, 240), (0, 320), (-130, 240), (-190, 90), (-150, -40), (-70, -90), (-40, -210)]
soda('can_zap.png', (12, 40, 170), (42, 110, 240), 'ZAP', (250, 250, 240), (170, 20, 28), 262, BOLT, (255, 224, 40))
soda('can_pow.png', (214, 30, 34), (150, 12, 24), 'POW', (255, 255, 250), (20, 16, 60), 240, burst(11, 190, 350), (255, 212, 40))
soda('can_blasto.png', (250, 120, 20), (214, 56, 16), 'BLASTO', (255, 248, 210), (70, 20, 90), 158, burst(8, 120, 370), (120, 40, 170))
soda('can_gas.png', (24, 30, 26), (20, 70, 44), 'GAS', (190, 255, 70), (10, 30, 20), 270, FLAME, (40, 150, 70))

# the lamp's base and cap: white, black confetti, loud shapes
n_w, n_h = 1536, 768
r = np.random.default_rng(90)
im = Image.new('RGB', (n_w * 2, n_h * 2), (238, 236, 232))
d = ImageDraw.Draw(im)
for _ in range(1500):
    x, y = float(r.uniform(0, n_w * 2)), float(r.uniform(0, n_h * 2))
    a = float(r.uniform(0, 3.14))
    L = float(r.uniform(16, 34))
    d.line([(x, y), (x + math.cos(a) * L, y + math.sin(a) * L)], fill=(14, 14, 16), width=6)
COLS = ((40, 196, 230), (236, 48, 130), (250, 212, 40), (118, 70, 210))
for i in range(46):
    x, y = float(r.uniform(60, n_w * 2 - 60)), float(r.uniform(40, n_h * 2 - 40))
    s_ = float(r.uniform(70, 120))
    c = COLS[i % 4]
    k = i % 4
    if k == 0:
        d.polygon([(x - s_, y - s_ * .7), (x + s_, y - s_ * .7), (x + s_ * .1, y + s_)], fill=c)
    elif k == 1:
        d.ellipse([x - s_ * .7, y - s_ * .7, x + s_ * .7, y + s_ * .7], fill=c)
    elif k == 2:
        d.polygon([(x - s_ * .4, y - s_), (x + s_ * .3, y - s_), (x, y - s_ * .1), (x + s_ * .5, y - s_ * .1), (x - s_ * .4, y + s_), (x - s_ * .1, y + s_ * .1), (x - s_ * .6, y + s_ * .1)], fill=c, outline=(14, 14, 16))
    else:
        d.polygon([(x, y - s_), (x + s_, y), (x, y + s_), (x - s_, y)], fill=c)
    if i % 3 == 0:
        d.line([(x - s_ + j * s_ * .4, y + s_ + (18 if j % 2 else -18)) for j in range(6)], fill=(14, 14, 16), width=10)
im.resize((n_w, n_h), Image.LANCZOS).save(OUT + 'lamp_memphis.png')

# I want to believe, as it'd hang in this bedroom: neon dusk, a fuzzy saucer, pines, the line across the bottom
w, h = 880, 1200
r = np.random.default_rng(1993)
g = np.linspace(0, 1, h, dtype=np.float32)[:, None]
stops = np.array(((10, 6, 44), (46, 12, 112), (150, 26, 150), (255, 70, 150)), np.float32)
pos = np.array((0, .3, .55, .68), np.float32)
bg = np.stack([np.interp(g[:, 0], pos, stops[:, c]) for c in range(3)], -1)[:, None, :].repeat(w, 1)
im = Image.fromarray(np.clip(bg, 0, 255).astype('uint8'))
d = ImageDraw.Draw(im)
for _ in range(420):
    x, y = float(r.uniform(0, w)), float(r.uniform(0, h * .62))
    v = int(r.uniform(110, 255))
    a = float(r.uniform(.8, 2.2))
    d.ellipse([x - a, y - a, x + a, y + a], fill=(v, v, min(255, v + 30)))
# the beam, soft-edged, and the saucer that's throwing it
sx, sy = w * .53, h * .24
beam = Image.new('L', (w, h), 0)
ImageDraw.Draw(beam).polygon([(sx - 42, sy + 26), (sx + 42, sy + 26), (sx + 205, h * .64), (sx - 185, h * .64)], fill=118)
beam = beam.filter(ImageFilter.GaussianBlur(9))
fade = Image.fromarray((np.clip(1.15 - (np.arange(h, dtype=np.float32) - sy) / (h * .5), 0, 1) ** .8 * 255)[:, None].repeat(w, 1).astype('uint8'))
beam = Image.composite(beam, Image.new('L', (w, h), 0), fade)
im.paste(Image.new('RGB', (w, h), (110, 250, 255)), (0, 0), beam)
d = ImageDraw.Draw(im)
d.ellipse([sx - 66, sy - 74, sx + 66, sy + 8], fill=(150, 226, 240))
d.ellipse([sx - 170, sy - 32, sx + 170, sy + 40], fill=(34, 26, 70))
d.ellipse([sx - 170, sy - 38, sx + 170, sy + 22], fill=(128, 128, 170))
d.ellipse([sx - 92, sy - 28, sx + 92, sy + 6], fill=(196, 200, 226))
for k in range(9):
    a = -1 + k / 4
    lx, ly = sx + a * 146, sy + 18 - (a * a) * 12
    d.ellipse([lx - 8, ly - 8, lx + 8, ly + 8], fill=((110, 250, 255) if k % 2 else (255, 90, 190)))
glow_ = im.filter(ImageFilter.GaussianBlur(14))
im = Image.blend(im, glow_, .3).filter(ImageFilter.GaussianBlur(1.6))  # nobody ever got a sharp one
d = ImageDraw.Draw(im)
# pines, two ranks
for rank, (base, col, lo, hi, n) in enumerate(((h * .67, (58, 12, 92), 90, 190, 26), (h * .7, (16, 4, 34), 150, 300, 15))):
    d.rectangle([0, base, w, h], fill=col)
    for i in range(n):
        x = (i + float(r.uniform(-.3, .3))) * w / (n - 1)
        th = float(r.uniform(lo, hi))
        tw = th * .3
        for lay in range(6):
            t = lay / 6
            y0 = base - th * (1 - t)
            d.polygon([(x, y0), (x + tw * (t + .25), y0 + th * .34), (x - tw * (t + .25), y0 + th * .34)], fill=col)
d.rectangle([0, h * .7, w, h], fill=(10, 3, 24))
for line, y, fs in (('I WANT TO', 846, 104), ('BELIEVE', 950, 196)):
    f = ImageFont.truetype('C:/Windows/Fonts/impact.ttf', fs)
    x = (w - d.textlength(line, font=f)) / 2
    d.text((x - 3, y), line, font=f, fill=(255, 40, 170))
    d.text((x + 3, y), line, font=f, fill=(40, 230, 255))
    d.text((x, y), line, font=f, fill=(246, 244, 255))
a_ = np.asarray(im, np.float32) + r.normal(0, 4, (h, w))[..., None]
Image.fromarray(np.clip(a_, 0, 255).astype('uint8')).save(OUT + 'poster_believe.png')

print('textures done', sorted(os.listdir(OUT)))

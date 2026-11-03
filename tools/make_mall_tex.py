# Textures for the mall arcade: pun cabinets' marquees and attract screens that match them, cosmic carpet, the signs. All drawn here.
import math
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace('\\', '/') + '/'

OUT = ROOT + 'render/tex/'
rng = np.random.default_rng(1993)
MARKER = ROOT + 'app/src/main/assets/fonts/PermanentMarker.ttf'
BLACK = 'C:/Windows/Fonts/ariblk.ttf'
IMPACT = 'C:/Windows/Fonts/impact.ttf'
# name, marquee top and bottom, ink, font, what's on its screen, the line across the top of the screen
GAMES = (
    ('CRAZY TAXES', (250, 200, 20), (240, 110, 10), (16, 16, 24), IMPACT, 'road', 'DUE APR 15'),
    ('MORTAL WOMBAT', (110, 10, 10), (20, 8, 8), (255, 190, 40), IMPACT, 'brawl', 'ROUND 1'),
    ('STREET FARTER II', (20, 40, 150), (220, 30, 30), (255, 240, 90), IMPACT, 'brawl', 'ROUND 2'),
    ('SPACE INVOICES', (6, 6, 30), (40, 20, 110), (120, 255, 120), BLACK, 'invaders', 'NET 30'),
    ('SNACK-MAN', (20, 20, 120), (10, 10, 50), (255, 225, 40), BLACK, 'maze', 'HIGH 024700'),
    ('TETANUS', (40, 0, 80), (220, 40, 160), (140, 255, 255), BLACK, 'blocks', 'GET A BOOSTER'),
    ('HEMORRHOIDS', (10, 10, 30), (70, 70, 100), (240, 240, 255), BLACK, 'rocks', 'INSERT COIN'),
    ('MOLE POSITION', (30, 90, 30), (110, 70, 20), (255, 245, 200), IMPACT, 'road', 'PREPARE TO DIG'),
    ('SNORECRAFT', (10, 30, 90), (30, 110, 200), (235, 245, 255), BLACK, 'stars', 'ZZZZZZ'),
    ('DONKEY KONGRESS', (180, 30, 20), (90, 10, 10), (255, 230, 90), IMPACT, 'girders', 'FILIBUSTER'),
)


def fit(d, text, path, w, h):
    size = h
    while size > 8:
        f = ImageFont.truetype(path, size)
        box = d.textbbox((0, 0), text, font=f, stroke_width=4)
        if box[2] - box[0] <= w and box[3] - box[1] <= h:
            return f, box
        size -= 2
    return f, box


def marquee(i, name, top, bottom, ink, font):
    W, H = 620, 160
    g = np.linspace(0, 1, H)[:, None, None]
    a = np.array(top, np.float32) * (1 - g) + np.array(bottom, np.float32) * g
    im = Image.fromarray(np.repeat(a, W, 1).astype('uint8'))
    d = ImageDraw.Draw(im)
    for k in range(14):
        x = rng.integers(0, W)
        y = rng.integers(0, H)
        r = rng.integers(10, 70)
        d.line([(x - r, y + r), (x + r, y - r)], fill=tuple(min(255, c + 40) for c in bottom), width=int(rng.integers(2, 7)))
    f, box = fit(d, name, font, W - 50, H - 36)
    d.text(((W - (box[2] - box[0])) / 2 - box[0], (H - (box[3] - box[1])) / 2 - box[1]), name, font=f, fill=ink, stroke_width=4, stroke_fill=(10, 8, 14))
    im.save(f'{OUT}mq{i}.png')


def screen(i, kind, line):
    """An attract screen, low-res and big-pixeled, showing the game on the marquee above it."""
    W, H = 160, 120
    im = Image.new('RGB', (W, H), (2, 2, 12))
    d = ImageDraw.Draw(im)
    if kind in ('rocks', 'stars', 'invaders'):
        for _ in range(70):
            d.point((int(rng.integers(0, W)), int(rng.integers(0, H))), fill=(220, 220, 255))
    if kind == 'rocks':
        for _ in range(7):
            x, y, r = int(rng.integers(0, W)), int(rng.integers(14, 90)), int(rng.integers(4, 12))
            d.polygon([(x + r * math.cos(k * 1.05) * (1 + .3 * (k % 2)), y + r * math.sin(k * 1.05)) for k in range(6)], outline=(235, 235, 235))
        d.polygon([(76, 104), (84, 104), (80, 92)], outline=(255, 255, 255))
        d.line((80, 92, 80, 70), fill=(255, 255, 255))
    elif kind == 'stars':
        # a little fleet, all parked, nothing happening
        for x, y in ((40, 50), (70, 42), (104, 56), (56, 74), (92, 80)):
            d.polygon([(x, y), (x + 14, y + 4), (x, y + 8)], fill=(150, 170, 200))
            d.text((x + 15, y - 8), 'z', fill=(255, 255, 255))
    elif kind == 'invaders':
        for r, c in enumerate(((120, 255, 120), (120, 255, 120), (255, 255, 120), (255, 120, 180))):
            for k in range(9):
                x, y = 22 + k * 13, 18 + r * 12
                d.rectangle((x, y, x + 8, y + 5), fill=c)
                d.point([(x + 2, y + 2), (x + 6, y + 2)], fill=(2, 2, 12))
                d.line((x, y + 6, x + 2, y + 7), fill=c)
                d.line((x + 8, y + 6, x + 6, y + 7), fill=c)
        for x in (30, 70, 110):
            d.rectangle((x, 90, x + 18, 97), fill=(60, 220, 60))
        d.rectangle((74, 108, 86, 112), fill=(120, 255, 255))
    elif kind == 'maze':
        M = (30, 60, 255)
        d.rectangle((4, 12, W - 5, H - 3), outline=M)
        for x, y, w, h in ((16, 24, 30, 8), (60, 24, 40, 8), (114, 24, 30, 8), (16, 44, 8, 30), (36, 44, 34, 8), (90, 44, 34, 8), (136, 44, 8, 30), (60, 62, 40, 16), (16, 90, 40, 8), (70, 90, 20, 16), (104, 90, 40, 8)):
            d.rectangle((x, y, x + w, y + h), outline=M)
        for y in range(18, H - 6, 18):
            for x in range(10, W - 6, 10):
                d.point((x, y), fill=(255, 220, 180))
        d.pieslice((26, 74, 38, 86), 30, 330, fill=(255, 225, 40))
        for x, c in ((70, (255, 60, 60)), (84, (255, 150, 200))):
            d.pieslice((x, 66, x + 10, 76), 180, 360, fill=c)
            d.rectangle((x, 71, x + 10, 76), fill=c)
    elif kind == 'road':
        d.rectangle((0, 12, W, 54), fill=(70, 120, 230))
        d.ellipse((110, 18, 136, 44), fill=(255, 220, 80))
        d.rectangle((0, 54, W, H), fill=(40, 150, 60))
        d.polygon([(70, 54), (90, 54), (150, H), (10, H)], fill=(60, 60, 66))
        for k in range(5):
            y = 58 + k * k * 3
            d.rectangle((79 - k, y, 81 + k, y + k + 1), fill=(255, 255, 255))
        body = (250, 210, 30) if 'APR' in line else (120, 80, 50)
        d.rectangle((66, 96, 94, 110), fill=body)
        d.rectangle((72, 88, 88, 96), fill=(40, 40, 60))
        d.rectangle((62, 108, 70, 114), fill=(10, 10, 10))
        d.rectangle((90, 108, 98, 114), fill=(10, 10, 10))
    elif kind == 'brawl':
        d.rectangle((0, 12, W, 80), fill=(120, 40, 60) if line == 'ROUND 1' else (60, 100, 180))
        d.rectangle((0, 80, W, H), fill=(70, 60, 50))
        a, b = ((150, 110, 70), (90, 90, 100)) if line == 'ROUND 1' else ((240, 240, 240), (230, 60, 40))
        for x, c, way in ((52, a, 1), (98, b, -1)):
            d.rectangle((x, 50, x + 10, 86), fill=c)
            d.ellipse((x, 38, x + 10, 50), fill=(240, 190, 150) if line != 'ROUND 1' else c)
            d.rectangle((x + (10 if way > 0 else -12), 56, x + (22 if way > 0 else 0), 60), fill=c)
            d.rectangle((x - 2, 86, x + 3, 100), fill=c)
            d.rectangle((x + 7, 86, x + 12, 100), fill=c)
        if line == 'ROUND 2':
            for k in range(7):
                x, y = 36 + int(rng.integers(-12, 12)), 80 + int(rng.integers(-8, 10))
                d.ellipse((x, y, x + 9, y + 7), fill=(120, 190, 60))
        d.rectangle((8, 15, 70, 20), fill=(255, 220, 40))
        d.rectangle((90, 15, 152, 20), fill=(255, 220, 40))
    elif kind == 'blocks':
        for x in range(50, 110, 10):
            for y in range(70, H, 10):
                if rng.random() < .7:
                    d.rectangle((x, y, x + 9, y + 9), fill=tuple(int(v) for v in rng.integers(70, 256, 3)))
        for x, y in ((70, 26), (80, 26), (90, 26), (80, 36)):
            d.rectangle((x, y, x + 9, y + 9), fill=(255, 90, 200))
        d.rectangle((48, 12, 49, H), fill=(200, 200, 200))
        d.rectangle((110, 12, 111, H), fill=(200, 200, 200))
    elif kind == 'girders':
        G = (220, 60, 90)
        for k, (y0, y1) in enumerate(((36, 42), (64, 58), (80, 86), (108, 102))):
            d.line((10, y0, 150, y1), fill=G, width=3)
        for x, y0, y1 in ((132, 42, 58), (26, 62, 80), (130, 86, 102)):
            d.line((x, y0, x, y1), fill=(90, 220, 240))
            d.line((x + 5, y0, x + 5, y1), fill=(90, 220, 240))
        d.rectangle((20, 20, 40, 36), fill=(150, 80, 30))
        d.ellipse((24, 14, 36, 24), fill=(190, 120, 60))
        d.rectangle((26, 18, 34, 20), fill=(30, 30, 90))   # a tie, of course it wears a tie
        d.ellipse((70, 44, 78, 52), fill=(180, 100, 40))
        d.rectangle((110, 92, 116, 102), fill=(240, 60, 40))
    w = d.textlength(line)
    d.text(((W - w) / 2, 1), line, fill=(255, 255, 255))
    a = np.asarray(im.resize((640, 480), Image.NEAREST), np.float32)
    a[::4, :] *= .55
    Image.fromarray(a.astype('uint8')).save(f'{OUT}scr{i}.png')


def carpet():
    """That carpet: black, with planets, zigs and confetti that sang under the blacklight."""
    S = 1024
    im = Image.new('RGB', (S, S), (9, 7, 22))
    d = ImageDraw.Draw(im)
    cols = [(255, 40, 180), (40, 240, 255), (250, 240, 60), (130, 70, 255), (60, 255, 120), (255, 110, 30)]

    def wrap(fn):
        for ox in (-S, 0, S):
            for oy in (-S, 0, S):
                fn(ox, oy)
    for _ in range(90):
        x, y, r, c = rng.integers(0, S), rng.integers(0, S), rng.integers(14, 46), cols[int(rng.integers(0, 6))]
        kind = rng.integers(0, 4)
        ang = rng.random() * math.tau

        def one(ox, oy):
            X, Y = x + ox, y + oy
            if kind == 0:
                d.ellipse((X - r, Y - r, X + r, Y + r), outline=c, width=5)
                d.arc((X - r * 1.7, Y - r * .5, X + r * 1.7, Y + r * .5), 170, 370, fill=c, width=3)
            elif kind == 1:
                pts = [(X + i * r * .5 * math.cos(ang) + (i % 2) * 18 * math.sin(ang), Y + i * r * .5 * math.sin(ang) - (i % 2) * 18 * math.cos(ang)) for i in range(7)]
                d.line(pts, fill=c, width=5)
            elif kind == 2:
                for k in range(4):
                    a = ang + k * math.pi / 4
                    d.line((X - r * .7 * math.cos(a), Y - r * .7 * math.sin(a), X + r * .7 * math.cos(a), Y + r * .7 * math.sin(a)), fill=c, width=3)
            else:
                d.polygon([(X + r * .8 * math.cos(ang + k * math.tau / 3), Y + r * .8 * math.sin(ang + k * math.tau / 3)) for k in range(3)], outline=c, width=4)
        wrap(one)
    for _ in range(900):
        x, y = rng.integers(0, S), rng.integers(0, S)
        d.point((int(x), int(y)), fill=cols[int(rng.integers(0, 6))])
    im.filter(ImageFilter.GaussianBlur(.7)).save(OUT + 'carpet.png')


def sign():
    W, H = 1200, 300
    im = Image.new('RGB', (W, H), (16, 6, 34))
    d = ImageDraw.Draw(im)
    f, box = fit(d, 'COLD WEENIE', MARKER, W - 340, 170)
    d.text((300, 22), 'COLD WEENIE', font=f, fill=(255, 225, 70), stroke_width=4, stroke_fill=(220, 30, 130))
    f2, box2 = fit(d, 'ARCADE', BLACK, 500, 84)
    d.text((300 + (W - 340 - (box2[2] - box2[0])) / 2, 190), 'ARCADE', font=f2, fill=(70, 240, 255), stroke_width=2, stroke_fill=(20, 40, 120))
    # the hot dog, on its own, as ever
    d.rounded_rectangle((36, 118, 262, 182), radius=30, fill=(214, 96, 70), outline=(255, 190, 150), width=5)
    d.line([(70, 138), (228, 138)], fill=(255, 170, 130), width=5)
    im.save(OUT + 'mall_sign.png')
    im = Image.new('RGB', (520, 260), (250, 245, 225))
    d = ImageDraw.Draw(im)
    f, _ = fit(d, 'TOKENS', IMPACT, 460, 110)
    d.text((40, 16), 'TOKENS', font=f, fill=(190, 20, 30))
    f, _ = fit(d, '4 FOR $1', IMPACT, 440, 96)
    d.text((40, 136), '4 FOR $1', font=f, fill=(20, 40, 150))
    im.save(OUT + 'mall_tokens.png')
    im = Image.new('RGB', (360, 90), (232, 216, 170))
    d = ImageDraw.Draw(im)
    f, _ = fit(d, 'OUT OF ORDER', MARKER, 330, 66)
    d.text((16, 12), 'OUT OF ORDER', font=f, fill=(24, 20, 18))
    im.save(OUT + 'mall_ooo.png')


for i, g in enumerate(GAMES):
    marquee(i, *g[:5])
    screen(i, g[5], g[6])
carpet()
sign()
print('ok')

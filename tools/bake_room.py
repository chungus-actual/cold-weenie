# Finish a room's Blender passes into the launcher's assets: bloom, a calm patch for the words, dark cabinet.
import json, os, sys
import numpy as np
from PIL import Image, ImageFilter
LOOK = {  # bloom threshold, bloom amount, words patch, how dark the cabinet goes
    'neon': (150, .55, .42, .70),
    'basement': (170, .5, .46, .72),
    'rain': (205, .35, .52, .74),
    'grid': (80, .8, .58, .62),
    'mall': (150, .5, .6, .72),
}
for r in sys.argv[1:]:
    OUT = f'render/out/{r}/'
    A = f'app/src/main/assets/scenes/{r}/'
    os.makedirs(A, exist_ok=True)
    room = Image.open(OUT + 'room.png').convert('RGB')
    tv = Image.open(OUT + 'tv.png').convert('RGB')
    thr, amt, words_k, below_k = LOOK[r]
    W, H = room.size
    a = np.asarray(room, dtype=np.float32)
    has_glass = os.path.exists(OUT + 'mask.png') and r == 'rain'
    if has_glass:
        k = np.asarray(Image.open(OUT + 'mask.png').convert('RGBA'), dtype=np.float32)[..., 3:] / 255
        plate = np.asarray(Image.open(OUT + 'plate.png').convert('RGB'), dtype=np.float32)
        a = a * (1 - k) + plate * k
    bright = np.clip(a - thr, 0, 255).astype('uint8')
    g1 = np.asarray(Image.fromarray(bright).filter(ImageFilter.GaussianBlur(26)), dtype=np.float32)
    g2 = np.asarray(Image.fromarray(bright).filter(ImageFilter.GaussianBlur(7)), dtype=np.float32)
    a = a + g1 * amt + g2 * amt * .45
    if r == 'grid':
        # backlit film: the light spreads a long way into the black, and the grain is part of the picture
        g3 = np.asarray(Image.fromarray(bright).filter(ImageFilter.GaussianBlur(70)), dtype=np.float32)
        a = a + g3 * .7
        a += np.random.default_rng(82).normal(0, 3.6, a.shape[:2])[..., None]
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    j = json.load(open(OUT + 'room.json'))
    ledge = j['ledge'][1]
    below = np.clip((yy - ledge - 10) / 30, 0, 1)
    a *= (1 - below * below_k)[..., None]
    words = np.clip(1 - xx / 1020, 0, 1) ** .7 * np.clip(1 - (yy - 470) / 120, 0, 1)
    a *= (1 - words * words_k)[..., None]
    a += np.random.default_rng(7).normal(0, 1.4, a.shape[:2])[..., None]
    if has_glass:
        # what's past the glass, finished the same way as the room, and where the glass actually shows
        ys, xs = np.where(k[..., 0] > .004)
        x0, x1, y0, y1 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
        p2 = (plate * (1 - words * words_k)[..., None])[y0:y1, x0:x1]
        pim = Image.fromarray(np.clip(p2, 0, 255).astype('uint8'))
        pim.resize((1024, 512), Image.LANCZOS).save(A + 'plate.jpg', quality=90)
        pim.filter(ImageFilter.GaussianBlur(5)).resize((512, 256), Image.LANCZOS).save(A + 'platefog.jpg', quality=88)
        al = np.zeros((y1 - y0, x1 - x0, 4), np.uint8)
        al[..., :3] = 255
        al[..., 3] = np.clip(k[y0:y1, x0:x1, 0] * 255, 0, 255)
        Image.fromarray(al, 'RGBA').save(A + 'glass.png', optimize=True)
        sc = 1920 / W
        j['glass'] = [x0 * sc, y0 * sc, (x1 - x0) * sc, (y1 - y0) * sc]
    Image.fromarray(np.clip(a, 0, 255).astype('uint8')).save(A + 'room.jpg', quality=91)
    if os.path.exists(OUT + 'topdog.png'):
        d = np.asarray(Image.open(OUT + 'topdog.png').convert('RGBA'), dtype=np.float32)
        ys, xs = np.where(d[..., 3] > 4)
        x0, x1, y0, y1 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
        # darkened exactly as the room around it was
        d[..., :3] *= 1.28 * (1 - words * words_k)[..., None]   # alone in the render it lost the case's light strip and its neighbours' bounce
        Image.fromarray(np.clip(d[y0:y1, x0:x1], 0, 255).astype('uint8'), 'RGBA').save(A + 'topdog.png', optimize=True)
        sc = 1920 / W
        j['topdog'] = [x0 * sc, y0 * sc, (x1 - x0) * sc, (y1 - y0) * sc]
    # what stands in front of each path things cross on: the finished room, cut out by that pass's silhouette
    for pi, ps in enumerate(j.get('passers', [])):
        m = OUT + 'nearer%.2f.png' % ps['plane']
        al = np.asarray(Image.open(m).convert('RGBA'), dtype=np.uint8)[..., 3]
        rgba = np.dstack((np.clip(a, 0, 255).astype('uint8'), al))
        Image.fromarray(rgba, 'RGBA').crop((0, 0, W, int(ledge) + 4)).save(A + 'nearer%d.png' % pi, optimize=True)
        ps['nearer'] = 'nearer%d.png' % pi
    t = np.asarray(tv, dtype=np.float32) * (1 - below * .3)[..., None]
    Image.fromarray(np.clip(t, 0, 255).astype('uint8')).resize((960, 540), Image.LANCZOS).save(A + 'tvlight.jpg', quality=88)
    json.dump(j, open(A + 'room.json', 'w'))
    print(r, os.path.getsize(A + 'room.jpg') // 1024, 'KB')

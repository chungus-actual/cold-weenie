# The Grid room's model renders (render/grid_sprites.py) sized for the launcher, cropped close, with a glow round the lit edges.
#   python tools/finish_sprites.py <render dir>
import sys
import numpy as np
from PIL import Image, ImageFilter
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace('\\', '/') + '/'

IN = sys.argv[1]
A = ROOT + 'app/src/main/assets/scenes/grid/'
for name, height, radius in (('cycle_blue', 150, 5), ('cycle_yellow', 150, 5), ('recognizer', 620, 7)):
    im = Image.open(f'{IN}/{name}.png').convert('RGBA')
    im = im.crop(im.getchannel('A').point(lambda v: 255 if v > 8 else 0).getbbox())
    w = round(im.width * height / im.height)
    im = im.resize((w, height), Image.LANCZOS)
    pad = radius * 4
    big = Image.new('RGBA', (w + pad * 2, height + pad * 2), (0, 0, 0, 0))
    big.alpha_composite(im, (pad, pad))
    a = np.asarray(big, dtype=np.float32) / 255
    # only what's bright gives off light
    lum = a[..., :3].max(axis=2)
    keep = np.clip((lum - .82) / .15, 0, 1)[..., None]
    lit = np.dstack((a[..., :3], a[..., 3:] * keep))
    glow = Image.fromarray((lit * 255).astype('uint8'), 'RGBA').filter(ImageFilter.GaussianBlur(radius))
    out = Image.new('RGBA', big.size, (0, 0, 0, 0))
    out.alpha_composite(glow)
    out.alpha_composite(glow)
    out.alpha_composite(big)
    out.save(A + name + '.png', optimize=True)
    print(name, out.size)

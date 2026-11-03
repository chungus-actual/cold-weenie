# Cold Weenie's leanback banner and icon, from render/weenie.png (render/weenie.py). The name comes from the Neo Geo
# ad: "Would you rather be a cold weenie or a real hot dog?"
from PIL import Image, ImageDraw, ImageFont
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace('\\', '/') + '/'

A, R = ROOT + 'app/src/main/assets/', ROOT + 'app/src/main/res/drawable-xhdpi/'
PAPER = (247, 246, 240, 255)
NAME = 'Cold Weenie'

weenie = Image.open(ROOT + 'render/weenie.png').convert('RGBA')

# --- banner 320x180 @xhdpi, drawn at 640x360
b = Image.new('RGBA', (640, 360), PAPER)
b.alpha_composite(weenie.resize((640, 360), Image.LANCZOS), (0, -58))
d = ImageDraw.Draw(b)
size = 92
while d.textlength(NAME, font=ImageFont.truetype(A + 'fonts/PermanentMarker.ttf', size)) > 520:
    size -= 1
font = ImageFont.truetype(A + 'fonts/PermanentMarker.ttf', size)
tape = Image.new('RGBA', (640, 360), (0, 0, 0, 0))
td = ImageDraw.Draw(tape)
td.polygon([(28, 186), (612, 176), (618, 322), (22, 332)], fill=(226, 212, 170, 255))
td.text(((640 - d.textlength(NAME, font=font)) / 2, 254 - size * .72), NAME, font=font, fill=(26, 22, 20, 255))
b.alpha_composite(tape.rotate(.9, resample=Image.BICUBIC))
b.convert('RGB').resize((320, 180), Image.LANCZOS).save(R + 'banner.png')

# --- icon 96x96: just the weenie, on a slant
i = Image.new('RGBA', (384, 384), PAPER)
w = weenie.crop((110, 210, 1490, 570)).rotate(32, expand=True, resample=Image.BICUBIC)
w = w.resize((384, int(w.height * 384 / w.width)), Image.LANCZOS)
i.alpha_composite(w, (0, (384 - w.height) // 2))
i.convert('RGB').resize((96, 96), Image.LANCZOS).save(R + 'icon.png')

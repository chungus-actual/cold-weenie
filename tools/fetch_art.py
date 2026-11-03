# Box art and logos for a library folder, from libretro's thumbnail archive. Never replaces a file that's there.
#   python -I tools/fetch_art.py <library folder>         what would be fetched
#   python -I tools/fetch_art.py <library folder> go      fetch it, to Media/<system>/Box and Media/<system>/Logo
# The folder is the one holding Roms: Games on a drive plugged into this computer, say.
import html
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

SITE = 'https://thumbnails.libretro.com/'
ARCHIVE = {
    'nes': 'Nintendo - Nintendo Entertainment System',
    'sms': 'Sega - Master System - Mark III',
    'gb': 'Nintendo - Game Boy',
    'genesis': 'Sega - Mega Drive - Genesis',
    'lynx': 'Atari - Lynx',
    'gg': 'Sega - Game Gear',
    'snes': 'Nintendo - Super Nintendo Entertainment System',
    'saturn': 'Sega - Saturn',
    'ps1': 'Sony - PlayStation',
    'n64': 'Nintendo - Nintendo 64',
    'gbc': 'Nintendo - Game Boy Color',
    'dc': 'Sega - Dreamcast',
    'gba': 'Nintendo - Game Boy Advance',
    'gc': 'Nintendo - GameCube',
    'psp': 'Sony - PlayStation Portable',
    'arcade': 'MAME',
}
KINDS = {'Box': 'Named_Boxarts', 'Logo': 'Named_Logos'}
UA = {'User-Agent': 'ColdWeenie-fetch-art/1.0'}


def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
        except OSError:
            pass
        time.sleep(1 + i * 2)
    return None


def listing(system, kind):
    """Every picture the archive has for a system: its plain name to its file name."""
    page = get(f'{SITE}{urllib.parse.quote(ARCHIVE[system])}/{KINDS[kind]}/')
    if not page:
        return {}
    names = (html.unescape(urllib.parse.unquote(m)) for m in re.findall(r'href="([^"?/]+\.png)"', page.decode('utf8', 'replace')))
    out = {}
    for n in sorted(names, key=lambda n: ('(USA)' not in n, len(n))):
        out.setdefault(plain(n[:-4]), n)
    return out


def plain(name):
    """The name with its region tags and punctuation gone, so a dump's name meets the archive's."""
    name = re.sub(r'\s*[(\[][^)\]]*[)\]]', '', name).lower().replace('&', ' and ')
    name = re.sub(r'^(.*), (the|a|an)\b', r'\2 \1', name)
    return re.sub(r'[^a-z0-9]+', ' ', name).strip()


def rom_folder(roms, system):
    d = os.path.join(roms, system)
    return os.path.join(d, 'roms') if os.path.isdir(os.path.join(d, 'roms')) else d


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__ or 'usage: fetch_art.py <library folder> [go]')
    root = sys.argv[1].rstrip('/\\')
    go = sys.argv[2:] == ['go']
    roms = os.path.join(root, 'Roms')
    if not os.path.isdir(roms):
        sys.exit(f'no Roms folder in {root}')
    todo = []
    for system in sorted(os.listdir(roms)):
        if system not in ARCHIVE:
            print(f'{system}: skipped, not a system folder name (see docs/library.md)')
            continue
        games = sorted({os.path.splitext(f)[0] for f in os.listdir(rom_folder(roms, system)) if os.path.isfile(os.path.join(rom_folder(roms, system), f))})
        for kind in KINDS:
            have = os.path.join(root, 'Media', system, kind)
            there = {os.path.splitext(f)[0].lower() for f in os.listdir(have)} if os.path.isdir(have) else set()
            lacking = [g for g in games if g.lower() not in there]
            if not lacking:
                continue
            arch = listing(system, kind)
            found = [(system, kind, g, arch[plain(g)]) for g in lacking if plain(g) in arch]
            print(f'{system} {kind}: {len(games)} games, {len(lacking)} lack art, {len(found)} found')
            todo += found
    if not go:
        print(f'{len(todo)} to fetch. Add go to fetch them.')
        return

    def fetch(item):
        system, kind, game, name = item
        data = get(f'{SITE}{urllib.parse.quote(ARCHIVE[system])}/{KINDS[kind]}/{urllib.parse.quote(name)}')
        if not data:
            return 0
        d = os.path.join(root, 'Media', system, kind)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, game + '.png'), 'wb') as f:
            f.write(data)
        return 1

    with ThreadPoolExecutor(6) as pool:
        print(f'{sum(pool.map(fetch, todo))} of {len(todo)} fetched')


main()

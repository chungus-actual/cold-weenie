# The library

Cold Weenie reads a folder named `Games` at the top of a plugged-in drive, else `/sdcard/Games`. A folder holding a
HyperSpin layout, named `Hyperspin`, works too. Bring your own games: none come with the app.

## Layout

A template to copy is in [examples/](../examples).

```
Games/
  Roms/
    snes/
      Super Metroid (USA).sfc
    ps1/
      Vagrant Story (USA).chd
      Final Fantasy VII (USA) (Disc 1).chd
      Final Fantasy VII (USA) (Disc 2).chd
  Media/
    snes/
      Box/Super Metroid (USA).png      the tile
      Logo/Super Metroid (USA).png     the title over the room
      Video/Super Metroid (USA).mp4    plays on the TV in the room
```

Everything under `Media` is optional, and files match a ROM by name. `(Disc N)` files become one game with a disc
picker in the More menu.

| Folder | System | Files | Runs on |
|---|---|---|---|
| `arcade` | Arcade | `.zip` | RetroArch `mame2010` |
| `nes` | NES | `.nes` `.zip` | RetroArch `nestopia` |
| `sms` | Master System | `.sms` `.zip` | RetroArch `genesis_plus_gx` |
| `gb` | Game Boy | `.gb` | RetroArch `gambatte` |
| `gbc` | Game Boy Color | `.gbc` | RetroArch `gambatte` |
| `genesis` | Genesis | `.md` `.gen` `.bin` | RetroArch `genesis_plus_gx` |
| `gg` | Game Gear | `.gg` | RetroArch `genesis_plus_gx` |
| `lynx` | Lynx | `.lnx` | RetroArch `handy` |
| `snes` | Super NES | `.sfc` `.smc` | RetroArch `snes9x` |
| `saturn` | Saturn | `.cue` | RetroArch `yabasanshiro` |
| `ps1` | PlayStation | `.pbp` `.cue` `.chd` | RetroArch `pcsx_rearmed` |
| `n64` | Nintendo 64 | `.n64` `.z64` `.v64` | RetroArch `mupen64plus_next_gles3` |
| `gba` | Game Boy Advance | `.gba` | RetroArch `mgba` |
| `dc` | Dreamcast | `.chd` `.cdi` `.gdi` | Flycast |
| `gc` | GameCube | `.gcz` `.rvz` `.iso` | Dolphin |
| `psp` | PSP | `.cso` `.iso` `.chd` | PPSSPP |

## Art

```sh
python -I tools/fetch_art.py E:/Games        # what's missing and what the archive has
python -I tools/fetch_art.py E:/Games go     # fetch boxes and logos from libretro's thumbnails
```

Run it on a computer with the drive plugged in, then move the drive to the TV.

## The catalogue

With no catalogue, every game goes on the shelves, named after its file. A catalogue is how a big library gets
sorted: `library.json` in `/sdcard/ColdWeenie`, one entry per game, keyed `<folder>/<file name without extension>`.

```json
{
  "snes/Super Metroid (USA)": { "t": "Super Metroid", "y": "1994", "m": "Nintendo", "g": "Adventure", "sh": "pick", "p": 1 },
  "n64/Mario Kart 64 (USA)": { "t": "Mario Kart 64", "g": "Racing", "sh": "pick", "p": 4, "c": "parallel_n64" },
  "snes/Some Shovelware (USA)": { "sh": "back" }
}
```

| Key | What | Used for |
|---|---|---|
| `t` | Title | Tiles, search |
| `y` | Year | The info line |
| `m` | Maker | The info line, the Konami code |
| `g` | Genre | Genre pages, Because you played, Couch night |
| `p` | Most players at once | The Two players row, Couch night |
| `c` | RetroArch core for this game | Overrides the system's core |
| `sh` | Shelf | `pick`: home and Play random. `shelf`: console and genre pages only. `back`: the back room |

Every key is optional. Once a catalogue exists, a game it doesn't list goes to the back room, and an arcade zip it
doesn't list is hidden, since that zip may only be a parent set or a BIOS.

Moving a game from the More menu overrides `sh`, and is kept in `stats.json`.

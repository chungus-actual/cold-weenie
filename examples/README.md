# Example library

Copy `Games` to the top of a drive, or to `/sdcard/Games`. Copy `ColdWeenie` to `/sdcard/ColdWeenie`.

The three games here are made up and won't run. Delete them and add your own.

```
Games/
  Roms/
    snes/
      Street Farter II (USA).sfc
    ps1/
      Final Fantasy Football (USA) (Disc 1).chd
      Final Fantasy Football (USA) (Disc 2).chd
    arcade/
      mwombat.zip
  Media/
    snes/
      Box/Street Farter II (USA).jpg
      Logo/Street Farter II (USA).png
      Video/Street Farter II (USA).mp4
    ps1/
      Box/Final Fantasy Football (USA).jpg
    arcade/
      Box/mwombat.jpg
ColdWeenie/
  library.json
```

| Rule | |
|---|---|
| Art | Same name as the ROM. Leave out `(Disc N)` |
| Formats | Box and Logo: `.jpg` or `.png`. Video: `.mp4` |
| Optional | All of `Media`, and `library.json` |
| With `library.json` | Games it doesn't list go to the back room. Arcade zips it doesn't list are hidden |

System names, file types and the catalogue keys: [docs/library.md](../docs/library.md).

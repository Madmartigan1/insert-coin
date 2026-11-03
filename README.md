# Insert Coin

A controller-driven, console-style front end for [RetroArch](https://www.retroarch.com/) on Linux.
Pick a system, scroll through box art, press **A** to play — no keyboard, no menus full of settings.

**Version 0.1.0** — first release, not yet tested on real hardware.

Insert Coin is a *front end*, not an emulator. It reads RetroArch's own playlists, thumbnails,
favorites and history, and starts each game in RetroArch with the core assigned to it.
Whatever already works in RetroArch works here.

## Features

- **System carousel** — Favorites and Recently Played first, then each system with a fan of its box art,
  friendly names, and empty systems hidden.
- **Game carousel** — large box art, the game's in-game snapshot blurred behind it, and its title screen
  in a side panel; year and publisher from RetroArch's databases where known.
- **Favorites** — **Y** adds or removes a game; shared with RetroArch's own Favorites.
- **Jump by letter** — **LB / RB** skip to the previous / next letter in long lists.
- **Controller shortcuts in games** — **Select + Start** quits back to Insert Coin;
  clicking both sticks opens RetroArch's menu (save states, settings).
- **Start on login** — optional, so the machine boots straight into the game menu.

## Controls

| Controller (Xbox layout) | Keyboard | Action |
|---|---|---|
| D-pad / left stick | Arrow keys | Move (up/down skips 10 games) |
| A / Start | Enter | Open system / play game |
| B / Back | Esc / Backspace | Back · on the home screen: exit dialog |
| Y | F | Toggle favorite |
| LB / RB | Page Up / Page Down | Previous / next letter |

## Requirements

- Linux with a desktop session (tested on Ubuntu 24.04 / Cinnamon)
- RetroArch with cores installed and playlists set up (`~/.config/retroarch`)
- Thumbnails in RetroArch's thumbnails folder (see `sync_thumbnails.py` below)
- Python 3.10+ and [pygame-ce](https://pypi.org/project/pygame-ce/)

No ROMs, BIOS files or artwork are included. You must supply your own games.

## Install

```bash
# 1. A private Python environment with pygame-ce
python3 -m venv ~/.local/share/insert-coin/venv
~/.local/share/insert-coin/venv/bin/pip install pygame-ce
#    (Ubuntu without python3-pip: create the venv with --without-pip and unzip the
#     pygame-ce wheel from PyPI into the venv's site-packages instead.)

# 2. Run it
~/.local/share/insert-coin/venv/bin/python insert_coin.py
```

Options:

- `--windowed` — run in a window instead of fullscreen
- `--shot DIR` — render sample screens to PNG files without a display (for testing)

To add it to the applications menu, create `~/.local/share/applications/insert-coin.desktop`
whose `Exec=` line runs the command above; copy it to `~/.config/autostart/` to start on login.

## Thumbnails: `sync_thumbnails.py`

Downloads missing box art, snapshots and title screens for every RetroArch playlist from
`thumbnails.libretro.com` — the same source RetroArch's own updater uses. It tries the exact
name first, then a careful fuzzy match (ignoring tags like `(USA)`, preferring the same region).
It never overwrites existing images.

```bash
python3 sync_thumbnails.py --dry   # show what would be downloaded
python3 sync_thumbnails.py         # download
```

## Files written

| Path | What |
|---|---|
| `~/.local/share/insert-coin/launch.cfg` | Controller shortcuts passed to RetroArch with `--appendconfig` (RetroArch saves them into its config on exit) |
| `~/.config/retroarch/content_favorites.lpl` | Updated when you toggle a favorite (only while RetroArch is closed) |
| `~/.cache/insert-coin/meta/` | Year / publisher lookups parsed from RetroArch's `.rdb` databases |

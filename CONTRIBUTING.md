# Contributing to Insert Coin

Thanks for your interest! Insert Coin is a small hobby project, and bug reports, ideas and
pull requests are all welcome.

## Ground rules

- **Never share games, BIOS files or links to them** — not in issues, pull requests,
  screenshots or comments. Such posts will be removed.
- Be kind and constructive. Assume good intentions.
- Keep Insert Coin a **front end**: emulation, cores and per-game settings belong to RetroArch.
  Features should work *with* a user's RetroArch setup rather than replace it.

## Reporting a bug

Open an issue and include:

1. **What happened** and **what you expected**.
2. **Steps to reproduce**, as precisely as you can.
3. **Your setup**:
   - Linux distribution and version, desktop environment, X11 or Wayland
   - `retroarch --version`
   - Python version (`python3 --version`) and pygame-ce version
     (`~/.local/share/insert-coin/venv/bin/python -c "import pygame; print(pygame.version.ver)"`)
   - Controller model, if input is involved
4. **Logs**: `~/.local/state/insert-coin/insert-coin.log`, and `retroarch-last.log` beside it for
   game problems. They list your game names and paths, so trim anything you'd rather not share.
5. For game-launch problems: the **system**, the **game's playlist label**, and the **core** —
   and whether the game works when started from RetroArch directly.

## Suggesting a feature

Open an issue describing the problem it solves and how it should feel with a controller in hand.
Mock-ups or sketches are very welcome.

## Development setup

```bash
git clone https://github.com/Madmartigan1/insert-coin.git
cd insert-coin
python3 -m venv .venv
.venv/bin/pip install pygame-ce
```

Run it in a window while developing:

```bash
.venv/bin/python insert_coin.py --windowed
```

Insert Coin reads your real RetroArch setup in `~/.config/retroarch`, so you need at least one
RetroArch playlist to see anything.

### Checking your changes without a display

`--shot` renders the main screens to PNG files without opening a window — handy for checking
layout changes, and in headless environments:

```bash
.venv/bin/python insert_coin.py --shot /tmp/insert-coin-shots
```

Please look at the screenshots before submitting UI changes, and attach before/after images to
your pull request.

### Running the tests

The tests check the rules that are easy to break without noticing: hiding copies and choosing
which version leads, names and A–Z sorting, the core table, favorites and history files, the
Flash button setup, and picture loading. They use only the standard library's `unittest`, run in
a second or two, and need no RetroArch, controller or display:

```bash
.venv/bin/python -m unittest discover -s tests
```

Every test runs in a temporary home folder with a small made-up library (`tests/support.py`), so
your real RetroArch setup is never read or changed. Keep it that way: tests use fictional games
only, never names from a real collection.

### Testing game launches safely

Launching a game starts the real RetroArch with your real configuration, saves and history.
To experiment without touching them, test with a throwaway RetroArch config
(`retroarch --config=/path/to/test.cfg`) that points its save, state and system directories
somewhere temporary.

## Code guidelines

- **Small modules, few dependencies.** `insert_coin.py` starts the app; the code lives in the
  `insertcoin/` package, one module per job (listed in `insertcoin/__init__.py`): the library,
  the screens, controllers, launching games, browser games and so on. `engine.py` is the built-in
  player. Every file and folder they use is defined once in `paths.py`. The only third-party
  dependency is pygame-ce. `sync_thumbnails.py` uses only the Python standard library.
  Please discuss before adding dependencies.
- **Python 3.10+**, standard library first.
- **Never block the main loop.** Disk and network work (images, databases) goes on background
  threads; the menu should stay at 60 fps while scrolling.
- **Controller first.** Every feature must be usable with a controller alone; keyboard support
  is a bonus.
- **Don't write to RetroArch's files while RetroArch is running**, and write them atomically
  (write a temporary file, then `os.replace`).
- **Never overwrite user data** — saves, favorites, playlists or artwork — without being asked.
- Follow the style of the surrounding code; keep functions small and names descriptive.

## Pull requests

1. Fork the repository and create a branch: `git checkout -b fix/short-description`.
2. Make focused commits with clear messages (what changed and why).
3. Make sure the tests pass (`.venv/bin/python -m unittest discover -s tests`), both scripts
   still start (`python3 -m compileall -q insert_coin.py engine.py paths.py insertcoin`), and
   render the screenshots with `--shot`.
4. Update `README.md` if you change controls, options, requirements or files written.
5. Open a pull request describing the change, how you tested it, and screenshots for UI changes.

## Versioning

Insert Coin uses [semantic versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.
Before 1.0, minor versions (0.2, 0.3, …) may add features and change behaviour;
patch versions (0.1.1, …) are fixes only. The version lives in `__version__` in `insertcoin/__init__.py`.
Every release gets an entry in [CHANGELOG.md](CHANGELOG.md).

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).

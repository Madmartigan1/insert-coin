# Changelog

All notable changes to Insert Coin. Versions follow [semantic versioning](https://semver.org/);
before 1.0, minor versions add features and patch versions fix bugs.
Each version is also a [GitHub Release](https://github.com/Madmartigan1/insert-coin/releases).

## [0.3.0] — 2026-11-04 · "Sound check"

Insert Coin now sounds like a console, and keeps a record of what happened when something
goes wrong.

### New
- **Menu sound effects.** Every action has its own retro sound:
  - a soft tick as you scroll (a lower one for systems, a higher one for games);
  - a rising "bleep-bloop" to open a system, and the same falling to go back;
  - a quick swoop when jumping by letter with **LB / RB**;
  - a sparkle when a game is added to Favorites, and two falling notes when it's removed;
  - a sweep when the menu opens;
  - a "ding-ding" **coin jingle** when a game starts;
  - a low buzz when something can't be done, such as a game with no core assigned.

  Scrolling stays pleasant when you hold a direction: ticks never pile up, and the ends of a
  list are silent. All sounds are synthesised by Insert Coin itself at start-up, so the
  project ships no audio files.
- **Sound on/off.** **B** on the home screen → **Sound: On / Off**. Your choice is remembered
  in `~/.config/insert-coin/settings.json`.
- **A log for troubleshooting.** `~/.local/state/insert-coin/insert-coin.log` records each
  start-up (versions, controllers, whether audio works), every game launch with its core, how
  RetroArch ended (normally, with an error code, or crashed) and how long it ran, any errors,
  and how Insert Coin itself closed. Hard crashes are recorded too.
- **RetroArch's detailed log for each game.** Games are started with RetroArch's verbose
  logging, kept as `retroarch-last.log` and `retroarch-previous.log` beside Insert Coin's log.
  When a game fails, RetroArch's error lines are copied into `insert-coin.log` as well.

### Changed
- The menu is now **Resume · Sound · Set up controller · Exit Insert Coin**.
- Insert Coin releases the audio device while a game runs and takes it back afterwards, so it
  never competes with RetroArch for sound.
- The "No core assigned", "ROM file not found", "Close RetroArch first" and "The game closed
  straight away" messages now come with the error sound and are written to the log.

### Documentation
- This changelog.
- README: menu sounds, the new files, and troubleshooting entries for crashes, missing sound and
  N64 shooters whose sticks feel swapped.

## [0.2.1] — 2026-11-02

### Fixed
- **PS5 controllers** (DualSense and DualSense Edge): the launch screen now says
  **Create + Options**. PS4 keeps Share + Options and PS3 Select + Start.
- **USB SNES-replica pads** now follow their printed letters like a real Nintendo pad: **A**
  (right) plays, **B** (bottom) goes back, **Y** (left) adds a favorite. Before, SDL's
  position-based mapping made the button printed B act as A. Replicas are recognised by a name
  containing "SNES", "Super Nintendo" or "Super Famicom", or as the iBuffalo Classic pad.
  Nintendo's own pads are unchanged.

### Documentation
- README screenshots use fictional system names, and the Nintendo-layout row of the button
  table is called "Switch / SNES-style".

## [0.2.0] — 2026-11-02 · "Any controller"

### New
- **Button hints match your controller.** PlayStation pads show ✕ ○ △ and L1 / R1, Xbox pads
  A B Y and LB / RB, Nintendo pads A B Y and L / R, and the keyboard shows key caps. The hints
  follow whichever device you used last. The controller family is detected from its USB
  vendor, so it's right even for pads with generic names.
- **Set-up screen for unrecognised controllers.** Press any button on a pad Insert Coin doesn't
  recognise and it walks you through Up, Down, Left, Right, A and B, plus optional Y, LB and RB.
  Buttons, d-pads and sticks all work, and a button can't be given two jobs. Saved per
  controller model in `~/.config/insert-coin/controllers.json`, so it only happens once.
- **Menu on B.** On the home screen, **B** opens Resume · Set up controller · Exit Insert Coin.
- The launch screen names the right quit buttons for your controller, including
  **Select + Start** on PS3 pads.

### Documentation
- README screenshots, made from a fictional demo library with generated artwork
  (`docs/make_screenshots.py`).
- A controller section and a per-controller button table.

## [0.1.1] — 2026-11-02

### Fixed
- No more crash on setups without RetroArch playlists. Insert Coin shows a **"No games found"**
  screen explaining what to do, and **B** exits.
- `--shot` no longer assumes specific playlists or games, so it works on any setup.

### Documentation
- MIT license.
- Full README: prerequisites, step-by-step installation, artwork, usage, files read and
  written, troubleshooting, uninstall.
- Contributing guide.

## [0.1.0] — 2026-11-02 · First release

A controller-driven, console-style game menu for RetroArch on Linux.

- **System carousel** with Favorites and Recently Played, built from your RetroArch playlists.
- **Game carousel** with box art, the game's snapshot blurred in the background and its title
  screen in a side panel; year and publisher from RetroArch's databases.
- **Favorites** with **Y**, shared with RetroArch's own favorites.
- **Jump by letter** with **LB / RB**.
- **Select + Start** quits a game back to the menu; clicking both sticks opens RetroArch's menu.
- **`sync_thumbnails.py`** fills in missing box art, snapshots and title screens from
  thumbnails.libretro.com.

[0.3.0]: https://github.com/Madmartigan1/insert-coin/releases/tag/v0.3.0
[0.2.1]: https://github.com/Madmartigan1/insert-coin/releases/tag/v0.2.1
[0.2.0]: https://github.com/Madmartigan1/insert-coin/releases/tag/v0.2.0
[0.1.1]: https://github.com/Madmartigan1/insert-coin/releases/tag/v0.1.1
[0.1.0]: https://github.com/Madmartigan1/insert-coin/releases/tag/v0.1.0

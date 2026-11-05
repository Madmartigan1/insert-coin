# Changelog

All notable changes to Insert Coin. Versions follow [semantic versioning](https://semver.org/);
before 1.0, minor versions add features and patch versions fix bugs.
Each version is also a [GitHub Release](https://github.com/Madmartigan1/insert-coin/releases).

## [Unreleased]

### Changed
- **Controls** in the built-in player's pause menu is now offered for arcade and Neo Geo games
  only. Home-console games have their own button settings in their menus, so their pause menu is
  back to **Resume / Quit game**.

### Fixed
- **Messages from the emulator now appear on screen** in the built-in player, as they do in
  RetroArch. Without them there was no way to know that **LT** had switched the PC Engine pad
  to 6-button mode, in which some older games can't walk left or right.

## [0.4.2] — 2026-11-04 · "Clean exit"

### Fixed
- **The built-in player could freeze while closing a game**, leaving a blank desktop as if
  Insert Coin had quit (it was still running underneath). Closing the sound device could
  deadlock with the sound thread, and the 8-second safety exit from 0.4.1 couldn't step in. The
  player no longer closes the sound device itself: it writes the save, shuts the emulator down
  and exits, and the system releases the sound device.

## [0.4.1] — 2026-11-04 · "Button masher"

Set up the buttons for each game — handy for fighting games — and MAME's own Tab menu is back.

### New
- **Controls for each game** in the built-in player. **Select + Start** → **Controls** lists
  the game's buttons by the names the emulator gives them, with the controller button that does
  each one, shown as printed on your pad. Choose a game button, then press the one you want for
  it; the two swap, so no button is lost. Saved for that game only; **Reset to standard layout**
  undoes it.
- **The keyboard reaches the game** in the built-in player, so emulators that use it work as in
  RetroArch — **Tab** opens MAME's own menu in arcade games, including *Input (this game)*.

### Fixed
- The built-in player can no longer get stuck while closing a game: once the save is written,
  it leaves after 8 seconds even if the emulator doesn't finish shutting down.

## [0.4.0] — 2026-11-04 · "Player One"

Insert Coin can now play games itself, and big collections are much tidier to browse.

### New
- **Built-in player** *(beta)*. Insert Coin can run games without RetroArch's window. It
  loads the same emulator cores RetroArch uses and shows the picture with sharp, correctly
  proportioned pixels, plays the sound at the game's own speed and reads every controller.
  Switch it on with **B** on the home screen → **Player: Built-in (beta)**.
  - Plays NES / Famicom, SNES, Game Boy, Game Boy Color, Game Boy Advance, Mega Drive /
    Genesis, 32X, PC Engine, Neo Geo Pocket, PlayStation, Atari 2600, arcade and Neo Geo.
    N64 still opens in RetroArch.
  - **Select + Start** (or Esc) pauses the game with a **Resume / Quit game** menu.
  - Battery saves go to Insert Coin's own folder; the first time you play a game, your
    RetroArch save for it is copied in, so you carry on where you left off.
  - Uses the core options you chose in RetroArch, and RetroArch's BIOS folder.
  - Reads games in `.zip` and `.7z` archives (`.7z` needs the 7-Zip program).
  - If it can't start a game, Insert Coin opens that game in RetroArch instead.
  - Games played here appear in Recently Played.
  - Not there yet: save states, rewind, fast-forward, shaders, core options, disc swapping.
- **One entry per game.** The same game copied into several folders is now shown once, and
  its versions — regions, revisions, fan translations — are grouped under one entry. The
  best version is picked for you: one you have a save for, then a clean dump, then USA /
  World, Europe, Japan. Press **X** to choose another; the note under the game says how many
  there are and shows the button to press on *your* controller.
- **Games: One per game / Show all.** **B** on the home screen → **Games** switches between the
  tidy view and every ROM, instantly.
- **The X button** has its own hint on every controller (blue X on Xbox, pink □ on
  PlayStation, X on Switch / SNES-style, V on the keyboard), and the set-up screen for
  unrecognised pads asks for it too (optional).

### Changed
- **Select + Start now opens a menu in every game** instead of quitting straight away: the
  built-in player's pause menu, or RetroArch's *Quick Menu*, where **Close Content** returns
  you to Insert Coin. Clicking both sticks no longer opens RetroArch's menu.
- **Button hints switch as soon as you plug in a controller**, not only after you press one
  of its buttons, with a short "Controller connected" message.
- `--windowed` now runs games in a window too, RetroArch included (without changing your
  RetroArch settings).

### Fixed
- Controllers swapped while a game was running were ignored afterwards, and the hints kept
  showing the old pad's buttons. The controller list is now refreshed after every game.
- Games inside folders whose names contain `#` (common for fan-translation collections)
  failed to start, and disappeared from Favorites and Recently Played.
- The "game closed straight away" warning no longer appears when you quit a game yourself
  within a few seconds.

## [0.3.1] — 2026-11-04 · "Credit counter"

### Changed
- **A coin-up sound of its own.** Starting a game now plays six quick rising ticks, like the
  credit counter on an arcade cabinet going up, followed by a bell — in place of the two-note
  coin, which sounded too much like a famous console's. Just as arcade cabinets each had their
  own coin sound, this one is Insert Coin's.
- The sound synthesiser can now play rests and several notes at once (the bell is two waveforms
  layered together).

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

[0.3.1]: https://github.com/Madmartigan1/insert-coin/releases/tag/v0.3.1
[0.3.0]: https://github.com/Madmartigan1/insert-coin/releases/tag/v0.3.0
[0.2.1]: https://github.com/Madmartigan1/insert-coin/releases/tag/v0.2.1
[0.2.0]: https://github.com/Madmartigan1/insert-coin/releases/tag/v0.2.0
[0.1.1]: https://github.com/Madmartigan1/insert-coin/releases/tag/v0.1.1
[0.1.0]: https://github.com/Madmartigan1/insert-coin/releases/tag/v0.1.0

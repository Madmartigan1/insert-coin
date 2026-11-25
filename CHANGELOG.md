# Changelog

All notable changes to Insert Coin. Versions follow [semantic versioning](https://semver.org/);
before 1.0, minor versions add features and patch versions fix bugs.
Each version is also a [GitHub Release](https://github.com/Madmartigan1/insert-coin/releases).

## [0.8.0] — 2026-11-24 · "Third Dimension"

### Added
- **Nintendo 64 in the built-in player.** N64 games now play in Insert Coin itself, like every
  other system. Their core (Mupen64Plus-Next with GLideN64) draws on the graphics card: the
  built-in player gives it a hidden OpenGL context and shows each finished frame like any other,
  so the pause menu, save states, Continue and the picture looks all work for N64 too. It uses the
  core settings you chose in RetroArch; a setting that needs Vulkan (the ParaLLEl-RDP plugin) opens
  the game in RetroArch instead. `--cores` now installs the N64 core, and `--scan --add` can
  test-start N64 games.
- **Button layouts made in RetroArch work in the built-in player.** RetroArch's remap files (for
  one game, a folder or a whole core) are read for every system, e.g. swapped sticks for an N64
  shooter. An arcade game's own **Controls** layout still comes first.
- **Credits** section in the README: every core with its authors and license, and the libraries,
  data and documentation Insert Coin relies on.

### Changed
- The **Continue** question has a third choice, **Not now**: back to Insert Coin without starting
  the game, keeping the Continue point. **B** now means Not now (it used to start over), and
  Select + Start no longer answers the question by accident.
- On the N64 the left stick is only the stick (on other systems it also works as the d-pad), as in
  RetroArch: N64 games use the d-pad for other things.

### Notes
- An N64 Continue point runs a fifth of a second of the game out of sight before loading (the core
  takes a state back only after its first frame).
- A few N64 games may crash with the GLideN64 graphics plugin in RetroArch as well; changing the
  core's RDP plugin to angrylion in RetroArch's core options lets them run.

## [0.7.0] — 2026-11-24 · "Continue?"

### Added
- **Save states in the built-in player.** Select + Start → **Save state** keeps the whole game at
  that moment in one of 4 slots per game, each shown with a picture and the date; saving over a
  used slot asks first. **Load state** puts the game back to that moment. States are kept in
  `~/.local/share/insert-coin/states/`.
- **Continue where you left off.** Quitting a game after at least 10 seconds of play keeps a
  Continue point; the next time you start it, Insert Coin asks **Continue** (with a picture of
  where you were) or **Start over**.
- **Picture look per system.** Select + Start → **Picture** switches between **Sharp**,
  **Smoothed** and **Scanlines**, live behind the menu; the choice is kept for every game of
  that system.

### Notes
- Some MAME 2003-Plus games only take a state back once their start-up is over, so loading one
  early in a game first runs the start-up out of sight (a second or two, with *Loading…*). A few
  arcade games still don't take a state back. CPS-3 games (FB Alpha 2012) have no save states.
- Games played in RetroArch keep RetroArch's own save states.

## [0.6.2] — 2026-11-23

### Changed
- The search screen's hint line also mentions decades: "Type a game name, a year (1991), a
  decade (1990s) or a company (Capcom)".

## [0.6.1] — 2026-11-23

### Added
- **Search by year and company.** Type a year ("1991") to find the games released that year, a
  decade ("1990s"), or a developer's or publisher's name ("capcom"; from the 4th letter, so
  "capc" is enough). Mix them with words of the name to narrow it down ("capcom 1991",
  "capcom street"). Years and companies come from RetroArch's databases.
- **Browse the games beside the keyboard.** Press right at the keyboard's right edge to move onto
  the games found: up / down choose, LB / RB page, A plays, Start opens the full results list at
  that game, and left or B goes back to the keyboard.

### Changed
- The search screen says what you can type: a game name, a year or a company.

## [0.6.0] — 2026-11-20 · "Power On"

### Added
- **Insert Coin's own cores.** `insert-coin --cores` puts a copy of every core the built-in
  player uses in Insert Coin's own folder: copied from RetroArch's when it has them, downloaded
  from libretro's build server when it doesn't, and test-loaded before use. The built-in player
  then runs on these copies; RetroArch keeps its own.
- **BIOS check and Insert Coin's own BIOS folder.** `insert-coin --bios` copies RetroArch's BIOS
  folder the first time (later runs only add what's missing, never replacing a file) and reports,
  system by system, which BIOS files are there, which are the known good ones, and which games
  need the missing ones. When a Famicom Disk System or Neo Geo game won't start for lack of a
  BIOS, Insert Coin now says so.
- **Super Nintendo games with an enhancement chip** (DSP or ST01x) play in Snes9x in the built-in
  player when the chip's files aren't in the BIOS folder; before, they stopped at the start-up
  logo. `insert-coin --cores` installs Snes9x.
- **Insert Coin's own box-art folder.** The menus read pictures from Insert Coin's folder first,
  and `sync_thumbnails.py` downloads new art into it. `insert-coin --copy-art` copies RetroArch's
  art into it and checks the copy two ways (every file byte for byte, and every game's box art,
  title screen and snapshot), ending with "All checks passed."
- **Turbo buttons** in the built-in player: on two-button systems (PC Engine, NES / Famicom,
  Game Boy, Game Boy Color, Neo Geo Pocket), holding LB / RB presses the bottom / right button
  about 15 times a second. On the PC Engine the left / top face buttons are turbo buttons too.
  Games that need LB / RB themselves keep them (Famicom Disk System, Game Boy Advance, the
  Atari 2600, the PC Engine in 6-button mode).

### Changed
- `insert-coin --help` lists the new options.
- README: how to add new games, an optional link so `insert-coin` works as a terminal command,
  and sections for the cores, BIOS and art commands.

## [0.5.1] — 2026-11-20

### Added
- `insert-coin --help` (or `-h`) lists the command-line options.

### Fixed
- An option Insert Coin doesn't know (a typo such as `--hlep`, or `--help` before this
  version) opened the full-screen app. It is now refused with a message, and so are options
  that only work together (`--add` and `--retry` go with `--scan`).

## [0.5.0] — 2026-11-16 · "Game select"

### Added
- **Search.** Press **R3** (or `/` on a keyboard) to type with the pad on an on-screen keyboard;
  every word you type must start a word of the game's name, and Roman numerals match digits
  ("2" finds "II"). Results from every system appear on a Search tile at the start of the
  carousel.
- **Insert Coin's own library (beta).** In the **B** menu, *Library: Insert Coin* copies your
  RetroArch playlists into Insert Coin's own list the first time, then reads from it. Favorites
  and Recently Played are kept in Insert Coin's own lists too, and still written to RetroArch's,
  so both stay in step whichever library you use. *Library: RetroArch* works as before.
- **Scanning for games (beta).** `insert-coin --scan` looks through your game folders and reports,
  system by system, the games that aren't in your library yet. It recognises them by checksum and
  arcade set name from RetroArch's databases, sets copies and BIOS files apart, and changes
  nothing. Later scans only read what changed.
- `insert-coin --scan --add` test-starts each game found in the built-in player, with no window
  or sound, and adds the ones that start to Insert Coin's own library. RetroArch's playlists are
  not changed, the library as it was is kept beside it, and games left out are listed with the
  reason in `scan-not-added.json` (nothing is deleted). Arcade sets are tried with every arcade
  core, and Mega Drive games with PicoDrive when BlastEm can't read them. `--retry` gives games
  left out for a black screen more starts, since some start only some of the time.
- `sync_thumbnails.py` also fetches box art for the games in Insert Coin's own library.

### Changed
- The Mega Drive tile is now called "Mega Drive / Genesis".

### Fixed
- Games recorded by RetroArch in Recently Played or Favorites had no box art, year or publisher.
- Pressing Ctrl+C in the terminal of a windowed Insert Coin was logged as an error; it now closes
  quietly.

## [0.4.5] — 2026-11-13 · "Extra life"

### Fixed
- **Flash games respond to every pad button again.** Buttons whose keys were sent by the game's
  page (A in some games) stopped reaching the game on some systems, while the other buttons kept
  working. Ruffle now presses the key for every button itself, as in the first version of Flash
  support. Each button presses one key, and shortcuts a game reads as typed letters (such as
  "P = pause") don't respond to the pad.
- **Box art could stop loading for the rest of a session.** A game's background, blown up to
  cover the screen, could come out one pixel short; cutting it to size then failed and stopped
  one of the threads that load pictures. After three such games no more art appeared. The
  background now always fits, and a picture that can't be loaded no longer stops anything.
- Switching on the built-in player in the **B** menu now says which systems it covers: every
  system except Nintendo 64 (the message still named only three).

### Under the hood
- The code is split into one module per job (`insertcoin/`), with every folder defined once
  (`paths.py`), one table of emulator cores (`insertcoin/cores.py`) and a library layer that is
  the only code reading RetroArch's files (`insertcoin/retroarch.py`): groundwork for Insert
  Coin's own game library.
- **Automatic tests** (`tests/`, run with `python -m unittest discover -s tests`): names and
  sorting, copies and versions, the core table, favorites and history, Flash buttons and picture
  loading, all on a small made-up library.

## [0.4.4] — 2026-11-09 · "Free play"

### Added
- **Browser and Flash games.** Playlists of games that run in a web browser — your own HTML5
  games or old Flash (`.swf`) games — listed in `~/.config/insert-coin/browser_games.json`. They
  open full-screen in their own browser profile, served only to this computer, and
  **Select + Start** brings you back. Flash games play through Ruffle; the pad becomes the keyboard
  and mouse they expect (keys set per game), with the right stick moving a pointer for mouse-only
  menus and A to click, as in Insert Coin's menus. The keyboard and mouse keep working alongside the
  pad; a few Flash screens only react to the real keyboard. Favorites and Recently Played work for
  them too. To play Flash games, install Ruffle as described in the README.

### Fixed
- A list with a single game says "1 game", not "1 games".
- If a browser game's window was left open, the next browser game no longer closes straight away:
  the old window is closed first.

## [0.4.3] — 2026-11-04 · "Message received"

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

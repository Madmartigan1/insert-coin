"""First-run setup (1.0 step 3): everything a new computer needs, in one go. The pad screens (firstrun.py) and
`insert-coin --setup` in a terminal both use these functions, so they always do the same thing.

1. find the folders that hold game files (the home folder, plugged-in drives and disks under /mnt), for the player
   to choose from, or let them choose one by hand;
2. get the game databases (--databases), the emulator cores (--cores) and the BIOS folder (--bios, plus any BIOS
   files found in the chosen folders);
3. scan the chosen folders and add the games the databases recognise by checksum (on an empty library);
4. the rest runs in the background (`--finish-setup`): test-starting the games that need it, and box art if the
   player said yes. Its progress is written to setup-status.json, which the app shows and reloads from.

Every step can be run again: what is already there is kept."""
import json, os, shutil, subprocess, sys, threading, time
from paths import APPDIR, HERE, HOME, LIBRARY, LOGDIR
from insertcoin.logs import log

STATUS = f"{LOGDIR}/setup-status.json"          # the background run: phase, progress, result
BACKGROUND_LOG = f"{LOGDIR}/setup-background.log"
MIN_FILES = 5                                   # fewer game files than this in a folder (and below it): not suggested
SKIP = {"snap", "node_modules", "__pycache__", "site-packages", "venv", "proc", "lost+found"}
ART_MB_PER_PICTURE = 0.13                       # thumbnails.libretro.com pictures average ~130 KB


# ---------------------------------------------------------------- 1. where the games are
def game_exts():
    from insertcoin.scanner import EXT_SYSTEM, TEXT_TOO
    roms = {e for e, sy in EXT_SYSTEM.items() if sy and e not in TEXT_TOO}         # a system's own file type
    return roms, {".zip", ".7z"}


def drives():
    """Plugged-in drives (/media/<user>, /run/media/<user>) and disks mounted by hand under /mnt, if readable."""
    user = os.path.basename(HOME)
    out = []
    for base in (f"/media/{user}", f"/run/media/{user}", "/mnt"):
        try: out += sorted(e.path for e in os.scandir(base) if e.is_dir() and os.access(e.path, os.R_OK | os.X_OK))
        except OSError: pass
    return out


def subfolders(path):
    """The folders in a folder, for choosing one by hand: hidden ones left out, sorted by name."""
    try: return sorted((e.name for e in os.scandir(path) if not e.name.startswith(".") and e.is_dir()), key=str.lower)
    except OSError: return []


def count_game_files(folder, progress=None):
    """Game files in a folder and below it, by the same rules as find_game_folders."""
    roms, archives = game_exts(); exts = roms | archives
    n = seen = 0; visited = set()
    for d, dirs, files in os.walk(folder, followlinks=True):
        real = os.path.realpath(d)
        if real in visited: dirs[:] = []; continue
        visited.add(real)
        dirs[:] = [x for x in dirs if not x.startswith(".") and x not in SKIP]
        seen += 1
        if progress and seen % 500 == 0: progress(seen)
        n += sum(os.path.splitext(f)[1].lower() in exts for f in files)
    return n


def find_game_folders(roots=None, progress=None):
    """[(folder, game files, likely)] to suggest, most files first. In each place looked (the home folder, each drive)
    a folder holding game files is followed down while one subfolder holds nearly all of them, so the suggestion is
    'Documents/My Games', not 'Documents'. likely = has files of a system's own type, or many archives (a folder of only a
    few zips may be anything)."""
    roms, archives = game_exts()
    totals, direct, typed = {}, {}, {}                      # folder -> game files below it / in it / of a system's type
    seen, visited = 0, set()
    for root in roots or [HOME] + drives():
        for d, dirs, files in os.walk(root, followlinks=True):        # a linked games folder (another drive) too
            real = os.path.realpath(d)
            if real in visited: dirs[:] = []; continue                 # each folder once (no link loops)
            visited.add(real)
            dirs[:] = [x for x in dirs if not x.startswith(".") and x not in SKIP]
            seen += 1
            if progress and seen % 500 == 0: progress(seen)
            n = t = 0
            for f in files:
                e = os.path.splitext(f)[1].lower()
                if e in roms: n += 1; t += 1
                elif e in archives: n += 1
            if not n: continue
            direct[d], typed[d] = n, t
            p = d
            while True:
                totals[p] = totals.get(p, 0) + n
                if p == root or p == "/": break
                p = os.path.dirname(p)
    kids = {}
    for p in totals:
        parent = os.path.dirname(p)
        if parent != p and parent in totals: kids.setdefault(parent, []).append(p)
    def typed_below(p): return sum(typed.get(q, 0) for q in totals if q == p or q.startswith(p + os.sep))
    out = []
    for root in roots or [HOME] + drives():
        if root not in totals: continue
        starts = ([root] if direct.get(root, 0) >= MIN_FILES else []) + \
                 [k for k in kids.get(root, []) if totals[k] >= MIN_FILES]
        for c in starts:
            while c != root:                                # down while one subfolder holds nearly everything
                best = max(kids.get(c, []), key=lambda k: totals[k], default=None)
                if not best or totals[best] < 0.9 * totals[c] or direct.get(c, 0) > 0.1 * totals[c]: break
                c = best
            n = totals[c] if c != root else direct[root]
            out.append((c, n, typed_below(c) > 0 or n >= 50))
    return sorted(set(out), key=lambda x: -x[1])


# ---------------------------------------------------------------- 2. what the games need
def get_databases(progress=None):
    """(ok, note). Kept if Insert Coin already has them (run --databases to update)."""
    from insertcoin import databases
    if os.path.isfile(databases.MANIFEST): return True, "already there"
    try:
        info = databases.install(progress=lambda got, total: progress and progress(
            f"{got / 2**20:.0f} of {total / 2**20:.0f} MB" if total else f"{got / 2**20:.0f} MB"))
    except Exception as e:
        log.warning("Setup: game databases: %s", e)
        return False, f"couldn't download them: {e}"
    return True, f"{info['files']} downloaded"


def get_cores(progress=None):
    from insertcoin import coreinstall
    from insertcoin.cores import CORES
    results = coreinstall.install(progress=lambda n, t, f: progress and progress(f"{n} of {t}: {CORES[f].name}"))
    failed = [CORES[f].name for f, what, _ in results if what == "failed"]
    ready = len(results) - len(failed)
    return not failed, f"{ready} ready" + (f"; not installed: {', '.join(failed)}" if failed else "")


def find_bios(folders, progress=None):
    """Copy BIOS files found in the game folders into Insert Coin's BIOS folder: only files the table knows (by
    name), only good ones (by checksum, or a complete Neo Geo BIOS), never replacing one. Returns their names."""
    from insertcoin import bios
    wanted = {}
    for b in bios.TABLE: wanted.setdefault(os.path.basename(b.file).lower(), []).append(b)
    copied = []
    for root in folders:
        for d, dirs, files in os.walk(root):
            dirs[:] = [x for x in dirs if not x.startswith(".")]
            for f in files:
                for b in wanted.get(f.lower(), []):
                    dest = f"{bios.OWN_SYSTEM}/{b.file}"
                    if os.path.exists(dest) or bios.judge(b, os.path.join(d, f))[0] != "ok": continue
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.copy2(os.path.join(d, f), dest); copied.append(b.file)
                    if progress: progress(f"found {b.file}")
    return copied


def get_bios(folders, progress=None):
    from insertcoin import bios
    copied, _ = bios.set_up_own()                               # RetroArch's BIOS folder, if there is one
    found = find_bios(folders, progress)
    needed = [b for b, status, _, _ in bios.check(bios.OWN_SYSTEM) if b.needed and status != "ok"]
    note = f"{copied + len(found)} files" + (f" ({len(found)} found with your games)" if found else "")
    if needed: note += "; missing: " + ", ".join(f"{os.path.basename(b.file)} ({b.system})" for b in needed) + \
                       " (only some games need them)"
    return True, note


# ---------------------------------------------------------------- 3. the games
def library_is_empty():
    try:
        with open(LIBRARY) as f: doc = json.load(f)
        return not any(s.get("games") for s in doc.get("systems", []))
    except (OSError, ValueError): return True


def find_games(folders, progress=None):
    from insertcoin.scanner import scan
    report = scan(roots=folders, progress=lambda n: progress and progress(f"{n:,} files"))
    return report


def to_test(report):
    """How many games are left to test-start: those found that aren't in the library yet."""
    from insertcoin.adding import candidates
    try:
        with open(LIBRARY) as f: have = {g["path"] for s in json.load(f).get("systems", []) for g in s.get("games", [])}
    except (OSError, ValueError): have = set()
    return sum(1 for _, path, _ in candidates(report) if path not in have)


def add_recognised(report, progress=None):
    """Add the console games the databases recognise by checksum, without test starts (an empty library only;
    otherwise everything is test-started in the background). Returns how many were added."""
    from insertcoin import adding
    from paths import RA
    if not library_is_empty(): return 0
    if not os.path.exists(LIBRARY) and os.path.isdir(f"{RA}/playlists"): return 0     # it starts as RetroArch's games
    keep = adding.recognised(report)
    only = {"systems": {sy: dict(s, new=[x for x in s["new"] if x["path"] in keep], by_type=[])
                        for sy, s in report["systems"].items()}}
    result = adding.add_found(only, progress=lambda n, t: progress and progress(f"{n:,} of {t:,}"))
    return sum(result["added"].values())


def use_own_library():
    """The games are in Insert Coin's own library: show that one from now on."""
    from insertcoin.settings import load_settings, save_settings
    s = load_settings()
    if s.get("library") != "insertcoin": s["library"] = "insertcoin"; save_settings(s)


# ---------------------------------------------------------------- box art
def art_estimate():
    """(pictures to download, MB) from a dry run of sync_thumbnails.py (it asks the art server what it has)."""
    r = subprocess.run([sys.executable, f"{HERE}/sync_thumbnails.py", "--dry"], capture_output=True, text=True, timeout=900)
    for ln in r.stdout.splitlines():
        if ln.startswith("TOTAL downloads:"):
            n = int(ln.split(":")[1].split()[0]); mb = int(ln.rsplit("~", 1)[1].split()[0])
            return n, mb
    raise RuntimeError((r.stderr or r.stdout).strip()[-200:] or "no answer from the art server")


def get_art(out=None):
    """Download the missing pictures (sync_thumbnails.py). Returns its exit code."""
    return subprocess.run([sys.executable, f"{HERE}/sync_thumbnails.py"], stdout=out, stderr=subprocess.STDOUT).returncode


# ---------------------------------------------------------------- 4. the background run
def write_status(**kw):
    os.makedirs(LOGDIR, exist_ok=True)
    tmp = STATUS + ".tmp"
    with open(tmp, "w") as f: json.dump(kw, f)
    os.replace(tmp, STATUS)


def read_status():
    try:
        with open(STATUS) as f: return json.load(f)
    except (OSError, ValueError): return None


def running(st):
    """Is the background run this status describes still going?"""
    if not st or st.get("phase") == "done": return False
    try: os.kill(int(st.get("pid", 0)), 0); return True
    except (OSError, ValueError, TypeError): return False


def start_background(folders, art=False):
    """Start the background run (test starts, then box art) as its own process, so it carries on if Insert Coin
    is closed. Returns its process id."""
    os.makedirs(LOGDIR, exist_ok=True)
    out = open(BACKGROUND_LOG, "w")
    env = dict(os.environ, INSERT_COIN_SETUP_ART="1" if art else "")
    p = subprocess.Popen([sys.executable, f"{HERE}/insert_coin.py", "--finish-setup", *folders], stdout=out,
                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env, start_new_session=True)
    write_status(pid=p.pid, phase="starting", n=0, total=0, art=art, started=time.time())
    log.info("Setup: background run started (pid %d): %s%s", p.pid, ", ".join(folders), ", with box art" if art else "")
    return p.pid


def finish(folders, art=False, out=None):
    """The background run: test-start the games that need it and add those that start, and (art) download box art
    alongside, then once more for the games added. Writes its progress to setup-status.json."""
    from insertcoin import adding
    from insertcoin.scanner import scan
    base = dict(pid=os.getpid(), art=art, started=time.time())
    write_status(**base, phase="tests", n=0, total=0)
    art_job = None
    if art:                                  # network while the test starts use the processors
        art_job = threading.Thread(target=get_art, args=(out,), daemon=True); art_job.start()
    last = [0.0]
    def progress(n, t):
        if time.time() - last[0] > 1 or n == t: last[0] = time.time(); write_status(**base, phase="tests", n=n, total=t)
    report = scan(roots=folders)                                    # cached: only the folder listing
    result = adding.add_found(report, progress=progress)
    added = sum(result["added"].values())
    if art_job:
        write_status(**base, phase="art", n=0, total=0, added=added)
        art_job.join(); get_art(out)                                # and the pictures for the games just added
    write_status(**base, phase="done", added=added, not_added=len(result["not_added"]), finished=time.time())
    log.info("Setup: background run done: %d added, %d not added", added, len(result["not_added"]))
    return result


# ---------------------------------------------------------------- the terminal route: insert-coin --setup
STEPS = (("databases", "Game databases"), ("cores", "Emulator cores"), ("bios", "BIOS files"),
         ("scan", "Finding your games"), ("add", "Adding the games the databases recognise"))


def choose_folders(found, answer):
    """The folders a typed answer picks from the numbered list: numbers ("1 3"), folder paths, or nothing (the
    ones marked likely). Returns (folders, problem)."""
    words = answer.split() if answer.strip() else []
    if not words: return [f for f, _, likely in found if likely], None
    if os.path.isdir(os.path.expanduser(answer.strip())): return [os.path.abspath(os.path.expanduser(answer.strip()))], None
    out = []
    for w in words:
        if w.isdigit() and 1 <= int(w) <= len(found): out.append(found[int(w) - 1][0])
        elif os.path.isdir(os.path.expanduser(w)): out.append(os.path.abspath(os.path.expanduser(w)))
        else: return [], f"not a number from the list or a folder: {w}"
    return list(dict.fromkeys(out)), None


def terminal(folders, ask=input, interactive=None):
    """insert-coin --setup [FOLDER...]: the same setup in the terminal. Everything runs here, test starts too."""
    from insertcoin.app import Progress
    from insertcoin import adding
    from insertcoin.scanner import summary
    interactive = sys.stdin.isatty() if interactive is None else interactive
    line = Progress()
    print("Insert Coin setup\n")
    if not folders:
        print("Looking for folders with game files (your home folder and drives)...")
        found = find_game_folders(progress=lambda n: line.show(f"  {n:,} folders..."))
        line.clear()
        if not found:
            print("No game files were found. Put your games in a folder (for example ~/Games) and run\n"
                  "  insert-coin --setup ~/Games"); return 2
        for k, (f, n, likely) in enumerate(found, 1):
            print(f"  {'*' if likely else ' '} {k}. {f.replace(HOME, '~', 1)}  ({n:,} game files)")
        while True:
            answer = ask("\nWhich folders hold your games? Numbers (e.g. 1 3) or a folder; Enter for the ones marked *: ") \
                if interactive else ""
            folders, problem = choose_folders(found, answer)
            if problem: print(problem); continue
            if folders: break
            print("Nothing chosen."); 
            if not interactive: return 2
    print("\nUsing: " + ", ".join(f.replace(HOME, "~", 1) for f in folders) + "\n")
    steps = {"databases": lambda p: get_databases(p), "cores": lambda p: get_cores(p), "bios": lambda p: get_bios(folders, p)}
    for key, title in STEPS[:3]:
        ok, note = steps[key](lambda t: line.show(f"  {title}: {t}"))
        line.clear(); print(f"{'ok' if ok else '!!'}  {title}: {note}")
    report = find_games(folders, lambda t: line.show(f"  Finding your games: {t}"))
    line.clear(); print(f"ok  Finding your games\n\n{summary(report)}\n")
    quick = add_recognised(report, lambda t: line.show(f"  Adding: {t}"))
    line.clear()
    if quick: print(f"ok  {quick:,} games the databases recognise were added straight away")
    use_own_library()
    n = to_test(report)
    if n:
        print(f"\nTest-starting {n:,} more games (60 seconds of game time each, no window or sound)...")
        result = adding.add_found(report, progress=lambda a, t: line.show(f"  {a:,} of {t:,}..."))
        line.clear(); print(adding.summary(result))
    if interactive:
        try:
            print("\nAsking the box-art server what it has for your games...")
            pics, mb = art_estimate()
            if pics and ask(f"Download box art: {pics:,} pictures, about {mb:,} MB? [y/N] ").strip().lower() in ("y", "yes"):
                get_art()
            elif not pics: print("Every game that has box art on the server already has it.")
        except Exception as e:
            print(f"Box art: couldn't reach the art server ({e}). Later: python3 sync_thumbnails.py")
    print("\nDone. Start Insert Coin to play.")
    return 0

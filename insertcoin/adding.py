"""Adding the games the scanner found (step 4b): each one is test-started first, and only games that start are
added to Insert Coin's own library (library.json). RetroArch's playlists are not changed.

A test start runs the game in the built-in player with no window, sound, saves or controllers, for 60 seconds of
game time (a few seconds of real time), pressing Start, A and B along the way. It passes if any frame it looks at
shows something: games without box art, or with a dark title screen, still count. It fails only if the game
can't be loaded, the player stops with an error, or the screen stays black the whole time (twice: some cores
fill the console's memory with random values at power-on, and a few games start only some of the time).

FBNeo is a special case: it "starts" an arcade set with files missing and shows its own error screen, so a
set it says files are required for fails too. Games added by an earlier run are tested again when these rules
change, and taken out of the library again if they now fail (their files stay where they are).

A library built from scratch (no games in it yet, e.g. on a computer without RetroArch) takes the console games
the databases recognise by their checksum straight in, without a test start: they are known, good dumps. Arcade
sets (a set may lack files) and games known only by their file type are still test-started.

Games that fail are never deleted: they are listed, with the reason, in scan-not-added.json. Games whose core
the built-in player can't run are listed there as "not tested" (none since 0.8, when N64 joined). Results are kept by file
size and time (and the cores tried), so running it again only tests what is new or changed. With retry, the
games left out for a black screen are started again, up to RETRY_STARTS times each, and added if one start
shows something."""
import os, shutil, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor
from paths import APPDIR, CACHE, CORES_DIR, HERE, LIBRARY, RA, SYSTEM
from insertcoin.coreinstall import own_core
from insertcoin.cores import DEFAULT_CORE, core_file, is_builtin
from insertcoin.logs import log
from insertcoin.names import split_archive
from insertcoin.ownlib import import_retroarch, new_library, save
from insertcoin.retroarch import read_json

VERSION = 1
RULES = 2               # how test starts are judged; results judged by older rules are tested again (2: FBNeo's missing files)
NOT_ADDED = f"{APPDIR}/scan-not-added.json"
RESULTS = f"{CACHE}/test-starts.json"                                   # path -> size, time, core, result
FRAMES = 3600                                                           # 60 seconds of game time
PRESSES = ("start@300-306", "a@900-906", "b@1500-1506", "start@2100-2106", "a@2700-2706", "b@3300-3306")
TIMEOUT = 180                                                           # seconds of real time for one test start
RETRY_STARTS = 6                                                        # starts per core for a black-screen game, with retry
# arcade sets: the playlist's own core first, then the other arcade cores (a set may only run in one of them)
ARCADE_CORES = {"MAME 2003-Plus": ("mame2003_plus_libretro.so", "mame2003_libretro.so", "fbneo_libretro.so",
                                   "fbalpha2012_cps3_libretro.so"),
                "FBNeo - Arcade Games": ("fbneo_libretro.so", "mame2003_plus_libretro.so", "mame2003_libretro.so",
                                         "fbalpha2012_cps3_libretro.so")}   # CPS-3: older CPS-3 sets FBNeo can't load
# consoles: a second core tried when the playlist's own can't start a game (BlastEm can't read interleaved .smd
# files; PicoDrive can, and plays Mega Drive games too; some Super Nintendo betas start only in Snes9x)
SECOND_CORES = {"Sega - Mega Drive - Genesis": ("picodrive_libretro.so",),
                "Nintendo - Super Nintendo Entertainment System": ("snes9x_libretro.so",)}


def candidates(report):
    """The games worth adding, from a scan report: the new ones and those known by file type (not copies, BIOS
    files or unknown files). [(system, path, label)]"""
    out = []
    for sy, s in sorted(report["systems"].items()):
        for x in s["new"] + s["by_type"]:
            archive, inner = split_archive(x["path"])
            label = x.get("name") or os.path.splitext(os.path.basename(inner or archive))[0]
            out.append((sy, x["path"], label))
    return out


def core_folder(f=None):
    """Where cores are looked for: RetroArch's folder where it has the core (or any, with no file named), else
    Insert Coin's own (a computer without RetroArch)."""
    ra = f"{RA}/cores"
    return ra if (os.path.exists(f"{ra}/{f}") if f else os.path.isdir(ra)) else CORES_DIR


def cores_to_try(system, defaults):
    """The cores a game of this playlist is tried with, in order: full paths."""
    d = defaults.get(system) or (f"{core_folder(DEFAULT_CORE[system])}/{DEFAULT_CORE[system]}" if system in DEFAULT_CORE else None)
    files = ARCADE_CORES.get(system) or (((core_file(d),) if d else ()) + SECOND_CORES.get(system, ()))
    folder = os.path.dirname(d) if d else core_folder()
    return [f"{folder}/{f}" if os.path.exists(f"{folder}/{f}") or not d else f"{core_folder(f)}/{f}" for f in files]


def same_tries(result, now):
    """Is a test result still good for the cores tried now? The same list, or (for a game that started) the same
    cores up to the one that started it, so a core added at the end doesn't test every game again."""
    if result.get("tries") == now: return True
    core, before = result.get("core"), result.get("tries") or []
    if not result.get("passed") or core not in now or core not in before: return False
    i = now.index(core)
    return before[:i + 1] == now[:i + 1]


FBNEO = "fbneo_libretro.so"
_fbneo_sets = None


def fbneo_sets():
    """The set names FBNeo's database knows (RetroArch's copy and Insert Coin's). FBNeo loads a set only by a name it
    knows; for any other it draws its own 'Romset is unknown' screen, which a test start would take for a game."""
    global _fbneo_sets
    if _fbneo_sets is None:
        from insertcoin.databases import rdb_paths
        from insertcoin.meta import _rdb_load
        _fbneo_sets = {(r.get("rom_name") or "").lower()[:-4] for p in rdb_paths("FBNeo - Arcade Games")
                       for r in _rdb_load(p) if (r.get("rom_name") or "").lower().endswith(".zip")}
    return _fbneo_sets


def fbneo_unknown(path):
    """An arcade zip whose set name FBNeo doesn't know (only when its database is there to ask)."""
    archive, inner = split_archive(path)
    if inner or not archive.lower().endswith(".zip"): return False
    known = fbneo_sets()
    return bool(known) and os.path.splitext(os.path.basename(archive))[0].lower() not in known


def false_pass(result, path):
    """A start that 'passed' on FBNeo's own error screen (a set FBNeo doesn't know): to be tested again."""
    return bool(result.get("passed") and core_file(result.get("core") or "") == FBNEO and fbneo_unknown(path))


def recognised(report):
    """Console games the databases know by their checksum (not arcade sets): paths."""
    return {x["path"] for sy, s in report["systems"].items() if sy not in ARCADE_CORES for x in s["new"] if x.get("name")}


def test_start(core, rom, env):
    """Start one game in the built-in player's test mode. Returns (passed, why)."""
    cmd = [sys.executable, f"{HERE}/engine.py", core, rom, "--probe", "--frames", str(FRAMES)]
    for p in PRESSES: cmd += ["--press", p]
    try: r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired: return False, f"did not finish within {TIMEOUT} s"
    out = r.stdout + r.stderr
    lit = next((ln for ln in out.splitlines() if "Probe: " in ln), "")
    if r.returncode < 0: return False, f"crashed (signal {-r.returncode})"
    # FBNeo still "starts" a set with files missing: it shows its own error screen, and logs "... is required"
    if any("[FBNeo]" in ln and "is required" in ln for ln in out.splitlines()):
        return False, "missing ROM files: FBNeo says some of the set's files are required"
    if r.returncode or not lit:
        err = next((ln for ln in out.splitlines() if ln.startswith("[ERROR]")), "") or out.strip()[-200:]
        return False, ("could not be loaded: " if "load" in err.lower() or "not found" in err.lower() else
                       "stopped with an error: ") + err.replace("[ERROR] ", "")[:200]
    n = int(lit.split("Probe: ", 1)[1].split()[0])
    return (True, "started") if n else (False, "black screen for 60 seconds")


def sandbox():
    """A throwaway place for the test starts: own save, BIOS (a copy) and settings folders."""
    tmp = tempfile.mkdtemp(prefix="insert-coin-test-starts-")
    shutil.copytree(SYSTEM, f"{tmp}/system", symlinks=True) if os.path.isdir(SYSTEM) else os.makedirs(f"{tmp}/system")
    env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy", INSERT_COIN_SAVES=f"{tmp}/saves",
               INSERT_COIN_SYSTEM=f"{tmp}/system", INSERT_COIN_CONFIG=f"{tmp}/config")
    return tmp, env


def add_found(report, starter=test_start, workers=None, progress=None, retry=False):
    """Test-start every candidate in the report, add those that start to library.json, list the rest. With retry,
    games left out earlier for a black screen get up to RETRY_STARTS starts per core.
    Returns a summary: {"added": {system: n}, "not_added": [...], "tested": n, "retried": n, "backup": path or None}."""
    t0 = time.time()
    if not os.path.exists(LIBRARY):
        import_retroarch() if os.path.isdir(f"{RA}/playlists") else new_library()
    doc = read_json(LIBRARY)
    if not isinstance(doc, dict) or not isinstance(doc.get("systems"), list):
        raise ValueError(f"{LIBRARY} couldn't be read: nothing was added")
    # a library built from scratch: recognised console games go straight in (see the top of this file)
    trusted = recognised(report) if not any(s.get("games") for s in doc["systems"]) else set()
    defaults = {s["name"]: s.get("default_core") for s in doc["systems"]}
    have = {g["path"] for s in doc["systems"] for g in s.get("games", [])}
    todo = [c for c in candidates(report) if c[1] not in have]
    earlier = [(s["name"], g["path"], g["label"]) for s in doc["systems"] for g in s.get("games", []) if g.get("added")]

    old = read_json(RESULTS) or {}
    known = old.get("games", {}) if old.get("version") == VERSION else {}
    def stamp(path):
        try: st = os.stat(split_archive(path)[0]); return [st.st_size, int(st.st_mtime)]
        except OSError: return None

    def still_good(sy, path):                       # tested before: same file, same cores, same rules
        k = known.get(path)
        return (k and k.get("file") == stamp(path) and same_tries(k, cores_to_try(sy, defaults)) and k.get("rules") == RULES
                and not false_pass(k, path))
    def was_black(k):                                # left out because a core showed only a black screen
        return not k["passed"] and (k.get("black") or k.get("why", "").startswith("black"))
    results, jobs, retried = {}, [], set()
    for sy, path, label in todo:
        if still_good(sy, path) and not (retry and was_black(known[path])): results[path] = known[path]
        else:
            jobs.append((sy, path, label))
            if retry and still_good(sy, path): retried.add(path)
    def judged_now(path):                            # added by an earlier run: tested again only if the file or rules changed
        k = known.get(path)
        return k and k.get("file") == stamp(path) and k.get("rules") == RULES and not false_pass(k, path)
    recheck = [g for g in earlier if not judged_now(g[1])]
    jobs += recheck

    tmp, env = sandbox() if jobs else (None, None)
    def run(job):
        sy, path, label = job
        tries = cores_to_try(sy, defaults)
        if path in trusted and tries:
            return path, {"file": stamp(path), "tries": tries, "rules": RULES, "passed": True, "core": tries[0],
                          "why": "recognised by its checksum (not test-started)", "trusted": True}
        if not tries or not is_builtin(tries[0]):
            return path, {"file": stamp(path), "tries": tries, "rules": RULES, "passed": False, "core": tries[0] if tries else None,
                          "why": "not tested: the built-in player can't run this system's core yet"}
        why, first, tried, black = "no core for this system", None, [], False
        starts = RETRY_STARTS if path in retried else 2       # some cores start with random memory: black isn't final
        for core in tries:
            if not os.path.exists(own_core(core)): why = f"core not installed: {core_file(core)}"; continue
            if core_file(core) == FBNEO and fbneo_unknown(path):
                why = "not a set FBNeo knows"; tried.append("fbneo"); first = first or why; continue
            ok, why = starter(own_core(core), path, env)
            for _ in range(starts - 1):
                if ok or not why.startswith("black"): break
                black = True
                ok, why = starter(own_core(core), path, env)
            if ok: return path, {"file": stamp(path), "tries": tries, "rules": RULES, "passed": True, "core": core}
            black = black or why.startswith("black")
            tried.append(core_file(core).replace("_libretro.so", ""))
            first = first or why                              # the reason its own core gave is the one that matters
        if first and len(tried) > 1: why = f"{first} (also tried: {', '.join(tried[1:])})"
        return path, {"file": stamp(path), "tries": tries, "rules": RULES, "passed": False, "core": tries[0], "why": why,
                      "black": black}
    try:
        with ThreadPoolExecutor(workers or max(1, (os.cpu_count() or 2) - 1)) as pool:
            for n, (path, res) in enumerate(pool.map(run, jobs), 1):
                results[path] = res
                if progress: progress(n, len(jobs))
    finally:
        if tmp: shutil.rmtree(tmp, ignore_errors=True)
    known.update(results)
    save(RESULTS, {"version": VERSION, "games": known})

    added, not_added, backup, taken_out = {}, [], None, {}
    by_name = {s["name"]: s for s in doc["systems"]}
    for sy, path, label in recheck:                  # added earlier, but don't pass now: out of the library again
        res = results[path]
        if res["passed"]: continue
        s = by_name[sy]; s["games"] = [g for g in s["games"] if not (g["path"] == path and g.get("added"))]
        not_added.append({"system": sy, "path": path, "name": label, "core": res.get("core"), "why": res["why"]})
        taken_out[sy] = taken_out.get(sy, 0) + 1
    for sy, path, label in todo:
        res = results[path]
        if not res["passed"]:
            not_added.append({"system": sy, "path": path, "name": label, "core": res.get("core"), "why": res["why"]})
            continue
        s = by_name.get(sy)
        if s is None:
            s = by_name[sy] = {"name": sy, "default_core": (cores_to_try(sy, defaults) or [None])[0], "games": []}
            doc["systems"].append(s)
        core = res["core"]
        s["games"].append({"label": label, "path": path,
                           "core": None if core == s.get("default_core") else core, "db": f"{sy}.lpl",
                           "added": time.strftime("scan %Y-%m-%d")})
        added[sy] = added.get(sy, 0) + 1
    if added or taken_out:
        backup = f"{LIBRARY}.pre-scan-{time.strftime('%Y-%m-%d-%H%M%S')}"
        shutil.copy2(LIBRARY, backup)
        save(LIBRARY, doc)
    save(NOT_ADDED, {"version": VERSION, "updated": round(time.time()),
                     "about": "Games the scanner found that were not added, and why. Nothing here was deleted.",
                     "games": not_added})
    log.info("Scan: tested %d new games (%d now, %.0f s); added %d; taken out %d; not added %d%s", len(todo), len(jobs),
             time.time() - t0, sum(added.values()), sum(taken_out.values()), len(not_added),
             f"; backup {backup}" if backup else "")
    trusted_n = sum(1 for _, p, _ in todo if results[p].get("trusted"))
    return {"added": added, "taken_out": taken_out, "not_added": not_added, "tested": len(todo) + len(recheck) - trusted_n,
            "started_now": len([j for j in jobs if j[1] not in trusted]), "retried": len(retried), "backup": backup,
            "recognised": trusted_n}


def summary(result):
    from insertcoin.systems import FRIENDLY
    name = lambda sy: FRIENDLY.get(sy, (sy,))[0]
    lines = [f"Test-started {result['tested']:,} games ({result['started_now']:,} now, the rest from earlier runs)."]
    if result.get("recognised"):
        lines.append(f"{result['recognised']:,} console games recognised by their checksum went straight in (a new library).")
    if result.get("retried"):
        lines.append(f"{result['retried']:,} of them had shown a black screen before and got up to {RETRY_STARTS} starts each.")
    if result["added"]:
        lines += ["", "Added to Insert Coin's library (B menu > Library: Insert Coin):"]
        lines += [f"  {name(sy)}: {n:,}" for sy, n in sorted(result["added"].items(), key=lambda x: name(x[0]))]
    else:
        lines += ["", "Nothing was added."]
    if result.get("taken_out"):
        lines += ["", "Taken out again (added by an earlier run, but they don't pass today's test start):"]
        lines += [f"  {name(sy)}: {n:,}" for sy, n in sorted(result["taken_out"].items(), key=lambda x: name(x[0]))]
    if result["backup"]: lines.append(f"The library before this: {result['backup']}")
    why = {}
    for g in result["not_added"]:
        k = g["why"].split(" (also tried")[0].split(":")[0]; why[k] = why.get(k, 0) + 1
    if result["not_added"]:
        lines += ["", f"Not added: {len(result['not_added']):,} (" + ", ".join(f"{w}: {n}" for w, n in sorted(why.items())) + ")",
                  f"Their list, with the reasons: {NOT_ADDED}"]
    if os.path.isdir(f"{RA}/playlists"): lines.append("RetroArch's playlists were not changed.")
    return "\n".join(lines)

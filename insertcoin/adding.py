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

Games that fail are never deleted: they are listed, with the reason, in scan-not-added.json. Games whose core
the built-in player can't run (Nintendo 64) are listed there as "not tested" for now. Results are kept by file
size and time (and the cores tried), so running it again only tests what is new or changed."""
import os, shutil, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor
from paths import APPDIR, CACHE, HERE, LIBRARY, RA, SYSTEM
from insertcoin.cores import DEFAULT_CORE, core_file, is_builtin
from insertcoin.logs import log
from insertcoin.names import split_archive
from insertcoin.ownlib import import_retroarch, save
from insertcoin.retroarch import read_json

VERSION = 1
RULES = 2               # how test starts are judged; results judged by older rules are tested again (2: FBNeo's missing files)
NOT_ADDED = f"{APPDIR}/scan-not-added.json"
RESULTS = f"{CACHE}/test-starts.json"                                   # path -> size, time, core, result
FRAMES = 3600                                                           # 60 seconds of game time
PRESSES = ("start@300-306", "a@900-906", "b@1500-1506", "start@2100-2106", "a@2700-2706", "b@3300-3306")
TIMEOUT = 180                                                           # seconds of real time for one test start
# arcade sets: the playlist's own core first, then the other arcade cores (a set may only run in one of them)
ARCADE_CORES = {"MAME 2003-Plus": ("mame2003_plus_libretro.so", "mame2003_libretro.so", "fbneo_libretro.so"),
                "FBNeo - Arcade Games": ("fbneo_libretro.so", "mame2003_plus_libretro.so", "mame2003_libretro.so")}
# consoles: a second core tried when the playlist's own can't start a game (BlastEm can't read interleaved .smd
# files; PicoDrive can, and plays Mega Drive games too)
SECOND_CORES = {"Sega - Mega Drive - Genesis": ("picodrive_libretro.so",)}


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


def cores_to_try(system, defaults):
    """The cores a game of this playlist is tried with, in order: full paths."""
    d = defaults.get(system) or (f"{RA}/cores/{DEFAULT_CORE[system]}" if system in DEFAULT_CORE else None)
    files = ARCADE_CORES.get(system) or (((core_file(d),) if d else ()) + SECOND_CORES.get(system, ()))
    folder = os.path.dirname(d) if d else f"{RA}/cores"
    return [f"{folder}/{f}" for f in files]


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


def add_found(report, starter=test_start, workers=None, progress=None):
    """Test-start every candidate in the report, add those that start to library.json, list the rest.
    Returns a summary: {"added": {system: n}, "not_added": [...], "tested": n, "backup": path or None}."""
    t0 = time.time()
    if not os.path.exists(LIBRARY): import_retroarch()
    doc = read_json(LIBRARY)
    if not isinstance(doc, dict) or not isinstance(doc.get("systems"), list):
        raise ValueError(f"{LIBRARY} couldn't be read: nothing was added")
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
        return k and k.get("file") == stamp(path) and k.get("tries") == cores_to_try(sy, defaults) and k.get("rules") == RULES
    results, jobs = {}, []
    for sy, path, label in todo:
        if still_good(sy, path): results[path] = known[path]
        else: jobs.append((sy, path, label))
    def judged_now(path):                            # added by an earlier run: tested again only if the file or rules changed
        k = known.get(path)
        return k and k.get("file") == stamp(path) and k.get("rules") == RULES
    recheck = [g for g in earlier if not judged_now(g[1])]
    jobs += recheck

    tmp, env = sandbox() if jobs else (None, None)
    def run(job):
        sy, path, label = job
        tries = cores_to_try(sy, defaults)
        if not tries or not is_builtin(tries[0]):
            return path, {"file": stamp(path), "tries": tries, "rules": RULES, "passed": False, "core": tries[0] if tries else None,
                          "why": "not tested: the built-in player can't run this system's core yet"}
        why, first, tried = "no core for this system", None, []
        for core in tries:
            if not os.path.exists(core): why = f"core not installed: {core_file(core)}"; continue
            ok, why = starter(core, path, env)
            if not ok and why.startswith("black"):                 # once more: some cores start with random memory
                ok, why = starter(core, path, env)
            if ok: return path, {"file": stamp(path), "tries": tries, "rules": RULES, "passed": True, "core": core}
            tried.append(core_file(core).replace("_libretro.so", ""))
            first = first or why                              # the reason its own core gave is the one that matters
        if first and len(tried) > 1: why = f"{first} (also tried: {', '.join(tried[1:])})"
        return path, {"file": stamp(path), "tries": tries, "rules": RULES, "passed": False, "core": tries[0], "why": why}
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
    return {"added": added, "taken_out": taken_out, "not_added": not_added, "tested": len(todo) + len(recheck),
            "started_now": len(jobs), "backup": backup}


def summary(result):
    from insertcoin.systems import FRIENDLY
    name = lambda sy: FRIENDLY.get(sy, (sy,))[0]
    lines = [f"Test-started {result['tested']:,} games ({result['started_now']:,} now, the rest from earlier runs)."]
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
    lines.append("RetroArch's playlists were not changed.")
    return "\n".join(lines)

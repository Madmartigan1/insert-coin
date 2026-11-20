"""Insert Coin's own box-art folder (0.6 step 3).

The menus read a game's pictures from ~/.local/share/insert-coin/thumbnails/ first, then from RetroArch's
thumbnails folder (retroarch.thumb_path); sync_thumbnails.py downloads new ones into Insert Coin's folder. Both
folders have RetroArch's layout: <system>/<Named_Boxarts|Named_Titles|Named_Snaps>/<label>.png.

`insert-coin --copy-art` copies RetroArch's pictures into Insert Coin's folder (never replacing one, never
changing RetroArch's folder), then checks the copy two ways: every file is compared byte for byte with
RetroArch's, and every game in the library is looked up in both folders, so the pictures each game shows are
proven to be the same before RetroArch's folder is retired."""
import filecmp, os, shutil
from paths import RA_THUMBNAILS, THUMBNAILS
from insertcoin.retroarch import thumb_rel

KINDS = ("Named_Boxarts", "Named_Titles", "Named_Snaps")


def same_folder(a, b):
    return os.path.isdir(a) and os.path.isdir(b) and os.path.samefile(a, b)


def pictures(root):
    """Every file under an art folder, as paths relative to it."""
    out = []
    for d, _, files in os.walk(root):
        rel = os.path.relpath(d, root)
        out += [os.path.normpath(os.path.join(rel, f)) for f in files if not f.endswith(".part")]
    return sorted(out)


def size_of(root, files):
    return sum(os.path.getsize(os.path.join(root, f)) for f in files)


def copy(src=None, dst=None, progress=None):
    """Copy every picture in src that dst lacks. Returns (copied, kept, failed: [(file, reason)])."""
    src, dst = src or RA_THUMBNAILS, dst or THUMBNAILS
    files = pictures(src)
    copied, kept, failed = 0, 0, []
    for n, f in enumerate(files, 1):
        if progress and (n % 500 == 0 or n == len(files)): progress(n, len(files))
        target = os.path.join(dst, f)
        if os.path.lexists(target): kept += 1; continue
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(os.path.join(src, f), target + ".part")
            os.replace(target + ".part", target); copied += 1
        except OSError as e:
            if os.path.exists(target + ".part"): os.remove(target + ".part")
            failed.append((f, e.strerror or str(e)))
    return copied, kept, failed


def verify(src=None, dst=None, progress=None):
    """Every picture in src must be in dst with the same bytes. Returns [(file, "missing" | "different")]."""
    src, dst = src or RA_THUMBNAILS, dst or THUMBNAILS
    problems, files = [], pictures(src)
    for n, f in enumerate(files, 1):
        if progress and (n % 500 == 0 or n == len(files)): progress(n, len(files))
        theirs, ours = os.path.join(src, f), os.path.join(dst, f)
        if not os.path.isfile(ours): problems.append((f, "missing"))
        elif not filecmp.cmp(theirs, ours, shallow=False): problems.append((f, "different"))
    return problems


def coverage(games, src=None, dst=None):
    """For each game (db, label), each kind of picture: does RetroArch's folder have it, and Insert Coin's?
    Returns {system: {kind: [in RetroArch's, in Insert Coin's, [labels RetroArch has and Insert Coin lacks]]}}."""
    src, dst = src or RA_THUMBNAILS, dst or THUMBNAILS
    out, seen = {}, set()
    for db, label in games:
        if not label or (db, label) in seen: continue
        seen.add((db, label))
        for kind in KINDS:
            rel = thumb_rel(db, label, kind)
            system = rel.split("/")[0]
            row = out.setdefault(system, {k: [0, 0, []] for k in KINDS})[kind]
            theirs, ours = os.path.isfile(f"{src}/{rel}"), os.path.isfile(f"{dst}/{rel}")
            row[0] += theirs; row[1] += ours
            if theirs and not ours: row[2].append(label)
    return out


def library_games():
    """(db, label) of every game Insert Coin can show: RetroArch's playlists, favorites and history, and Insert
    Coin's own library and lists when it has them."""
    from insertcoin.retroarch import RetroArch, read_json
    from paths import FAVORITES, HISTORY, LIBRARY
    ra, out = RetroArch(), []
    for _, entries in ra.playlists(): out += [(e.db, e.label) for e in entries]
    for doc in (read_json(ra.FAVORITES), read_json(ra.HISTORY)):
        out += [(it.get("db_name") or "", it.get("label") or "") for it in (doc or {}).get("items", [])]
    lib = read_json(LIBRARY) or {}
    for s in lib.get("systems", []):
        out += [(g.get("db") or s.get("name", ""), g.get("label") or "") for g in s.get("games", [])]
    for path in (FAVORITES, HISTORY):
        out += [(it.get("db") or "", it.get("label") or "") for it in (read_json(path) or {}).get("items", [])]
    return [(db, label) for db, label in out if db and label]


def summary(copied, kept, failed, problems, cover, dst=None):
    dst = dst or THUMBNAILS
    lines = [f"Copied {copied:,} pictures from RetroArch's art folder" + (f"; {kept:,} were already there." if kept else ".")]
    for f, why in failed[:10]: lines.append(f"  could not copy {f}: {why}")
    if len(failed) > 10: lines.append(f"  ... and {len(failed) - 10:,} more")
    lines.append("")
    if problems:
        lines.append(f"Check 1, every file: {len(problems):,} picture(s) are missing or different in Insert Coin's folder:")
        lines += [f"  {why}: {f}" for f, why in problems[:10]]
        if len(problems) > 10: lines.append(f"  ... and {len(problems) - 10:,} more")
    else:
        lines.append("Check 1, every file: every picture in RetroArch's folder is in Insert Coin's, byte for byte.")
    lacking = sum(len(r[2]) for kinds in cover.values() for r in kinds.values())
    games = {k: sum(kinds[k][0] for kinds in cover.values()) for k in KINDS}
    lines.append(f"Check 2, every game: box art {games['Named_Boxarts']:,}, title screens {games['Named_Titles']:,}, "
                 f"snapshots {games['Named_Snaps']:,} found in RetroArch's folder; "
                 + ("Insert Coin's has every one of them." if not lacking else f"{lacking:,} of them are missing from Insert Coin's:"))
    if lacking:
        for system, kinds in sorted(cover.items()):
            for k, (_, _, labels) in kinds.items():
                if labels: lines.append(f"  {system}, {k[6:].lower()}: {len(labels):,} (e.g. {labels[0]})")
    lines += ["", f"Insert Coin's art folder: {dst}",
              "The menus read it first; RetroArch's art folder was not changed."]
    if not failed and not problems and not lacking:
        lines.append("All checks passed.")
    return "\n".join(lines)

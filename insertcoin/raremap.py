"""RetroArch's button layouts (.rmp remap files), so a layout set up in RetroArch also works in the built-in player.

RetroArch keeps them in `~/.config/retroarch/config/remaps/<core name>/` and uses the first one it finds:
`<game>.rmp` (this game), `<folder>.rmp` (every game in the game's folder), `<core name>.rmp` (every game
of the core). Each line says what one control in your hand gives the game, for one player:

    input_player1_btn_y = "0"        the left face button (RetroPad Y) presses B (0) instead
    input_player1_stk_l_x+ = "20"    pushing the left stick right moves the game's right stick right
    input_player1_btn_l2 = "-1"      LT does nothing

The numbers are RetroPad ids: 0-15 buttons (B Y Select Start Up Down Left Right A X L R L2 R2 L3 R3) and 16-23
stick directions (left stick X+ X- Y+ Y-, then the right stick's). Lines that aren't there keep their usual job.

Only read, never written: changing a layout stays RetroArch's job (and the built-in player's own Controls screen
for arcade games, whose layout comes first).

Source: the file format and the numbers are RetroArch's (https://github.com/libretro/RetroArch, GPLv3,
The RetroArch team; `input_remapping_load_file` and the libretro.h RetroPad ids). No code was copied.
"""
import os

BUTTONS = ("b", "y", "select", "start", "up", "down", "left", "right", "a", "x", "l", "r", "l2", "r2", "l3", "r3")
STICKS = ("l_x+", "l_x-", "l_y+", "l_y-", "r_x+", "r_x-", "r_y+", "r_y-")             # ids 16-23
NOTHING = -1
FULL = 32767
PRESSED_AT = FULL // 2                    # a stick pushed at least half way counts as a held button


def find(remaps_dir, core_name, game_name, content_dir=None):
    """The remap file RetroArch would use for this game, or None."""
    names = [game_name] + ([os.path.basename(os.path.normpath(content_dir))] if content_dir else []) + [core_name]
    for n in names:
        p = os.path.join(remaps_dir, core_name, f"{n}.rmp")
        if n and os.path.isfile(p): return p
    return None


def read(path):
    """{port: {control id: what it gives}} for the controls whose job changed. Unreadable files give {}."""
    out = {}
    try:
        with open(path, errors="replace") as f: lines = f.read().splitlines()
    except OSError:
        return out
    for ln in lines:
        if "=" not in ln: continue
        k, v = (x.strip() for x in ln.split("=", 1))
        if not k.startswith("input_player"): continue
        try: v = int(v.strip('"'))
        except ValueError: continue
        num, _, rest = k[len("input_player"):].partition("_")
        if not num.isdigit() or not 1 <= int(num) <= 4: continue
        for prefix in ("btn_", "stk_", ""):            # older notes also wrote the stick ones without "stk_"
            if rest.startswith(prefix) and rest[len(prefix):] in BUTTONS + STICKS:
                name = rest[len(prefix):]; break
        else:
            continue
        src = BUTTONS.index(name) if name in BUTTONS else 16 + STICKS.index(name)
        if (src < 16) != (prefix != "stk_") and prefix: continue    # btn_ names a button, stk_ a stick direction
        to = v if 0 <= v <= 23 else NOTHING
        if to != src: out.setdefault(int(num) - 1, {})[src] = to
    return out


def directions(sticks):
    """A pad's two sticks [(lx, ly), (rx, ry)] as how far each of the 8 directions is pushed (0..FULL)."""
    (lx, ly), (rx, ry) = sticks
    return [max(0, lx), max(0, -lx), max(0, ly), max(0, -ly), max(0, rx), max(0, -rx), max(0, ry), max(0, -ry)]


def apply(layout, bits, sticks):
    """One player's buttons (bitmask) and sticks after the layout: returns (bits, sticks)."""
    if not layout: return bits, sticks
    push = directions(sticks)
    out_bits = bits & ~sum(1 << s for s in layout if s < 16)        # moved buttons no longer give their own job
    out_push = [0 if 16 + d in layout else push[d] for d in range(8)]
    for src, to in layout.items():
        amount = (FULL if bits >> src & 1 else 0) if src < 16 else push[src - 16]
        if not amount or to == NOTHING: continue
        if to < 16:
            if src < 16 or amount >= PRESSED_AT: out_bits |= 1 << to
        else: out_push[to - 16] = max(out_push[to - 16], amount)
    p = out_push
    return out_bits, [(p[0] - p[1], p[2] - p[3]), (p[4] - p[5], p[6] - p[7])]

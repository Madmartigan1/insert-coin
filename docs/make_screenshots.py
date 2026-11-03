#!/usr/bin/env python3
"""Render the README screenshots from a made-up demo library.

Every game here is fictional and all artwork (box art, snapshots, title screens) is drawn by this
script, so the screenshots contain no third-party artwork and nothing from a real game collection.
Your own RetroArch setup is never read: everything happens in a throwaway home folder.

    python3 docs/make_screenshots.py            # writes docs/screenshots/*.png
"""
import hashlib, json, os, random, runpy, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "screenshots")
APP = os.path.join(HERE, "..", "insert_coin.py")
SIZE = (1280, 720)                                     # README images are scaled down to keep the repo small

LIBRARY = {   # playlist name -> fictional games
    "FBNeo - Arcade Games": ["Blaze Fist", "Cosmo Raiders", "Metal Moth", "Neon Brawlers", "Rocket Rally",
                             "Sky Lancer", "Star Pilot X", "Thunder Alley", "Turbo Tanks", "Volt Viper"],
    "Nintendo - Super Nintendo Entertainment System": [
        "Aether Knights", "Bubble Brigade", "Crystal Lanterns", "Dune Runners", "Ember Quest", "Frostbite Falls",
        "Gearworks Rally", "Harbor Heroes", "Iron Lotus", "Jade Comet", "Kite Wars", "Lunar Harvest",
        "Moss Temple", "Nimbus Racer", "Orbit Odyssey"],
    "Sega - Mega Drive - Genesis": ["Coral Kingdom", "Puzzle Pagoda", "Rogue Comet", "Sunset Striker",
                                    "Thunder Circuit", "Wavebreaker"],
    "Nintendo - Game Boy": ["Block Garden", "Pocket Planet", "Tiny Towers", "Lantern Lane"],
    "Sony - PlayStation": ["Chrome Horizon", "Echo Protocol", "Glass Labyrinth", "Night Courier"],
    "Atari - 2600": ["Comet Catch", "Space Snake", "Warp Fox"],
}
REGIONS = ["World", "USA", "Japan", "Europe"]
FAVORITES = ["Ember Quest", "Neon Brawlers", "Chrome Horizon", "Coral Kingdom"]
RECENT = ["Star Pilot X", "Ember Quest", "Tiny Towers", "Rogue Comet", "Echo Protocol"]


def palette(name):
    r = random.Random(hashlib.md5(name.encode()).hexdigest())
    base = [r.randint(40, 220) for _ in range(3)]
    return r, tuple(base), tuple(min(255, c + 70) for c in base), tuple(c // 3 for c in base)


def draw_art(pygame, font, name, root):
    """Box art, an in-game 'snapshot' and a title screen, all drawn from the game's name."""
    r, base, light, dark = palette(name)
    # box art 600x800
    box = pygame.Surface((600, 800))
    for y in range(800):
        t = y / 800; pygame.draw.line(box, tuple(int(light[i] * (1 - t) + dark[i] * t) for i in range(3)), (0, y), (600, y))
    for _ in range(14):
        pygame.draw.circle(box, tuple(min(255, c + r.randint(20, 90)) for c in base),
                           (r.randint(0, 600), r.randint(160, 640)), r.randint(20, 120), r.choice([0, 6]))
    pygame.draw.rect(box, (20, 20, 28), (0, 0, 600, 90)); pygame.draw.rect(box, (20, 20, 28), (0, 700, 600, 100))
    box.blit(font(34).render("PIXEL FORGE", True, light), (30, 26))
    words, lines, cur = name.upper().split(), [], ""
    for w in words:
        if font(84).size((cur + " " + w).strip())[0] < 540: cur = (cur + " " + w).strip()
        else: lines.append(cur); cur = w
    lines.append(cur)
    for k, ln in enumerate(lines):
        img = font(84).render(ln, True, (255, 255, 255)); sh = font(84).render(ln, True, (0, 0, 0))
        y = 470 + k * 90 - len(lines) * 45
        box.blit(sh, (300 - img.get_width() / 2 + 5, y + 5)); box.blit(img, (300 - img.get_width() / 2, y))
    box.blit(font(28).render("1 - 2 PLAYERS", True, (220, 220, 230)), (30, 740))
    # snapshot: a tiny pixel-art scene, scaled up with hard edges
    s = pygame.Surface((160, 120))
    for y in range(80):
        t = y / 80; pygame.draw.line(s, tuple(int(light[i] * (1 - t) + base[i] * t) for i in range(3)), (0, y), (160, y))
    pygame.draw.circle(s, (255, 230, 150), (r.randint(20, 140), r.randint(12, 34)), 9)
    for x in range(0, 160, 8):
        h = r.randint(4, 30); pygame.draw.rect(s, dark, (x, 80 - h, 8, h))
    pygame.draw.rect(s, tuple(c // 2 for c in base), (0, 80, 160, 40))
    for x in range(0, 160, 8):
        pygame.draw.rect(s, dark, (x, 80, 8, 8), 1)
    pygame.draw.rect(s, (255, 255, 255), (40, 64, 8, 16)); pygame.draw.rect(s, (230, 60, 60), (40, 60, 8, 6))
    snap = pygame.transform.scale(s, (640, 480))
    # title screen
    t = pygame.Surface((160, 120)); t.fill((8, 8, 20))
    for _ in range(40): t.set_at((r.randint(0, 159), r.randint(0, 119)), (200, 200, 255))
    f = pygame.font.Font(None, 22); img = f.render(name.upper(), False, light)
    t.blit(pygame.transform.scale(img, (min(150, img.get_width()), img.get_height())), (80 - min(150, img.get_width()) / 2, 40))
    t.blit(pygame.font.Font(None, 12).render("PUSH START", False, (255, 255, 255)), (58, 86))
    title = pygame.transform.scale(t, (640, 480))
    return box, snap, title


def build_home(pygame, root):
    ra = os.path.join(root, ".config", "retroarch")
    for d in ("playlists", "cores", "roms"): os.makedirs(os.path.join(ra, d), exist_ok=True)
    core = os.path.join(ra, "cores", "demo_libretro.so"); open(core, "w").close()
    fontpath = pygame.font.match_font("dejavusans,notosans,ubuntu", bold=True)
    fonts = {}
    font = lambda n: fonts.setdefault(n, pygame.font.Font(fontpath, n))
    items = {}
    for pl, games in LIBRARY.items():
        sysdir = "MAME" if pl.startswith("MAME") else pl
        for kind in ("Named_Boxarts", "Named_Snaps", "Named_Titles"):
            os.makedirs(os.path.join(ra, "thumbnails", sysdir, kind), exist_ok=True)
        entries = []
        for k, g in enumerate(games):
            label = f"{g} ({REGIONS[k % len(REGIONS)]})"
            rom = os.path.join(ra, "roms", g.replace(" ", "_") + ".zip"); open(rom, "w").close()
            box, snap, title = draw_art(pygame, font, g, root)
            for kind, img in (("Named_Boxarts", box), ("Named_Snaps", snap), ("Named_Titles", title)):
                pygame.image.save(img, os.path.join(ra, "thumbnails", sysdir, kind, label + ".png"))
            e = {"path": rom, "label": label, "core_path": core, "core_name": "Demo", "crc32": "00000000|crc", "db_name": pl + ".lpl"}
            entries.append(e); items[g] = e
        json.dump({"version": "1.5", "default_core_path": core, "items": entries}, open(os.path.join(ra, "playlists", pl + ".lpl"), "w"))
    json.dump({"version": "1.5", "items": [items[g] for g in FAVORITES]}, open(os.path.join(ra, "content_favorites.lpl"), "w"))
    json.dump({"version": "1.5", "items": [items[g] for g in RECENT]}, open(os.path.join(ra, "content_history.lpl"), "w"))


def main():
    root = tempfile.mkdtemp(prefix="insert-coin-demo-")
    os.environ.update(HOME=root, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy",
                      INSERT_COIN_CONFIG=os.path.join(root, ".config", "insert-coin"))
    import pygame
    pygame.init()
    build_home(pygame, root)
    m = runpy.run_path(APP, run_name="insert_coin_demo")
    app = m["App"](shot=OUT); app.running = True
    time.strftime = lambda fmt, *a: "20:15"               # a fixed clock, so re-renders don't differ
    os.makedirs(OUT, exist_ok=True)

    def save(name):
        for _ in range(45): app.draw()                     # let the animations settle
        pygame.image.save(pygame.transform.smoothscale(app.screen, SIZE), os.path.join(OUT, name + ".png"))
        print("wrote", os.path.join("docs", "screenshots", name + ".png"))

    def go_system(pl):
        app.si = next(i for i, s in enumerate(app.lib.systems) if s["id"] == pl); app.spos = float(app.si)

    app.style = "xbox"
    go_system("FBNeo - Arcade Games"); save("home")
    go_system("Nintendo - Super Nintendo Entertainment System"); app.screen_mode = "games"
    app.gi[app.sys["id"]] = next(k for k, g in enumerate(app.games()) if g.title == "Ember Quest")
    app.gpos = float(app.cur_gi()); save("games")
    app.si = 0; app.spos = 0.0; app.screen_mode = "games"; app.gpos = 0.0; save("favorites")
    app.screen_mode = "systems"; go_system("Sony - PlayStation"); app.screen_mode = "quit"; app.quit_sel = 1; save("menu")
    app.raw[1] = None
    app.start_setup(1, name="USB Gamepad", guid="demo", baseline={})
    app.setup["step"] = 4; save("controller_setup")
    # the button-hint bar in each controller style
    app.setup = None; go_system("Nintendo - Super Nintendo Entertainment System"); app.screen_mode = "games"
    W, H = app.screen.get_size(); strips = []
    for st in ("xbox", "playstation", "nintendo", "keyboard"):
        app.style = st
        for _ in range(3): app.draw()
        strips.append(app.screen.subsurface((0, H - 100, W, 100)).copy())
    sheet = pygame.Surface((W, 100 * len(strips)))
    for k, s in enumerate(strips): sheet.blit(s, (0, 100 * k))
    pygame.image.save(pygame.transform.smoothscale(sheet, (SIZE[0], int(SIZE[0] * sheet.get_height() / W))),
                      os.path.join(OUT, "button_hints.png"))
    print("wrote", os.path.join("docs", "screenshots", "button_hints.png"))


if __name__ == "__main__":
    main()

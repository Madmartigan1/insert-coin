"""Drawing every screen, and --shot sample screenshots."""
import os, pygame, random, re, time
from insertcoin.systems import FRIENDLY
from insertcoin.controllers import GLYPHS, QUIT_COMBO, SETUP_STEPS
from insertcoin.names import split_archive, tags
from insertcoin.web import WebGame
from insertcoin.draw import H, W, magnifier, n_games, rrect, shade, star, text, wrap
class Screens:

    # -- drawing
    def card(self, g, w, h, color):
        """Box art fitted into (w, h), or a placeholder card with the title."""
        s = self.img.get(g.thumb("Named_Boxarts"), w, h)
        if s: return s
        surf = pygame.Surface((int(w * 0.74), int(h)), pygame.SRCALPHA)
        rrect(surf, shade(color, 0.55), surf.get_rect(), 16)
        rrect(surf, shade(color, 0.9), surf.get_rect(), 16, 4)
        f = self.fonts(max(14, int(h / 12)), True)
        lines = wrap(f, g.title, surf.get_width() - 24, 4)
        y = surf.get_height() / 2 - len(lines) * f.get_linesize() / 2
        for ln in lines:
            text(surf, f, ln, (surf.get_width() / 2, y), anchor="midtop"); y += f.get_linesize()
        return surf

    def draw_background(self, color, g=None):
        top, bot = shade(color, 0.32), (8, 8, 14)
        for y in range(0, H, 8):
            t = y / H; c = tuple(int(top[i] * (1 - t) + bot[i] * t) for i in range(3))
            pygame.draw.rect(self.screen, c, (0, y, W, 8))
        if g is not None:
            bg = self.img.get(g.thumb("Named_Snaps"), W, H, "blur")
            if bg:
                if self.prev_bg is not bg:
                    self.prev_bg_old, self.prev_bg, self.bg_change = self.prev_bg, bg, time.time()
                a = min(1.0, (time.time() - self.bg_change) / 0.25)
                old = getattr(self, "prev_bg_old", None)
                if old and a < 1:
                    old.set_alpha(int(255 * (1 - a))); self.screen.blit(old, (0, 0))
                bg.set_alpha(int(255 * a)); self.screen.blit(bg, (0, 0))
                dim = pygame.Surface((W, H), pygame.SRCALPHA); dim.fill((5, 5, 12, 165)); self.screen.blit(dim, (0, 0))

    def draw_header(self, title, sub):
        text(self.screen, self.fonts(46, True), title, (70, 48))
        text(self.screen, self.fonts(26), sub, (72, 108), (200, 205, 220))
        text(self.screen, self.fonts(34, True), time.strftime("%H:%M"), (W - 70, 52), anchor="topright")

    def draw_button(self, action, x, cy, draw=True):
        """Draw the button for `action` in the current controller style; return the x after it."""
        kind, label, color = GLYPHS[self.style].get(action, GLYPHS["xbox"][action])
        s = self.screen
        if kind == "letter":
            if draw:
                pygame.draw.circle(s, color, (x + 21, cy), 21)
                text(s, self.fonts(24, True), label, (x + 21, cy), anchor="center", shadow=False)
            return x + 52
        if kind == "shape":                                        # PlayStation: coloured symbol on a dark button
            if draw:
                cx = x + 21
                pygame.draw.circle(s, (34, 37, 50), (cx, cy), 21); pygame.draw.circle(s, (90, 96, 115), (cx, cy), 21, 2)
                if label == "cross":
                    pygame.draw.line(s, color, (cx - 8, cy - 8), (cx + 8, cy + 8), 4); pygame.draw.line(s, color, (cx - 8, cy + 8), (cx + 8, cy - 8), 4)
                elif label == "circle":
                    pygame.draw.circle(s, color, (cx, cy), 9, 4)
                elif label == "triangle":
                    pygame.draw.polygon(s, color, [(cx, cy - 10), (cx + 10, cy + 8), (cx - 10, cy + 8)], 4)
                elif label == "square":
                    pygame.draw.rect(s, color, (cx - 8, cy - 8, 16, 16), 4)
            return x + 52
        f = self.fonts(22, True)                                   # pills (shoulder buttons) and keyboard keys
        for part in label.split():
            w = max(54, f.size(part)[0] + 26)
            if draw:
                r = pygame.Rect(x, cy - 19, w, 38)
                if kind == "key":
                    rrect(s, (225, 228, 238), r, 8); rrect(s, (150, 155, 170), r, 8, 2)
                    text(s, f, part, r.center, (25, 28, 38), anchor="center", shadow=False)
                else:
                    rrect(s, color, r, 10); text(s, f, part, r.center, anchor="center", shadow=False)
            x += w + 8
        return x + 2

    def draw_hints(self, hints):
        y, f = H - 54, self.fonts(26)
        width = 0
        for action, label in hints:                                # measure first, so the row is centred
            width = self.draw_button(action, width, y, draw=False) + f.size(label)[0] + 40
        x = W / 2 - (width - 40) / 2
        for action, label in hints:
            x = self.draw_button(action, x, y)
            r = text(self.screen, f, label, (x, y), (225, 228, 238), anchor="midleft"); x = r.right + 40

    def draw_systems(self, hints=True):
        s = self.sys
        self.draw_background(s["color"])
        self.draw_header("Insert Coin", f"{sum(len(x['games']) for x in self.lib.systems if not x['special']):,} games · {len([x for x in self.lib.systems if not x['special']])} systems")
        self.spos += (self.si - self.spos) * 0.22
        n = len(self.lib.systems); cy = 500
        order = sorted(range(-3, 4), key=lambda k: -abs(k))
        base = round(self.spos)
        for k in order:
            i = base + k
            if not 0 <= i < n: continue
            sy = self.lib.systems[i]; d = i - self.spos; ad = abs(d)
            sc = max(0.45, 1 - 0.22 * ad); w, h = 560 * sc, 400 * sc
            x = W / 2 + d * 470 - w / 2 * (1 if d >= 0 else 1)
            rect = pygame.Rect(0, 0, w, h); rect.center = (W / 2 + d * 470 * (1 - 0.06 * ad), cy)
            tile = pygame.Surface((w, h), pygame.SRCALPHA)
            rrect(tile, shade(sy["color"], 0.5), tile.get_rect(), 26)
            g3 = sy["games"][:: max(1, len(sy["games"]) // 3)][:3] if sy["special"] else random.Random(sy["id"]).sample(sy["games"], min(3, len(sy["games"])))
            if sy["special"] == "search" and not sy["games"]: magnifier(tile, (w * 0.5, h * 0.36), 70 * sc)
            for j, g in enumerate(g3):                                     # a little fan of box art
                im = self.img.get(g.thumb("Named_Boxarts"), 190 * sc, 230 * sc)
                if im:
                    r = im.get_rect(); r.midbottom = (w * (0.3 + 0.2 * j), h * 0.70)
                    tile.blit(im, r)
            grad = pygame.Surface((w, h * 0.45), pygame.SRCALPHA)
            for yy in range(int(h * 0.45)):
                pygame.draw.line(grad, (*shade(sy["color"], 0.25), int(235 * yy / (h * 0.45))), (0, yy), (w, yy))
            tile.blit(grad, (0, h * 0.55))
            text(tile, self.fonts(int(46 * sc), True), sy["name"], (26 * sc, h - 98 * sc), maxw=w - 40)
            sub = sy["maker"] if sy["special"] == "search" and not sy["games"] else f"{sy['maker']}  ·  {n_games(len(sy['games']))}"
            text(tile, self.fonts(int(24 * sc)), sub, (28 * sc, h - 42 * sc), (215, 220, 230), maxw=w - 40)
            mask = pygame.Surface((w, h), pygame.SRCALPHA); rrect(mask, (255, 255, 255, 255), mask.get_rect(), 26)
            tile.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            if ad > 0.5: tile.set_alpha(int(255 * max(0.35, 1 - 0.3 * ad)))
            self.screen.blit(tile, rect)
            if ad < 0.5: rrect(self.screen, (255, 255, 255), rect.inflate(10, 10), 30, 5)
        dots_w = n * 22; x0 = W / 2 - dots_w / 2
        for i in range(n):
            pygame.draw.circle(self.screen, (255, 255, 255) if i == self.si else (110, 115, 130), (x0 + i * 22 + 11, 790), 6 if i == self.si else 4)
        text(self.screen, self.fonts(30), s["maker"] if s["special"] else n_games(len(s['games'])), (W / 2, 850), (210, 215, 228), anchor="midtop")
        if hints: self.draw_hints([("a", "Open"), ("b", "Power")] + ([("r3", "Search")] if self.style != "generic" else []))

    def draw_games(self, hints=True):
        s = self.sys; gs = self.games(); i = self.cur_gi(); g = gs[i] if gs else None
        self.draw_background(s["color"], g)
        self.draw_header(s["name"], f"{n_games(len(gs))}  ·  {i + 1:,} / {len(gs):,}")
        self.gpos += (i - self.gpos) * 0.25
        if abs(i - self.gpos) > 40: self.gpos = i - 40 * (1 if i > self.gpos else -1)
        cx, cy, H0 = 700, 470, 470
        base = round(self.gpos)
        self.screen.set_clip(pygame.Rect(0, 150, 1320, 700))           # keep the carousel clear of the side panel
        for k in sorted(range(-4, 4), key=lambda k: -abs(k)):
            j = base + k
            if not 0 <= j < len(gs): continue
            d = j - self.gpos; ad = abs(d)
            h = H0 * max(0.42, 1 - 0.2 * ad) if ad > 0.5 else H0
            hb = int(h // 16 * 16)
            im = self.card(gs[j], hb * 0.95, hb, s["color"])
            x = cx + (d * 330 if ad <= 1 else (330 + (ad - 1) * 215) * (1 if d > 0 else -1))
            r = im.get_rect(); r.center = (x, cy)
            if ad > 0.5:
                im = im.copy(); im.set_alpha(int(255 * max(0.25, 1 - 0.28 * ad)))
            else:
                sh = pygame.Surface((r.w + 30, r.h + 30), pygame.SRCALPHA); rrect(sh, (0, 0, 0, 120), sh.get_rect(), 24)
                self.screen.blit(sh, r.move(-6, 4).inflate(18, 18))
            self.screen.blit(im, r)
            if ad <= 0.5:
                rrect(self.screen, (255, 255, 255), r.inflate(12, 12), 14, 5)
                if self.lib.is_fav(gs[j]):
                    star(self.screen, (r.right - 30, r.top + 32), 26)
        self.screen.set_clip(None)
        # title-screen side panel
        px, py, pw, ph = 1360, 230, 500, 375
        rrect(self.screen, (0, 0, 0, 0), (px - 8, py - 8, pw + 16, ph + 16), 18)
        frame = pygame.Surface((pw + 16, ph + 16), pygame.SRCALPHA); rrect(frame, (10, 10, 18, 200), frame.get_rect(), 18)
        self.screen.blit(frame, (px - 8, py - 8))
        if g:
            ts = self.img.get(g.thumb("Named_Titles"), pw, ph)
            if ts:
                r = ts.get_rect(center=(px + pw / 2, py + ph / 2)); self.screen.blit(ts, r)
            elif ts is None:
                text(self.screen, self.fonts(26), "No title screen", (px + pw / 2, py + ph / 2), (150, 155, 170), anchor="center")
        text(self.screen, self.fonts(22, True), "TITLE SCREEN", (px, py + ph + 18), (170, 175, 190))
        # title + info
        if g:
            text(self.screen, self.fonts(58, True), g.title, (cx, 770), anchor="midtop", maxw=1250)
            info = []
            m = self.meta.get(g)
            if m:
                if m[0]: info.append(str(m[0]))
                if m[1]: info.append(m[1])
            sysname = FRIENDLY.get(g.system, (g.system,))[0] if s["special"] else None
            if sysname: info.append(sysname)
            t = [x for x in tags(g.label) if len(x) < 30][:2]
            info += t
            if info: text(self.screen, self.fonts(28), "  ·  ".join(info), (cx, 846), (205, 210, 225), anchor="midtop", maxw=1250)
            if not g.core and not isinstance(g, WebGame):
                text(self.screen, self.fonts(24), "No core assigned", (cx, 892), (240, 150, 120), anchor="midtop")
            elif g.versions:                                        # "3 versions · (X) to choose", with this pad's own X button
                f1, f2 = self.fonts(26, True), self.fonts(26)
                a, b = f"{len(g.versions)} versions  ·  ", "  to choose"
                bw = self.draw_button("x", 0, 0, draw=False)
                x0 = cx - (f1.size(a)[0] + bw + f2.size(b)[0]) / 2
                text(self.screen, f1, a, (x0, 908), (150, 200, 255), anchor="midleft")
                x1 = self.draw_button("x", x0 + f1.size(a)[0], 908)
                text(self.screen, f2, b, (x1 - 10, 908), (190, 205, 230), anchor="midleft")
        else:
            text(self.screen, self.fonts(40), "No games here", (W / 2, H / 2), anchor="center")
        if self.jump and time.time() < self.jump[1]:
            box = pygame.Surface((220, 220), pygame.SRCALPHA); rrect(box, (0, 0, 0, 190), box.get_rect(), 30)
            self.screen.blit(box, (cx - 110, cy - 110))
            text(self.screen, self.fonts(150, True), self.jump[0], (cx, cy), anchor="center")
        if not hints: return
        hs = [("a", "Play"), ("b", "Back"), ("y", "Favorite")]
        if g and g.versions: hs.append(("x", "Versions"))
        self.draw_hints(hs + [("lbrb", "Jump A–Z")])

    def draw_versions(self):
        self.draw_games(hints=False)
        dim = pygame.Surface((W, H), pygame.SRCALPHA); dim.fill((0, 0, 0, 175)); self.screen.blit(dim, (0, 0))
        vs = self.vlist; show = 7; top = max(0, min(self.vsel - show // 2, len(vs) - show))
        box = pygame.Rect(0, 0, 1180, 190 + 84 * min(show, len(vs))); box.center = (W / 2, H / 2 - 20)
        rrect(self.screen, (28, 30, 42), box, 28); rrect(self.screen, (90, 95, 115), box, 28, 3)
        text(self.screen, self.fonts(40, True), vs[0].title, (W / 2, box.top + 34), anchor="midtop", maxw=1080)
        text(self.screen, self.fonts(26), f"{len(vs)} versions", (W / 2, box.top + 88), (170, 175, 190), anchor="midtop")
        for row, k in enumerate(range(top, min(len(vs), top + show))):
            r = pygame.Rect(0, 0, 1080, 70); r.midtop = (W / 2, box.top + 140 + row * 84)
            on = k == self.vsel
            rrect(self.screen, (230, 232, 240) if on else (55, 58, 75), r, 18)
            folder = os.path.basename(os.path.dirname(split_archive(vs[k].path)[0]))
            text(self.screen, self.fonts(28, True), vs[k].label, (r.left + 28, r.centery), (20, 22, 30) if on else (230, 232, 240),
                 anchor="midleft", shadow=False, maxw=760)
            text(self.screen, self.fonts(22), folder, (r.right - 24, r.centery), (90, 95, 110) if on else (150, 155, 170),
                 anchor="midright", shadow=False, maxw=260)
        self.draw_hints([("a", "Play"), ("b", "Back")])

    def draw_search(self):
        """The on-screen keyboard, what's typed, and the games it finds so far."""
        color = (120, 110, 210)
        self.draw_background(color, self.preview[0] if self.preview else None)
        kb = self.style == "keyboard"
        self.draw_header("Search", "Type on your keyboard" if kb else "Type a word from the game's name")
        box = pygame.Rect(120, 170, 1060, 96)
        rrect(self.screen, (236, 238, 245), box, 22)
        f = self.fonts(46, True)
        if self.q:
            r = text(self.screen, f, self.q, (box.left + 34, box.centery), (20, 22, 30), anchor="midleft", shadow=False, maxw=980)
            if int(time.time() * 2) % 2: pygame.draw.rect(self.screen, (20, 22, 30), (r.right + 4, box.centery - 26, 4, 52))
        else:
            text(self.screen, self.fonts(40), "for example: knight", (box.left + 34, box.centery), (140, 145, 160), anchor="midleft", shadow=False)
        x0, y, kw, gap = box.left, 320, 94, 10
        for row, keys in enumerate(self.KEYS):
            wide = isinstance(keys, tuple)
            w = (box.width - gap * (len(keys) - 1)) / len(keys) if wide else kw
            x = x0 + (box.width - (len(keys) * (w + gap) - gap)) / 2
            for col, k in enumerate(keys):
                r = pygame.Rect(round(x), y, round(w), 88)
                on = not kb and (row, col) == (self.kpos[0], min(self.kpos[1], len(keys) - 1))
                rrect(self.screen, (236, 238, 245) if on else (48, 51, 68), r, 16)
                if not on: rrect(self.screen, (80, 85, 105), r, 16, 2)
                text(self.screen, self.fonts(36 if not wide else 32, True), k, r.center, (20, 22, 30) if on else (235, 237, 245),
                     anchor="center", shadow=False)
                x += w + gap
            y += 88 + 14
        # what it finds so far
        px, py = 1270, 180
        n = len(self.preview)
        head = n_games(n) if n else ("No games match" if self.q.strip() else "Games appear as you type")
        text(self.screen, self.fonts(34, True), head, (px, py))
        for k, g in enumerate(self.preview[:9]):
            yy = py + 70 + k * 74
            text(self.screen, self.fonts(28, True), g.title, (px, yy), maxw=600)
            sysname = FRIENDLY.get(g.system, (g.system,))[0]
            text(self.screen, self.fonts(22), sysname, (px, yy + 36), (175, 180, 200), maxw=600)
        if n > 9: text(self.screen, self.fonts(24), f"and {n - 9:,} more", (px, py + 70 + 9 * 74), (175, 180, 200))
        self.draw_hints([("a", "Search"), ("b", "Back")] if kb else
                        [("a", "Type"), ("x", "Delete"), ("y", "Space"), ("b", "Back")])

    @property
    def POWER_MENU(self):
        return ("Resume", f"Sound: {'On' if self.sfx.enabled else 'Off'}",
                f"Player: {'Built-in (beta)' if self.settings.get('engine') else 'RetroArch'}",
                f"Games: {'One per game' if self.settings['one_per_game'] else 'Show all'}", "Set up controller", "Exit Insert Coin")

    def draw_quit(self):
        self.draw_systems(hints=False)
        dim = pygame.Surface((W, H), pygame.SRCALPHA); dim.fill((0, 0, 0, 170)); self.screen.blit(dim, (0, 0))
        box = pygame.Rect(0, 0, 640, 200 + 96 * len(self.POWER_MENU)); box.center = (W / 2, H / 2)
        rrect(self.screen, (28, 30, 42), box, 28); rrect(self.screen, (90, 95, 115), box, 28, 3)
        text(self.screen, self.fonts(44, True), "Insert Coin", (W / 2, box.top + 48), anchor="midtop")
        for k, lbl in enumerate(self.POWER_MENU):
            r = pygame.Rect(0, 0, 480, 76); r.center = (W / 2, box.top + 180 + k * 96)
            on = self.quit_sel == k
            rrect(self.screen, (230, 232, 240) if on else (55, 58, 75), r, 20)
            text(self.screen, self.fonts(32, True), lbl, r.center, (20, 22, 30) if on else (230, 232, 240), anchor="center", shadow=False)
        self.draw_hints([("a", "Choose"), ("b", "Close")])

    def draw_setup(self):
        s = self.setup; act, shown, what, optional = SETUP_STEPS[s["step"]]
        self.draw_background((60, 70, 100))
        self.draw_header("Set up your controller", s["name"])
        text(self.screen, self.fonts(30), f"Step {s['step'] + 1} of {len(SETUP_STEPS)}", (W / 2, 250), (190, 195, 210), anchor="midtop")
        text(self.screen, self.fonts(40), "Press the button you want for", (W / 2, 330), anchor="midtop")
        cy = 500                                                    # the button being asked for, big
        if shown in ("up", "down", "left", "right"):
            pygame.draw.circle(self.screen, (110, 116, 132), (W / 2, cy), 70)
            pts = {"up": [(0, -34), (30, 18), (-30, 18)], "down": [(0, 34), (30, -18), (-30, -18)],
                   "left": [(-34, 0), (18, -30), (18, 30)], "right": [(34, 0), (-18, -30), (-18, 30)]}[shown]
            pygame.draw.polygon(self.screen, (255, 255, 255), [(W / 2 + x, cy + y) for x, y in pts])
        else:
            f = self.fonts(80, True); tw = max(140, f.size(shown)[0] + 70)
            if len(shown) == 1: pygame.draw.circle(self.screen, (110, 116, 132), (W / 2, cy), 70)
            else: rrect(self.screen, (120, 130, 150), pygame.Rect(W / 2 - tw / 2, cy - 60, tw, 120), 28)
            text(self.screen, f, shown, (W / 2, cy), anchor="center", shadow=False)
        text(self.screen, self.fonts(44, True), what, (W / 2, 610), anchor="midtop")
        if s["msg"]:
            text(self.screen, self.fonts(30), s["msg"], (W / 2, 690), (255, 170, 120), anchor="midtop")
        elif optional:
            text(self.screen, self.fonts(30), "Optional - press your B button to skip", (W / 2, 690), (190, 195, 210), anchor="midtop")
        for k in range(len(SETUP_STEPS)):                          # progress dots
            x = W / 2 + (k - (len(SETUP_STEPS) - 1) / 2) * 34
            pygame.draw.circle(self.screen, (255, 255, 255) if k <= s["step"] else (90, 95, 115), (x, 790), 9 if k == s["step"] else 7)
        text(self.screen, self.fonts(26), "Buttons, the d-pad and sticks all work.   Esc on the keyboard cancels.",
             (W / 2, H - 70), (170, 175, 190), anchor="midtop")

    def splash(self, g, engine=False, web=False):
        self.screen.fill((0, 0, 0))
        im = self.img.get(g.thumb("Named_Boxarts"), 420, 520)
        if im: self.screen.blit(im, im.get_rect(center=(W / 2, H / 2 - 60)))
        text(self.screen, self.fonts(44, True), g.title, (W / 2, H / 2 + 250), anchor="midtop", maxw=1500)
        combo = self.pad_quit.get(self.cur_pad, QUIT_COMBO[self.style]) if self.style != 'keyboard' else 'Esc'
        note = (f"{combo} returns to Insert Coin" if self.style != "keyboard" else "Alt + F4 returns to Insert Coin") if web \
            else f"{combo} opens the game menu"
        text(self.screen, self.fonts(26), f"Starting…   ({note})", (W / 2, H / 2 + 320), (180, 185, 200), anchor="midtop")
        pygame.display.flip()

    def draw_empty(self):
        self.draw_background((60, 70, 100))
        self.draw_header("Insert Coin", "No games found")
        lines = ["Insert Coin shows the games in your RetroArch playlists,",
                 "but none were found in ~/.config/retroarch/playlists.",
                 "", "Open RetroArch, use Import Content to scan your games,",
                 "then start Insert Coin again."]
        for n, ln in enumerate(lines):
            text(self.screen, self.fonts(34), ln, (W / 2, 360 + n * 56), (220, 224, 235), anchor="midtop")
        self.draw_hints([("b", "Exit")])

    def draw(self):
        self.img.pump()
        if self.screen_mode == "setup":
            return self.draw_setup()
        if not self.lib.systems:
            return self.draw_empty()
        {"systems": self.draw_systems, "games": self.draw_games, "quit": self.draw_quit,
         "versions": self.draw_versions, "search": self.draw_search}[self.screen_mode]()
        if self.toast and time.time() < self.toast[1]:
            f = self.fonts(30); w = f.size(self.toast[0])[0] + 60
            r = pygame.Rect(0, 0, w, 64); r.midtop = (W / 2, H - 150 if self.screen_mode in ("quit", "search") else 150)   # clear of the menu
            box = pygame.Surface(r.size, pygame.SRCALPHA); rrect(box, (0, 0, 0, 200), box.get_rect(), 32); self.screen.blit(box, r)
            text(self.screen, f, self.toast[0], r.center, anchor="center", shadow=False)

    def screenshots(self):
        os.makedirs(self.shot, exist_ok=True)
        def snap(name):
            for _ in range(40): self.draw()                         # let animations settle
            pygame.image.save(self.screen, f"{self.shot}/{name}.png")
        if not self.lib.systems:
            print("No RetroArch playlists with games found - nothing to render."); pygame.quit(); return
        snap("1_systems")
        # the two largest systems, a third of the way into each list, so neighbours are visible
        big = sorted((i for i, s in enumerate(self.lib.systems) if not s["special"]),
                     key=lambda i: -len(self.lib.systems[i]["games"]))[:2] or [0]
        time.sleep(1.5)                                             # give the metadata thread a moment
        for n, i in enumerate(big, 2):
            self.si = i; self.screen_mode = "games"
            self.gi[self.sys["id"]] = len(self.games()) // 3; self.gpos = float(self.cur_gi())
            snap(f"{n}_games_{re.sub(r'[^a-z0-9]+', '_', self.sys['name'].lower())}")
        self.screen_mode = "systems"; self.si = 0; self.spos = 0.0; snap(f"{len(big) + 2}_systems_first")
        self.screen_mode = "quit"; snap(f"{len(big) + 3}_quit")
        # the button-hint bar in every controller style, stacked into one image
        self.si = big[0]; self.screen_mode = "games"; strips = []
        for st in GLYPHS:
            self.style = st; self.draw()
            strips.append(self.screen.subsurface((0, H - 110, W, 110)).copy())
        sheet = pygame.Surface((W, 110 * len(strips)))
        for k, strip in enumerate(strips): sheet.blit(strip, (0, 110 * k))
        pygame.image.save(sheet, f"{self.shot}/{len(big) + 4}_button_styles.png")
        pygame.quit()

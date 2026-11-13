"""Screen size and drawing helpers."""
import pygame
W, H = 1920, 1080


def text(surf, font, s, pos, color=(255, 255, 255), anchor="topleft", shadow=True, maxw=None):
    if maxw:
        while font.size(s)[0] > maxw and len(s) > 4: s = s[:-2].rstrip() + "…" if not s.endswith("…") else s[:-2].rstrip() + "…"
    img = font.render(s, True, color)
    r = img.get_rect(**{anchor: pos})
    if shadow:
        sh = font.render(s, True, (0, 0, 0)); sh.set_alpha(150); surf.blit(sh, r.move(2, 3))
    surf.blit(img, r)
    return r


def wrap(font, s, width, lines=3):
    words, out, cur = s.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if font.size(t)[0] <= width: cur = t
        else:
            if cur: out.append(cur)
            cur = w
    if cur: out.append(cur)
    return out[:lines]


def rrect(surf, color, rect, radius=18, width=0):
    pygame.draw.rect(surf, color, rect, width, border_radius=radius)


def star(surf, center, r, color=(255, 210, 60)):
    import math
    cx, cy = center
    pts = [(cx + (r if k % 2 == 0 else r * 0.45) * math.sin(k * math.pi / 5), cy - (r if k % 2 == 0 else r * 0.45) * math.cos(k * math.pi / 5)) for k in range(10)]
    pygame.draw.polygon(surf, (0, 0, 0), [(x + 2, y + 3) for x, y in pts])
    pygame.draw.polygon(surf, color, pts)


def magnifier(surf, center, r, color=(255, 255, 255)):
    """A magnifying glass: the Search tile's picture."""
    cx, cy = center
    pygame.draw.circle(surf, color, (cx - r * 0.15, cy - r * 0.15), r * 0.62, max(3, int(r * 0.16)))
    pygame.draw.line(surf, color, (cx + r * 0.3, cy + r * 0.3), (cx + r * 0.85, cy + r * 0.85), max(4, int(r * 0.24)))


def n_games(n):
    return f"{n:,} game" + ("" if n == 1 else "s")


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)

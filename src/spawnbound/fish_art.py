from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Look:
    colors: tuple[str, str, str, str, str, str]  # A paleta segue a ordem do desenho, do contorno do dorso às nadadeiras.
    start: int = 3
    end: int = 13
    height: float = 2.5
    pattern: str = ""
    round: bool = False
    barbels: bool = False


LOOKS = {
    "lambari": Look(("#3c5866", "#5d7f8a", "#a9c4c6", "#e8f0e6", "#c43c2c", "#e8a83a"), 4, 13, 2.2, "line"),
    "tilapia": Look(("#33463c", "#4f6a5a", "#7f9a84", "#c9d6b8", "#2c3e34", "#9a6a5a"), 4, 13, 3.8, "stripes"),
    "bagre": Look(("#2e2622", "#4a3f3a", "#6e625a", "#b8a894", "#2e2622", "#5a4c44"), 3, 13, 2.4, barbels=True),
    "traira": Look(("#2f2c18", "#4c4a2a", "#7a7440", "#c9bf8a", "#2a2814", "#5c5630"), 3, 14, 2.2, "spots"),
    "tucunare": Look(("#3c4c18", "#5f7a2a", "#c9b83a", "#f0e08a", "#26300e", "#d4502a"), 4, 13, 3.2, "bars"),
    "pirarucu": Look(("#2c3834", "#40504a", "#6e7e6a", "#c8c0a0", "#b8302a", "#7a3a2a"), 3, 14, 2.5, "rear"),
    "sardinha": Look(("#1e3c64", "#2f5a8a", "#9cc0d8", "#eef6f8", "#1e3c64", "#7aa0bc"), 4, 13, 2.0, "spots"),
    "tainha": Look(("#33444f", "#4a5f70", "#9fb2bc", "#e4ecec", "#5d7282", "#7c8e98"), 3, 14, 2.5, "stripes_h"),
    "baiacu": Look(("#5c5024", "#8a7a3a", "#c8b45a", "#f4eccc", "#4a3e18", "#a8943e"), 5, 12, 4.2, "spots",
                   round=True),
    "robalo": Look(("#3c4848", "#5a6a6a", "#bcc8c4", "#f0f4ec", "#1c2424", "#8a9a96"), 3, 14, 3.0, "line"),
    "garoupa": Look(("#4a1e16", "#6a2e22", "#a4523a", "#d89a74", "#f0c8a0", "#7a3a2a"), 4, 13, 4.0, "spots"),
    "atum": Look(("#141e40", "#1e2e5a", "#6a84a8", "#e2e8ee", "#e8c03a", "#e8c03a"), 3, 14, 3.4, "finlets"),
}
CENTER = 7.5


def palette(item: str) -> dict[str, str]:
    look = LOOKS[item]
    return {**dict(zip("1234pf", look.colors)), "e": "#140e18", "w": "#ffffff"}


def _half(look: Look, x: int) -> float:
    t = (x - look.start + .5) / (look.end - look.start + 1)
    if look.round:
        return look.height * math.sqrt(max(0., 1 - (2 * t - 1) ** 2))
    return look.height * math.sin(math.pi * min(1., t * .82 + .12)) ** .8


def drawing(item: str) -> str:
    look = LOOKS[item]
    grid = [["."] * 16 for _ in range(16)]
    body = set()
    for x in range(look.start, look.end + 1):
        half = _half(look, x)
        top, bottom = round(CENTER - half), round(CENTER + half)
        for y in range(max(1, top), min(15, bottom) + 1):
            rel = (y - top) / max(1, bottom - top)
            key = "1" if y == top else "2" if rel < .34 else "3" if rel < .7 else "4"
            grid[y][x] = key
            body.add((x, y))
    for k in range(1, min(4, look.start)):
        x = look.start - k
        for y in range(round(CENTER - k - .5), round(CENTER + k + .5) + 1):
            if 0 <= y < 16 and (k > 1 or abs(y - CENTER) < 1.5):
                grid[y][x] = "f"
    mid = (look.start + look.end) // 2
    for x in range(mid - 1, mid + 2):
        top = round(CENTER - _half(look, x))
        if top - 1 >= 0 and (x != mid + 1 or look.height > 3):
            grid[top - 1][x] = "f"
    belly_x = mid + 2
    bottom = round(CENTER + _half(look, belly_x))
    if bottom + 1 < 16 and not look.round:
        grid[bottom + 1][belly_x] = "f"
    side = [(x, y) for x, y in body if grid[y][x] in "23"]
    for x, y in side:
        if look.pattern == "stripes" and x % 3 == 0 and x < look.end - 2:
            grid[y][x] = "p"
        elif look.pattern == "bars" and x in (mid - 3, mid, mid + 3):
            grid[y][x] = "p"
        elif look.pattern == "spots" and (x * 7 + y * 5) % 9 == 0 and x < look.end - 2:
            grid[y][x] = "p"
        elif look.pattern == "line" and y == round(CENTER) and x < look.end - 2:
            grid[y][x] = "p"
        elif look.pattern == "stripes_h" and (y - round(CENTER)) % 2 == 0 and x < look.end - 2:
            grid[y][x] = "p"
        elif look.pattern == "rear" and x < mid - 1:
            grid[y][x] = "p"
    if look.pattern == "finlets":
        for x in range(look.start + 1, mid - 1, 2):
            top, bottom = round(CENTER - _half(look, x)), round(CENTER + _half(look, x))
            grid[max(0, top - 1)][x] = "p"
            grid[min(15, bottom + 1)][x] = "p"
    if look.round:
        for x, y in ((mid - 2, round(CENTER - look.height) - 1), (mid + 2, round(CENTER - look.height) - 1),
                     (look.start - 1, round(CENTER) - 3), (mid, round(CENTER + look.height) + 1)):
            if 0 <= x < 16 and 0 <= y < 16 and grid[y][x] == ".":
                grid[y][x] = "f"
    eye_x = look.end - 2
    eye_y = round(CENTER - _half(look, eye_x) * .35)
    grid[eye_y][eye_x] = "e"
    if look.height >= 3.4 and eye_y - 1 >= 0 and grid[eye_y - 1][eye_x] != ".":
        grid[eye_y - 1][eye_x] = "w"
    if look.barbels:
        for x, y in ((look.end + 1, round(CENTER) + 1), (look.end, round(CENTER) + 2), (look.end + 1, round(CENTER) + 3)):
            if 0 <= x < 16 and 0 <= y < 16:
                grid[y][x] = "f"
    return "\n".join("".join(row) for row in grid)

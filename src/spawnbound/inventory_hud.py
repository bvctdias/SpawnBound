from __future__ import annotations

import math
from functools import lru_cache

import pygame

from spawnbound.domain.inventory import CHEST_COLUMNS, HOTBAR_SIZE, SLOT_COUNT
from spawnbound.item_icons import ITEMS, icon, mini_icon
from spawnbound.domain.tools import TOOLS
from spawnbound.view import HUD_HEADROOM, hotbar_rect, inventory_panel, slot_rect
from spawnbound.crafting_view import TITLES, bench_button, contains, recipe_layout
from spawnbound.domain.crafting import RECIPES, shown_recipes
from spawnbound.pplay_ui import GameMeter, draw_on, show


CREAM = "#fff3ce"
MUTED = "#c9bb9e"
GOLD = "#ddb56e"
INK = "#211d21"
EDGE = "#75614c"
PANEL = (22, 16, 16, 224)
SHORT = "#f47b78"

SLOT_FILL = (40, 31, 33, 228)
SLOT_PICKED = (61, 48, 46, 236)
SLOT_LIGHT = "#5a4744"
SLOT_DARK = "#1c1517"
NOTCH = "#2a2124"
HEART = (".XXX...XXX.",
         "XRRRX.XRRRX",
         "XRHHRXRRRDX",
         "XRHRRRRRRDX",
         "XRRRRRRRRDX",
         ".XRRRRRRDX.",
         "..XRRRRDX..",
         "...XRRDX...",
         "....XDX....",
         ".....X.....")
HEART_PITCH = 12
HEART_LOOKS = {
    "full": {"R": "#e8464e", "H": "#ffc2b0", "D": "#a82c3c"},
    "empty": {"R": "#4b3a3f", "H": "#5d4a4f", "D": "#3a2c31"},
    "flash": {"R": "#fff4ec", "H": "#fff4ec", "D": "#fff4ec"},
}


class InventoryHUD:
    def __init__(self, font):
        self.font = font
        self.temperature = self._temperature_dial()

    def _text(self, surface, text, position, color=CREAM, scale=1):
        glyphs = self.font.render(text, pygame.Color(color)[:3], scale, shadow=(31, 24, 27))
        surface.blit(glyphs, position)

    @staticmethod
    def _temperature_dial():
        dial = pygame.Surface((24, 24), pygame.SRCALPHA)
        pygame.draw.circle(dial, INK, (12, 12), 12)
        pygame.draw.circle(dial, EDGE, (12, 12), 10)
        pygame.draw.circle(dial, "#29292b", (12, 12), 9)
        for i, color in enumerate(("#62bdde", "#a8b3b1", "#ed796b")):
            points = []
            for radius, steps in ((8, range(6)), (5, reversed(range(6)))):
                for step in steps:
                    angle = math.radians(200 - 73 * (i + step / 5))
                    points.append((12 + round(radius * math.cos(angle)), 12 - round(radius * math.sin(angle))))
            pygame.draw.polygon(dial, color, points)
        pygame.draw.polygon(dial, CREAM, [(11, 13), (12, 5), (13, 13)])
        pygame.draw.circle(dial, GOLD, (12, 13), 2)
        dial.set_at((12, 13), INK)
        return dial

    def _slot(self, surface, rect, stack, *, number=None, marked=False, large=False):
        pygame.draw.rect(surface, (18, 15, 14, 214), rect, border_radius=6)
        if marked:
            for x, dx in ((rect.left+1, 1), (rect.right-2, -1)):
                for y, dy in ((rect.top+1, 1), (rect.bottom-2, -1)):
                    pygame.draw.lines(surface, CREAM, False,
                                      [(x, y+dy*8), (x, y+dy*3), (x+dx*3, y), (x+dx*8, y)], 3)
        if stack:
            if stack.item in ITEMS:
                show(surface, icon(stack.item, 3 if large else 2), center=rect.center)
            else:
                self._text(surface, "?", (rect.centerx - 5, rect.centery - 7), GOLD, 2)
            if stack.count > 1 or (large and stack.item not in TOOLS):
                count = str(stack.count)
                scale = 2 if large else 1
                self._text(surface, count, (rect.right-4-self.font.size(count, scale)[0],
                                            rect.bottom-3-7*scale), scale=scale)
        if number is not None:
            self._text(surface, str(number), (rect.x+5, rect.y+4), MUTED)

    @staticmethod
    def _chamfer(surface, rect, color, width=0):
        x, y, w, h = rect
        if width == 0:
            pygame.draw.rect(surface, color, (x + 1, y, w - 2, h))
            pygame.draw.rect(surface, color, (x, y + 1, w, h - 2))
            return
        pygame.draw.line(surface, color, (x + 1, y), (x + w - 2, y))
        pygame.draw.line(surface, color, (x + 1, y + h - 1), (x + w - 2, y + h - 1))
        pygame.draw.line(surface, color, (x, y + 1), (x, y + h - 2))
        pygame.draw.line(surface, color, (x + w - 1, y + 1), (x + w - 1, y + h - 2))

    def _bar_slot(self, surface, rect, stack, selected):
        self._chamfer(surface, rect, SLOT_PICKED if selected else SLOT_FILL)
        pygame.draw.line(surface, SLOT_LIGHT, (rect.x + 2, rect.y + 1), (rect.right - 3, rect.y + 1))
        pygame.draw.line(surface, SLOT_DARK, (rect.x + 2, rect.bottom - 2), (rect.right - 3, rect.bottom - 2))
        if selected:
            self._chamfer(surface, rect.inflate(2, 2), CREAM, 1)
            self._chamfer(surface, rect, CREAM, 1)
        else:
            self._chamfer(surface, rect, INK, 1)
        if stack:
            if stack.item in ITEMS:
                show(surface, icon(stack.item, 2), center=rect.center)
            else:
                self._text(surface, "?", (rect.centerx - 5, rect.centery - 7), GOLD, 2)
            if stack.count > 1:
                count = str(stack.count)
                self._text(surface, count, (rect.right - 3 - self.font.size(count, 1)[0], rect.bottom - 10))

    @staticmethod
    def _line(surface, box, fraction, fill, light, track, notch=0):
        draw_on(surface, ThinMeter(box, fraction, fill, light, track, notch))

    @staticmethod
    @lru_cache(maxsize=None)
    def _heart_image(look):
        colors = HEART_LOOKS[look]
        image = pygame.Surface((len(HEART[0]), len(HEART)), pygame.SRCALPHA)
        for y, row in enumerate(HEART):
            for x, cell in enumerate(row):
                if cell != ".":
                    image.set_at((x, y), colors.get(cell, INK))
        return image

    def draw_bar(self, surface, config, player, hurt=0.):
        left, top, width, height = hotbar_rect(config)
        show(surface, self.temperature, topleft=(left, top - 27))
        x = left + 28
        shake = round(2 * math.sin(hurt * 18) * hurt) if hurt > 0 else 0
        hearts = config.starting_hearts + player.bonus_hearts
        for i in range(hearts):
            hx, hy = x + shake + i * HEART_PITCH, top - 27
            if hurt > 0 and i == player.hearts:
                self._lost_heart(surface, hx, hy, 1 - hurt)
            else:
                show(surface, self._heart_image("full" if i < player.hearts else "empty"), topleft=(hx, hy))
        row = hearts * HEART_PITCH - 1
        self._line(surface, pygame.Rect(x, top - 15, row, 6), player.energy / player.max_energy,
                   "#f0bf3a", "#fff09a", "#3d3127", HEART_PITCH)
        self._line(surface, pygame.Rect(x, top - 8, row, 4), player.xp / player.xp_to_next_level,
                   "#5cc46e", "#9be58f", "#24372b")
        self._text(surface, f"NV {player.level}", (x + row + 4, top - 14))
        for i in range(HOTBAR_SIZE):
            self._bar_slot(surface, pygame.Rect(slot_rect(config, i, False)), player.inventory.slots[i],
                           i == player.inventory.selected)
        return pygame.Rect(left - 1, top - HUD_HEADROOM, width + 2, height + HUD_HEADROOM + 1)

    def _lost_heart(self, surface, hx, hy, t):
        heart = self._heart_image("full")
        w, h = heart.get_size()
        if t < .25:
            grow = 2 * round(t * 8)
            flash = pygame.transform.scale(self._heart_image("flash"), (w + grow, h + grow))
            show(surface, flash, topleft=(hx - grow // 2, hy - grow // 2))
            return
        k = (t - .25) / .75
        drop, spread = round(10 * k * k), round(4 * k)
        half = w // 2 + 1
        show(surface, heart.subsurface((0, 0, half, h)), topleft=(hx - spread, hy + drop))
        show(surface, heart.subsurface((half, 0, w - half, h)), topleft=(hx + half + spread, hy + drop))

    def _label(self, surface, rect, text, scale=2, color=CREAM):
        w, h = self.font.size(text, scale)
        self._text(surface, text, (rect.centerx - w // 2, rect.centery - h // 2), color, scale)

    def _recipe_panel(self, surface, inventory, panel, layout):
        title = pygame.Rect(layout.title)
        pygame.draw.rect(surface, PANEL, title, border_radius=6)
        self._label(surface, title, TITLES[panel.equipment])
        station = panel.production
        pointer = panel.pointer
        tooltip = None
        if station is not None:
            output = pygame.Rect(layout.output)
            pygame.draw.rect(surface, PANEL, output, border_radius=5)
            if station.recipe:
                show(surface, icon(station.recipe.product), center=output.center)
                count = f"{station.ready}/{station.ready + station.pending}"
                self._text(surface, count, (output.right+5 - self.font.size(count, 2)[0], output.bottom - 10), scale=2)
                if contains(layout.output, pointer):
                    tooltip = ITEMS[station.recipe.product][0]
                cancel = pygame.Rect(layout.cancel)
                pygame.draw.ellipse(surface, PANEL, cancel)
                self._label(surface, cancel, "X", 1, SHORT if station.pending else MUTED)
                if contains(layout.cancel, pointer):
                    tooltip = "Cancelar pendentes"
            collect = pygame.Rect(layout.collect)
            pygame.draw.rect(surface, PANEL, collect, border_radius=11)
            self._label(surface, collect, "Recolher", 2, CREAM if station.outputs else MUTED)
            done = [(item, n) for item, n in station.outputs if not (station.recipe and item == station.recipe.product)]
            later = [(recipe.product, n) for recipe, n in station.queue]
            for side, items, color in ((-1, done, CREAM), (1, later, MUTED)):
                for i, (item, n) in enumerate(items):
                    box = pygame.Rect(0, 0, 26, 26)
                    if side < 0:
                        box.midright = (output.left - 4 - 26 * i, output.centery)
                    else:
                        box.midleft = (output.right + 20 + 26 * i, output.centery)
                    show(surface, mini_icon(item), center=box.center)
                    self._text(surface, str(n), (box.right - self.font.size(str(n), 1)[0], box.bottom - 6), color, 1)
                    if box.collidepoint(pointer or (-1, -1)):
                        tooltip = ITEMS[item][0]
        bounds = title.unionall([pygame.Rect(row) for row in layout.rows])
        for box, recipe in zip(layout.rows, shown_recipes(panel.equipment, inventory)):
            row = pygame.Rect(box)
            hovered = contains(box, pointer)
            pygame.draw.rect(surface, (59, 41, 33, 218) if hovered else PANEL, row, border_radius=5)
            if hovered:
                self._corners(surface, row)
                tooltip = ITEMS[recipe.product][0]
            show(surface, icon(recipe.product), midleft=(row.left + 6, row.centery))
            for i, (item, required) in enumerate(reversed(recipe.costs.items())):
                right = row.right - 5 - 44 * i
                ingredient = pygame.Rect(right - 39, row.top, 39, row.height)
                show(surface, icon(item), center=(ingredient.centerx - 3, row.centery))
                number = str(required)
                color = CREAM if inventory.quantity(item) >= required else SHORT
                self._text(surface, number, (right - self.font.size(number, 2)[0], row.bottom - 16), color, 2)
                if hovered and ingredient.collidepoint(pointer):
                    tooltip = ITEMS[item][0]
        if panel.message:
            w, h = self.font.size(panel.message)
            note = pygame.Rect(0, bounds.bottom + 3, w + 12, h + 6)
            note.centerx = title.centerx
            note.clamp_ip(surface.get_rect())
            pygame.draw.rect(surface, PANEL, note, border_radius=4)
            self._label(surface, note, panel.message, 1)
            bounds.union_ip(note)
        if tooltip:
            w, h = self.font.size(tooltip)
            tip = pygame.Rect(int(pointer[0])+8, int(pointer[1])-19, w+10, h+6).clamp(surface.get_rect())
            pygame.draw.rect(surface, PANEL, tip, border_radius=4)
            self._label(surface, tip, tooltip, 1)
            bounds.union_ip(tip)
        return bounds

    @staticmethod
    def _corners(surface, rect):
        for x, dx in ((rect.left+1, 1), (rect.right-2, -1)):
            for y, dy in ((rect.top+1, 1), (rect.bottom-2, -1)):
                pygame.draw.lines(surface, CREAM, False,
                                  [(x, y+dy*7), (x, y+dy*2), (x+dx*2, y), (x+dx*7, y)], 2)

    def draw_pack(self, surface, config, inventory, source, hover, chest, craft=None):
        paired = chest is not None
        layout = recipe_layout(config, craft.equipment, inventory) if craft and craft.equipment else None
        if layout and not layout.beside_bag:
            return self._recipe_panel(surface, inventory, craft, layout)
        bounds = pygame.Rect(inventory_panel(config, paired))
        if not paired:
            button = pygame.Rect(bench_button(config))
            pygame.draw.rect(surface, PANEL, button, border_radius=5)
            show(surface, icon("bench"), center=button.center)
            if craft and contains(bench_button(config), craft.pointer):
                self._corners(surface, button)
                self._text(surface, "Bancada", (button.x+3, button.bottom+3))
                bounds.union_ip(button.inflate(0, 24))
            bounds.union_ip(button)
        if layout:
            bounds.union_ip(self._recipe_panel(surface, inventory, craft, layout))
        groups = [(inventory, 0, "Inventário", HOTBAR_SIZE)]
        if paired:
            groups.append((chest, SLOT_COUNT, "Baú", CHEST_COLUMNS))
        tooltip = None
        for owner, offset, title, columns in groups:
            first = pygame.Rect(slot_rect(config, offset, True, paired))
            last = pygame.Rect(slot_rect(config, offset + columns - 1, True, paired))
            header = pygame.Rect(0, bounds.top, 152, 40)
            header.centerx = (first.left + last.right) // 2
            pygame.draw.rect(surface, (21, 16, 15, 226), header, border_radius=6)
            w, h = self.font.size(title, 2)
            self._text(surface, title, (header.centerx-w//2, header.centery-h//2), scale=2)
            for i, stack in enumerate(owner.slots, offset):
                rect = pygame.Rect(slot_rect(config, i, True, paired))
                self._slot(surface, rect, stack, large=True, marked=i in (source, hover, inventory.selected))
                if i == hover and stack:
                    tooltip = (rect, ITEMS[stack.item][0] if stack.item in ITEMS else stack.item)
        if tooltip:
            slot, name = tooltip
            w, h = self.font.size(name, 2)
            box = pygame.Rect(slot.right-6, slot.top-10, w+12, h+8).clamp(surface.get_rect())
            pygame.draw.rect(surface, (23, 18, 16, 235), box, border_radius=4)
            self._text(surface, name, (box.x+6, box.y+4), scale=2)
            bounds.union_ip(box)
        return bounds


class ThinMeter(GameMeter):
    def __init__(self, box, fraction, fill, light, track, notch=0) -> None:
        super().__init__(box, fraction)
        self.cor_barra, self.cor_fundo, self.light, self.notch = fill, track, light, notch

    def paint(self, screen) -> None:
        box = self.rect
        InventoryHUD._chamfer(screen, box, INK)
        inner = box.inflate(-2, -2)
        pygame.draw.rect(screen, self.cor_fundo, inner)
        width = max(0, min(inner.width, round(inner.width * self.fraction)))
        if width:
            pygame.draw.rect(screen, self.cor_barra, (inner.x, inner.y, width, inner.height))
            pygame.draw.line(screen, self.light, inner.topleft, (inner.x + width - 1, inner.y))
        if self.notch:
            for x in range(box.x + self.notch - 1, inner.right - 1, self.notch):
                pygame.draw.line(screen, NOTCH, (x, inner.y), (x, inner.bottom - 1))

from __future__ import annotations

import math

import pygame

import spawnbound.pplay_media  # noqa: F401
from PPlay.gameimage import GameImage
from PPlay.gameobject import GameObject
from PPlay.keyboard import Keyboard
from PPlay.mouse import Mouse
from PPlay.sprite import Sprite
from PPlay.tween import Tween
from PPlay.uikit import Button, ProgressBar
from PPlay.window import Window

PLATE = (30, 18, 14, 222)
PLATE_HOVER = (64, 38, 26, 236)
GOLD = (221, 181, 110)
CREAM = (255, 243, 206)
DIM = (150, 136, 122)
SHADOW = (12, 8, 8)


def window() -> Window:
    # Os testes precisam do objeto Window do PPlay mesmo quando não abrem uma janela.
    if Window._instance is None:
        made = Window.__new__(Window)
        made.eventos, made.cor_fundo, made._delta_time = [], (0, 0, 0, 0), 0.
        made.keyboard, made.mouse = Keyboard(), Mouse()
    return Window._instance


def draw_on(surface: pygame.Surface, *objects) -> None:
    # Os objetos do PPlay desenham em window.screen. O alvo anterior precisa ser restaurado após o desenho.
    screen = window()
    previous = getattr(screen, "screen", None)
    screen.screen = surface
    try:
        for obj in objects:
            obj.draw()
    finally:
        screen.screen = previous


class Box(GameObject):
    def __init__(self, rect) -> None:
        super().__init__()
        self.x, self.y, self.width, self.height = rect


class Pointer(Box):
    def __init__(self, point) -> None:
        super().__init__((math.floor(point[0]), math.floor(point[1]), 1, 1))


def pointed(rect, point) -> bool:
    return point is not None and Box(rect).collided(Pointer(point))


class GameButton(Button):
    def __init__(self, rect, text: str = "", font=None, *, enabled: bool = True, edge: bool = True,
                 color=CREAM, dim=DIM, detail: str = "", detail_color=None, radius: int = 8) -> None:
        rect = pygame.Rect(rect)
        super().__init__(rect.width, rect.height, text)
        self.set_position(rect.x, rect.y)
        self.font, self.enabled, self.edge, self.radius = font, enabled, edge, radius
        self.cor_texto, self.dim = color, dim
        self.detail, self.detail_color = detail, detail_color

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(self.x, self.y, self.width, self.height)

    def over(self, point) -> bool:
        return pointed(self.rect, point)

    def update(self, pointer=None, click=None) -> None:
        self.hovered = self.enabled and self.over(pointer)
        self.pressed = self.enabled and self.over(click)

    def is_clicked(self, click=None) -> bool:
        return self.enabled and self.over(click)

    def draw(self) -> None:
        screen, rect = Window.get_screen(), self.rect
        plate = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(plate, PLATE_HOVER if self.hovered else PLATE, plate.get_rect(), border_radius=self.radius)
        screen.blit(plate, rect)
        if self.hovered and self.edge:
            pygame.draw.rect(screen, GOLD, rect, 1, border_radius=self.radius)
        if not self.texto or self.font is None:
            return
        color = self.cor_texto if self.enabled else self.dim
        label = self.font.render(self.texto, color, 2, shadow=SHADOW)
        if not self.detail:
            screen.blit(label, label.get_rect(center=rect.center))
            return
        screen.blit(label, (rect.left + 14, rect.top + 9))
        detail = self.font.render(self.detail, self.detail_color if self.enabled else self.dim, 1, shadow=SHADOW)
        screen.blit(detail, (rect.left + 14, rect.top + 32))


class GameMeter(ProgressBar):
    def __init__(self, rect, value: float, maximum: float = 1.) -> None:
        rect = pygame.Rect(rect)
        super().__init__(rect.width, rect.height)
        self.set_position(rect.x, rect.y)
        self.valor_max = maximum
        self.set_value(value)

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(self.x, self.y, self.width, self.height)

    @property
    def fraction(self) -> float:
        return self.valor_atual / self.valor_max if self.valor_max else 0.

    def draw(self) -> None:
        self.paint(Window.get_screen())

    def paint(self, screen: pygame.Surface) -> None:
        raise NotImplementedError


class Picture(GameImage):
    def __init__(self, image: pygame.Surface, position=(0, 0), transparency: float = 255) -> None:
        GameObject.__init__(self)
        self.image = image
        self.width, self.height = image.get_size()
        self.rect = image.get_rect()
        self.set_position(*position)
        self.set_transparency(round(transparency))


def show(surface: pygame.Surface, image: pygame.Surface, transparency: float = 255, **anchor) -> pygame.Rect:
    rect = image.get_rect(**anchor)
    draw_on(surface, Picture(image, rect.topleft, transparency))
    return rect


class Strip(Sprite):
    def __init__(self, frames) -> None:
        GameObject.__init__(self)
        width = max(frame.get_width() for frame in frames)
        height = max(frame.get_height() for frame in frames)
        self.image = pygame.Surface((width * len(frames), height), pygame.SRCALPHA)
        for n, frame in enumerate(frames):
            self.image.blit(frame, (n * width, 0), special_flags=pygame.BLEND_RGBA_MAX)
        self.width, self.height = width, height
        self.rect = pygame.Rect(0, 0, width, height)
        self.total_frames, self.loop, self.frame_atual, self.rodando = len(frames), True, 0, False
        self.tempo_por_frame, self.tempo_acumulado = .1, 0
        self.vx = self.vy = 0
        self.no_chao, self.body = False, None


class Fade(GameObject):
    def __init__(self, transparency: float = 255) -> None:
        super().__init__()
        self.transparency = transparency

    def to(self, value: float, seconds: float, kind: str = "linear") -> None:
        Tween.to(self, "transparency", value, seconds, kind)


def advance_fades() -> None:
    window()
    Tween.update()


__all__ = ["Box", "Fade", "GameButton", "GameMeter", "Picture", "Pointer", "Strip", "advance_fades",
           "draw_on", "pointed", "show", "window"]

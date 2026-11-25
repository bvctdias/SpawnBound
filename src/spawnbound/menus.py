from __future__ import annotations

import hashlib
import math
import pickle
import secrets
import threading
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pygame

from spawnbound.paths import data_dir, resource_dir
from spawnbound import controls_menu
from spawnbound.audio import quiet
from spawnbound.config import GameConfig
from spawnbound.domain.coordinates import GridPos, WorldPos
from spawnbound.domain.model import ObjectKind, WorldObject
from spawnbound.domain.session import GameSession
from spawnbound.domain.terrain import mill_site
from spawnbound.input import InputFrame
from spawnbound.inventory_hud import CREAM, EDGE, GOLD, MUTED
from spawnbound.island_apart import make_session
from spawnbound.pplay_ui import GameButton, draw_on, pointed
from spawnbound.savegame import (SLOTS, SaveError, SlotInfo, latest_slot, list_slots, load_session, parse_seed,
                                 save_session)
from spawnbound.states import NO_TRANSITION, Transition, TransitionKind, door_ahead

GAME_TITLE = "SPAWNBOUND"
PLATE = (30, 18, 14, 222)
PLATE_HOVER = (64, 38, 26, 236)
PANEL = (21, 16, 15, 214)
FIELD = (12, 10, 10, 236)
LINE_PLATE = (21, 16, 15, 170)
DIM = (150, 136, 122)
ALERT = (240, 150, 120)
SHADOW = (12, 8, 8)
NIGHT_BLUE = (10, 14, 26)
def _rgb(color) -> tuple[int, int, int]:
    return tuple(pygame.Color(color))[:3]


SIZES = {"title": (0, 30), "text": (0, 16), "note": (0, 12), "button": (300, 38), "slot": (480, 50), "field": (300, 40)}
GAP = 8
UNSAVED_SECONDS = 5.
SEED_DIGITS = 10


@dataclass(frozen=True, slots=True)
class Item:
    key: str
    label: str
    kind: str = "button"
    enabled: bool = True
    detail: str = ""
    color: tuple = CREAM


def layout(items, config: GameConfig, top: int) -> list[pygame.Rect]:
    rects, y = [], top
    for item in items:
        width, height = SIZES[item.kind]
        rect = pygame.Rect(0, 0, width, height)
        rect.midtop = (config.virtual_width // 2, y)
        rects.append(rect)
        y = rect.bottom + GAP
    return rects


def item_at(items, config: GameConfig, top: int, point) -> str | None:
    if point is None:
        return None
    for item, rect in zip(items, layout(items, config, top)):
        if item.kind in ("button", "slot") and item.enabled and pointed(rect, point):
            return item.key
    return None


def draw_items(surface, font, items, config: GameConfig, top: int, hover: str | None = None,
               caret: bool = False, backdrop: bool = True) -> pygame.Rect:
    rects = layout(items, config, top)
    scales = {"title": 3, "text": 1, "note": 1}
    covered = None
    for item, rect in zip(items, rects):
        if item.kind in scales:
            width = font.size(item.label, scales[item.kind])[0]
            rect = pygame.Rect(rect.centerx - width // 2, rect.top, width, rect.height)
        covered = rect.copy() if covered is None else covered.union(rect)
    if covered is None:
        return pygame.Rect(0, 0, 0, 0)
    if backdrop:
        back = covered.inflate(48, 32)
        plate = pygame.Surface(back.size, pygame.SRCALPHA)
        pygame.draw.rect(plate, PANEL, plate.get_rect(), border_radius=10)
        surface.blit(plate, back)
        pygame.draw.rect(surface, EDGE, back, 2, border_radius=10)
        covered = back
    for item, rect in zip(items, rects):
        if item.kind in scales:
            color = item.color if item.kind != "note" or item.color != CREAM else MUTED
            label = font.render(item.label, _rgb(color), scales[item.kind], shadow=SHADOW)
            if not backdrop and item.kind != "title":
                strip = label.get_rect(midtop=rect.midtop).inflate(16, 8)
                plate = pygame.Surface(strip.size, pygame.SRCALPHA)
                pygame.draw.rect(plate, LINE_PLATE, plate.get_rect(), border_radius=4)
                surface.blit(plate, strip)
            surface.blit(label, label.get_rect(midtop=rect.midtop))
            continue
        lit = item.enabled and hover == item.key
        if item.kind == "field":
            box = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(box, FIELD, box.get_rect(), border_radius=6)
            surface.blit(box, rect)
            pygame.draw.rect(surface, GOLD, rect, 1, border_radius=6)
            text = item.label + ("_" if caret else " ")
            shown = font.render(text if item.label else ("_" if caret else ""), _rgb(CREAM), 2, shadow=SHADOW)
            surface.blit(shown, shown.get_rect(midleft=(rect.left + 14, rect.centery)))
            if not item.label:
                hint = font.render(item.detail, _rgb(DIM), 1, shadow=SHADOW)
                surface.blit(hint, hint.get_rect(midright=(rect.right - 12, rect.centery)))
            continue
        button = GameButton(rect, item.label, font, enabled=item.enabled, color=_rgb(CREAM), dim=_rgb(DIM),
                            detail=item.detail if item.kind == "slot" else "", detail_color=_rgb(MUTED))
        button.hovered = lit
        draw_on(surface, button)
    return covered


def prepare_session(session: GameSession) -> None:
    session.spaces.prepare(session.island_life.world)
    session.navigation
    current = session.world
    island = session.island_life.world
    if island is not current:
        try:
            session.world = island
            session.navigation
        finally:
            session.world = current


def slot_detail(info: SlotInfo | None) -> str:
    if info is None:
        return "vazio"
    if not info.compatible:
        return "save de outra versão do jogo" if info.seed else "save danificado"
    return f"{info.place} - seed {info.seed} - {info.played} - {info.date}"


MENU_SEED = 1234
SCENE_SPEED = 3.
SCENE_START = 8.
FADE_SECONDS = 1.2
CAMERA_OFFSET = -11.
PAN_SECONDS = 90.
PAN_TILES = 4.
VIEW_WAIT = 5.
# A imagem salva cobre a janela enquanto a ilha do menu termina de carregar.
CACHE_DIR = data_dir() / "cache" / "menu"
CACHE_VERSION = 1
INTRO_SECONDS = .3
COVER_SECONDS = .6


def _digest(head: str, files) -> str:
    digest = hashlib.blake2b(head.encode(), digest_size=10)
    for path in sorted(files):
        digest.update(path.relative_to(resource_dir()).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def scene_keys(config: GameConfig, seed: int, size: int | None) -> tuple[str, str]:
    package = Path(__file__).resolve().parent
    art = resource_dir() / "assets" / "native_32"
    world = [*package.joinpath("domain").rglob("*.py"), package / "menus.py"]
    island = _digest(repr((CACHE_VERSION, seed, size, config)), world)
    rest = [path for path in package.rglob("*.py") if path not in world]
    look = _digest(island, [*rest, *(path for path in art.rglob("*") if path.is_file())])
    return island, look


class MenuScene:
    def __init__(self, config: GameConfig, seed: int = MENU_SEED, size: int | None = 128,
                 cache: Path | None = None):
        self.config, self.seed, self.size = config, seed, size
        self.session: GameSession | None = None
        self.elapsed = 0.
        self.shown_at = 0.
        self._built: GameSession | None = None
        self.view_ready: bool | None = None
        self._view_wait = 0.
        self.cache = cache
        self._keys = scene_keys(config, seed, size) if cache is not None else None
        self.picture: pygame.Surface | None = None
        self._picture_path: Path | None = None
        self._stale = False
        self._replacement: pygame.Surface | None = None
        self._covering = False
        self._thread = threading.Thread(target=self._build, name="menu island", daemon=True)
        self._thread.start()

    def _build(self) -> None:
        session = self._open_kept()
        if session is None:
            session = self._make()
            self._keep(session)
        self._built = session

    def _island_path(self) -> Path:
        return self.cache / f"ilha-{self._keys[0]}.bin"

    def _open_kept(self) -> GameSession | None:
        if self._keys is None:
            return None
        try:
            session = pickle.loads(zlib.decompress(self._island_path().read_bytes()))
        except Exception:
            return None
        if not isinstance(session, GameSession):
            return None
        session.config = self.config
        session._navigation = {}
        return session

    def _keep(self, session: GameSession) -> None:
        if self._keys is None:
            return
        try:
            self.cache.mkdir(parents=True, exist_ok=True)
            path = self._island_path()
            for old in self.cache.glob("ilha-*"):
                if old != path:
                    old.unlink()
            temporary = path.with_suffix(".tmp")
            temporary.write_bytes(zlib.compress(pickle.dumps(session, protocol=pickle.HIGHEST_PROTOCOL), 1))
            temporary.replace(path)
        except Exception:  # Mesmo sem permissão para gravar o cache, a cena atual pode abrir.
            pass

    def backdrop(self, renderer) -> pygame.Surface | None:
        if self._keys is not None and self._picture_path is None:
            name = getattr(renderer, "picture_key", None)
            if name is None:
                return None
            self._picture_path = self.cache / f"vista-{name()}.png"
            try:
                picture = pygame.image.load(str(self._picture_path))
                self.picture = picture.convert() if pygame.display.get_surface() is not None else picture
                self._stale = self._picture_path.with_suffix(".chave").read_text("ascii") != self._keys[1]
            except Exception:
                self.picture, self._stale = None, False
        return self.picture

    def capture(self) -> "callable | None":
        if (self._picture_path is None or not self.ready or self.clock > 0
                or (self.picture is not None and not self._stale)):
            return None
        path, key = self._picture_path, self._keys[1]

        def save(view: pygame.Surface) -> None:
            self._replacement, self._stale = view, False

            def write() -> None:
                try:
                    temporary = path.with_name(path.stem + ".tmp.png")
                    pygame.image.save(view, str(temporary))
                    temporary.replace(path)
                    path.with_suffix(".chave").write_text(key, "ascii")
                except Exception:
                    pass

            threading.Thread(target=write, name="menu picture", daemon=True).start()

        return save

    def _make(self) -> GameSession:
        session = GameSession.create(self.seed, self.config, chunk_preview_size=self.size)
        world = session.world
        if world.chunk_preview_size:
            mill = world.objects.get(mill_site(world.spawn, world.chunk_preview_size))
            if mill is not None and mill.kind is ObjectKind.WINDMILL:
                mill.variant = "restored"
        for offset in (GridPos(2, 1), GridPos(1, 2), GridPos(2, 2), GridPos(-2, 1), GridPos(1, -2)):
            cell = (world.camp or world.spawn) + offset
            if session.can_place(cell):
                world.objects[cell] = WorldObject.create(cell, ObjectKind.CAMPFIRE, elevation=world.elevation_at(cell))
                world.placed_fires.add(cell)
                break
        session.wildlife.mobs = {uid: mob for uid, mob in session.wildlife.mobs.items()
                                 if not mob.hostile}
        session.cycle_seconds = SCENE_START
        return session

    @property
    def built(self) -> GameSession | None:
        return self._built if self.session is None else None

    def hide(self) -> None:
        if self.session is not None:
            self._built, self.session = self.session, None
            self._built.cycle_seconds = SCENE_START
            self.view_ready, self._view_wait = False, 0.

    @property
    def ready(self) -> bool:
        return self.session is not None

    @property
    def camera(self) -> WorldPos:
        return self.camera_over(self.session.world)

    @property
    def clock(self) -> float:
        return self.elapsed - self.shown_at if self.session is not None else 0.

    def camera_over(self, world) -> WorldPos:
        camp = world.camp or world.spawn
        swing = math.sin(2 * math.pi * self.clock / PAN_SECONDS) * PAN_TILES
        return WorldPos(camp.x + CAMERA_OFFSET + swing, camp.y + CAMERA_OFFSET - swing, float(world.elevation_at(camp)))

    @property
    def veil(self) -> float:
        if self.ready and not self._covering:
            return max(0., 1 - self.clock / FADE_SECONDS)
        return max(0., 1 - self.elapsed / INTRO_SECONDS) if self.picture is not None else 1.

    @property
    def cover(self) -> float:
        if self.ready:
            return max(0., 1 - self.clock / COVER_SECONDS) if self._covering else 0.
        return 1. if self.picture is not None else 0.

    def update(self, seconds: float) -> None:
        dt = max(0., seconds)
        self.elapsed += dt
        if self.session is None:
            if self._built is None:
                return
            if self.view_ready is False and self._view_wait < VIEW_WAIT:
                self._view_wait += dt
                return
            self.session, self.shown_at = self._built, self.elapsed
            self._covering = self.picture is not None
            return  # O primeiro quadro da cena deve coincidir com a imagem salva.
        if self._replacement is not None and self.cover == 0:
            self.picture, self._replacement = self._replacement, None
        session = self.session
        duration = sum(self.config.phase_durations)
        session.cycle_seconds = (SCENE_START + (self.elapsed - self.shown_at) * SCENE_SPEED) % duration
        session.production_seconds += dt
        life = session.wildlife
        life.grace = 60.
        life.tick(dt, self.camera)
        if any(mob.hostile for mob in life.mobs.values()):
            life.mobs = {uid: mob for uid, mob in life.mobs.items() if not mob.hostile}
        session.school.advance(session.world, self.camera, dt)


SEED_LIMIT = 2_147_483_647
AHEAD_AFTER = 1.5
BUSY_QUIET = .25


class Ahead:
    def __init__(self, build, key=None) -> None:
        self.key = key
        self.session: GameSession | None = None
        self.error: Exception | None = None
        self.view = False
        self.drawn = False
        self._thread = threading.Thread(target=self._run, args=(build,), name="menu ahead", daemon=True)
        self._thread.start()

    def _run(self, build) -> None:
        try:
            self.session = build()
        except Exception as error:
            self.error = error

    @property
    def running(self) -> bool:
        return self._thread.is_alive()

    def wait(self) -> GameSession:
        self._thread.join()
        if self.error is not None:
            raise self.error
        return self.session


@dataclass(slots=True)
class MainMenuState:
    config: GameConfig
    scene: MenuScene
    island_size: int | None = 128
    play_sound: Callable[[str], None] = field(default=quiet, kw_only=True)
    folder: Path | None = None
    transparent: bool = False
    ahead: bool = False
    screen: str = field(default="main", init=False)
    seed_text: str = field(default="", init=False)
    message: str = field(default="", init=False)
    pointer: tuple[float, float] | None = field(default=None, init=False)
    slots: list = field(default_factory=list, init=False)
    latest: int | None = field(default=None, init=False)
    _built: GameSession | None = field(default=None, init=False)
    _error: str = field(default="", init=False)
    _builder: threading.Thread | None = field(default=None, init=False)
    _loading: int | None = field(default=None, init=False)
    _back: str = field(default="new", init=False)
    _view_ready: bool | None = field(default=None, init=False)
    _view_wait: float = field(default=0., init=False)
    _busy_time: float = field(default=0., init=False)
    _spare: Ahead | None = field(default=None, init=False)
    _kept: Ahead | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        self.slots = list_slots(self.folder)
        self.latest = latest_slot(self.folder)

    @property
    def top(self) -> int:
        return {"main": 236, "new": 170, "busy": 220, "load": 120}[self.screen]

    def items(self) -> list[Item]:
        alert = [Item("", self.message, "text", color=ALERT)] if self.message else []
        if self.screen == "main":
            items = [Item("new", "Novo jogo")]
            if self.latest is not None:
                items.append(Item("continue", "Continuar"))
            items += [Item("load", "Carregar jogo", enabled=any(s is not None and s.compatible for s in self.slots)),
                      Item("quit", "Sair")]
            if self.latest is not None:
                items.append(Item("", f"Continuar: espaço {self.latest} - {slot_detail(self.slots[self.latest - 1])}",
                                  "note"))
            return items + alert
        if self.screen == "new":
            return [Item("", "NOVO JOGO", "title"),
                    Item("", "Digite a seed da ilha ou deixe vazio para sortear.", "text"),
                    Item("field", self.seed_text, "field", detail="sorteada"),
                    Item("start", "Começar"), Item("back", "Voltar")] + alert
        if self.screen == "busy":
            if self._busy_time < BUSY_QUIET:
                return []
            if self._loading is not None:
                return [Item("", "CARREGAR JOGO", "title"), Item("", f"Abrindo o espaço {self._loading}...", "text")]
            return [Item("", "NOVO JOGO", "title"), Item("", "Gerando a ilha...", "text")]
        rows = [Item(f"slot{n}", f"Espaço {n}", "slot", enabled=info is not None and info.compatible,
                     detail=slot_detail(info)) for n, info in enumerate(self.slots, 1)]
        return [Item("", "CARREGAR JOGO", "title"), *rows, Item("back", "Voltar")] + alert

    def step(self, frame: InputFrame, delta_time: float) -> Transition:
        if frame.quit_requested or frame.close_requested:
            return Transition(TransitionKind.QUIT)
        self.scene.update(delta_time)
        self.pointer = frame.pointer
        if self.screen == "busy":
            return self._finish_busy(delta_time)
        self._prepare_ahead()
        choice = item_at(self.items(), self.config, self.top, frame.destination_click)
        if choice or (self.screen == "new" and frame.enter_pressed) or (self.screen != "main" and frame.pause_pressed):
            self.play_sound("click")
        if self.screen == "main":
            if choice == "new":
                self.screen, self.seed_text, self.message = "new", "", ""
            elif choice == "continue":
                return self._load(self.latest)
            elif choice == "load":
                self.refresh()
                self.screen, self.message = "load", ""
            elif choice == "quit":
                return Transition(TransitionKind.QUIT)
        elif self.screen == "new":
            for character in frame.typed:
                if character.isdigit() and len(self.seed_text) < SEED_DIGITS:
                    self.seed_text += character
            if frame.backspace_pressed:
                self.seed_text = self.seed_text[:-1]
            if choice == "start" or frame.enter_pressed:
                self._start_new_game()
            elif choice == "back" or frame.pause_pressed:
                self.screen, self.message = "main", ""
        elif self.screen == "load":
            if choice and choice.startswith("slot"):
                return self._load(int(choice[4:]))
            if choice == "back" or frame.pause_pressed:
                self.screen, self.message = "main", ""
        return NO_TRANSITION

    def _start_new_game(self) -> None:
        seed = parse_seed(self.seed_text)
        spare, self._spare = self._spare, None
        if seed is None and spare is not None and spare.error is None:
            self._work(spare.wait, None, "new")
            return
        if seed is None:
            seed = secrets.randbelow(SEED_LIMIT)
        self._work(lambda: self._new_session(seed), None, "new")

    def _new_session(self, seed: int) -> GameSession:
        try:
            session = make_session(seed, self.config, self.island_size)
        except Exception as error:
            raise SaveError(f"Não deu para gerar a ilha: {error}") from error
        prepare_session(session)
        return session

    def _load(self, slot: int | None) -> Transition:
        if slot is None:
            return NO_TRANSITION
        kept, self._kept = self._kept, None
        if kept is not None and kept.error is None and kept.key == self._slot_key(slot):
            self._work(kept.wait, slot, self.screen)
        else:
            self._work(lambda: self._saved_session(slot), slot, self.screen)
        return NO_TRANSITION

    def _saved_session(self, slot: int) -> GameSession:
        session = load_session(slot, self.config, self.folder)
        prepare_session(session)
        session.last_message = f"Jogo carregado do espaço {slot}."
        return session

    def _slot_key(self, slot: int | None) -> tuple | None:
        info = self.slots[slot - 1] if slot is not None and 0 < slot <= len(self.slots) else None
        return (slot, info.saved_at) if info is not None and info.compatible else None

    def _prepare_ahead(self) -> None:
        if not self.ahead or not self.scene.ready or self.scene.clock < AHEAD_AFTER:
            return
        if any(game is not None and game.running for game in (self._spare, self._kept)):
            return
        if self._spare is None and self.island_size is not None:
            seed = secrets.randbelow(SEED_LIMIT)
            self._spare = Ahead(lambda: self._new_session(seed))
            return
        key = self._slot_key(self.latest)
        if key is not None and (self._kept is None or self._kept.key != key):
            self._kept = Ahead(lambda: self._saved_session(key[0]), key)

    def _work(self, build, slot: int | None, back: str) -> None:
        self._built, self._error, self._loading, self._back = None, "", slot, back
        self._view_ready, self._view_wait, self._busy_time = None, 0., 0.
        self.screen, self.message = "busy", ""

        def run():
            try:
                self._built = build()
            except SaveError as error:
                self._error = str(error)
            except Exception as error:
                self._error = f"Não deu para abrir o jogo: {error}"

        self._builder = threading.Thread(target=run, name="menu work", daemon=True)
        self._builder.start()

    def _finish_busy(self, delta_time: float = 0.) -> Transition:
        self._busy_time += max(0., delta_time)
        if self._builder is not None and self._builder.is_alive():
            return NO_TRANSITION
        if self._built is None:
            if self._loading is not None:
                self.refresh()
            self.screen, self.message = self._back, self._error or "Não deu para abrir o jogo."
            return NO_TRANSITION
        if self._view_ready is False and self._view_wait < VIEW_WAIT:
            self._view_wait += max(0., delta_time)
            return NO_TRANSITION
        session, self._built = self._built, None
        return Transition(TransitionKind.START, session=session, slot=self._loading)

    def paint(self, surface, config: GameConfig, font) -> pygame.Rect:
        items = self.items()
        hover = item_at(items, config, self.top, self.pointer)
        caret = int(self.scene.elapsed * 2.5) % 2 == 0
        if self.screen == "main":
            title = font.render(GAME_TITLE, _rgb(CREAM), 7, shadow=SHADOW)
            surface.blit(title, title.get_rect(center=(config.virtual_width // 2, 128)))
            draw_items(surface, font, items, config, self.top, hover, backdrop=False)
            hint = font.render("F alterna janela e tela cheia", _rgb(MUTED), 1, shadow=SHADOW)
            surface.blit(hint, hint.get_rect(bottomleft=(16, config.virtual_height - 12)))
        else:
            draw_items(surface, font, items, config, self.top, hover, caret)
        return surface.get_rect()

    def draw(self, renderer) -> None:
        scene = self.scene
        camera = scene.camera if scene.ready else None
        renderer.draw_menu(scene.session, (camera.x, camera.y, camera.z) if camera else None, self.paint, scene.veil,
                           backdrop=scene.backdrop(renderer), cover=scene.cover, capture=scene.capture())
        self._draw_ahead(renderer)

    def _draw_ahead(self, renderer) -> None:
        prepare = getattr(renderer, "prepare_arrival", None)
        if prepare is None:
            return
        scene = self.scene
        if scene.session is None:
            built = scene.built
            scene.view_ready = built is not None and prepare(built, built.world, scene.camera_over(built.world),
                                                             veiled=True)
        if self.screen == "busy":
            done = self._builder is None or not self._builder.is_alive()
            session = self._built if done else None
            ready = session is not None and prepare(session, session.world, session.player.position3d, veiled=True)
            landing = door_ahead(session) if ready else None
            self._view_ready = ready and (landing is None or prepare(session, *landing, veiled=True))
        elif scene.session is not None:
            self._draw_games_ahead(prepare)

    def _draw_games_ahead(self, prepare) -> None:
        for game in (self._spare, self._kept):
            session = game.session if game is not None else None
            if session is None or game.drawn:
                continue
            if not game.view:
                game.view = prepare(session, session.world, session.player.position3d, veiled=True)
                game.drawn = game.view and game is self._kept
            else:
                landing = door_ahead(session)
                game.drawn = landing is None or prepare(session, *landing, veiled=True)
            return


@dataclass(slots=True)
class PauseMenuState:
    gameplay: object
    folder: Path | None = None
    transparent: bool = False
    screen: str = field(default="main", init=False)
    pending: str | None = field(default=None, init=False)
    target: int | None = field(default=None, init=False)
    message: str = field(default="", init=False)
    pointer: tuple[float, float] | None = field(default=None, init=False)
    slots: list = field(default_factory=list, init=False)

    @property
    def top(self) -> int:
        return {"main": 130, "controls": 0, "slots": 120, "overwrite": 170, "leave": 170}[self.screen]

    def items(self) -> list[Item]:
        alert = [Item("", self.message, "text", color=GOLD if self.message.startswith("Jogo salvo") else ALERT)
                 ] if self.message else []
        if self.screen == "main":
            return [Item("", "PAUSADO", "title"), Item("resume", "Continuar"), Item("save", "Salvar jogo"),
                    Item("controls", "Controles"), Item("menu", "Menu principal"), Item("quit", "Sair do jogo"),
                    *(alert or [Item("", "Esc para continuar", "note")])]
        if self.screen == "controls":
            return []
        if self.screen == "slots":
            current = self.gameplay.save_slot
            rows = [Item(f"slot{n}", f"Espaço {n}" + (" (esta partida)" if n == current else ""), "slot",
                         detail=slot_detail(info)) for n, info in enumerate(self.slots, 1)]
            return [Item("", "SALVAR JOGO", "title"), *rows, Item("back", "Voltar")] + alert
        if self.screen == "overwrite":
            return [Item("", "SOBRESCREVER?", "title"),
                    Item("", f"O espaço {self.target} guarda outra partida:", "text"),
                    Item("", slot_detail(self.slots[self.target - 1]), "note"),
                    Item("yes", "Sobrescrever"), Item("no", "Cancelar")]
        return [Item("", "SAIR SEM SALVAR?", "title"),
                Item("", "O que você fez desde o último save será perdido.", "text"),
                Item("save_leave", "Salvar e sair"), Item("leave", "Sair sem salvar"), Item("cancel", "Cancelar")]

    def step(self, frame: InputFrame, delta_time: float) -> Transition:
        del delta_time
        if frame.quit_requested:
            return self._leave("quit")
        self.pointer = frame.pointer
        choice = item_at(self.items(), self.gameplay.config, self.top, frame.destination_click)
        back = frame.pause_pressed
        controls_back = self.screen == "controls" and controls_menu.button_at(self.gameplay.config, frame.destination_click)
        if choice or back or controls_back:
            self.gameplay.play_sound("click")
        if self.screen == "main":
            if back or choice == "resume":
                return Transition(TransitionKind.POP)
            if choice == "save":
                self._open_slots(None)
            elif choice == "controls":
                self.screen, self.message = "controls", ""
            elif choice in ("menu", "quit"):
                return self._leave(choice)
        elif self.screen == "controls":
            if back or controls_back:
                self.screen = "main"
        elif self.screen == "slots":
            if choice and choice.startswith("slot"):
                slot = int(choice[4:])
                if self.slots[slot - 1] is None or slot == self.gameplay.save_slot:
                    return self._save(slot)
                self.screen, self.target = "overwrite", slot
            elif back or choice == "back":
                self.screen, self.pending = "main", None
        elif self.screen == "overwrite":
            if choice == "yes":
                return self._save(self.target)
            if back or choice == "no":
                self.screen = "slots"
        else:
            if choice == "save_leave":
                if self.gameplay.save_slot is not None:
                    return self._save(self.gameplay.save_slot)
                self._open_slots(self.pending)
            elif choice == "leave":
                return self._finish(self.pending)
            elif back or choice == "cancel":
                self.screen, self.pending = "main", None
        return NO_TRANSITION

    def _open_slots(self, pending: str | None) -> None:
        self.slots = list_slots(self.folder)
        self.screen, self.pending, self.message = "slots", pending, ""

    def ask_leave(self, action: str) -> None:
        self.screen, self.pending, self.message = "leave", action, ""

    def _leave(self, action: str) -> Transition:
        if self.gameplay.unsaved:
            self.ask_leave(action)
            return NO_TRANSITION
        return self._finish(action)

    @staticmethod
    def _finish(action: str | None) -> Transition:
        return Transition({"menu": TransitionKind.TO_MENU, "restart": TransitionKind.RESTART,
                           "new_seed": TransitionKind.NEW_SEED}.get(action, TransitionKind.QUIT))

    def _save(self, slot: int) -> Transition:
        try:
            save_session(self.gameplay.session, slot, self.folder)
        except SaveError as error:
            self.screen, self.pending, self.message = "main", None, str(error)
            return NO_TRANSITION
        self.gameplay.mark_saved(slot)
        if self.pending is not None:
            return self._finish(self.pending)
        self.screen, self.message = "main", f"Jogo salvo no espaço {slot}."
        return NO_TRANSITION

    def paint(self, surface, config: GameConfig, font) -> pygame.Rect:
        if self.screen == "controls":
            return controls_menu.draw(surface, config, font, controls_menu.button_at(config, self.pointer))
        items = self.items()
        return draw_items(surface, font, items, config, self.top, item_at(items, config, self.top, self.pointer))

    def draw(self, renderer) -> None:
        self.gameplay.draw(renderer, overlay=self.paint)


__all__ = ["MainMenuState", "MenuScene", "PauseMenuState", "SLOTS"]

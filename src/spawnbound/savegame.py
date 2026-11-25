from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import pickle
import random
import sys
import time
import zlib
from collections import deque
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from spawnbound.paths import data_dir
from spawnbound.config import GameConfig
from spawnbound.domain.mobs import Wildlife
from spawnbound.domain.model import SpaceKind
from spawnbound.domain.session import GameSession

SAVE_VERSION = 1  # Aumentar quando a leitura dos saves anteriores se tornar incompatível.
SLOTS = 3
MAGIC = b"SPAWNBOUND-SAVE\n"
SAVE_DIR = data_dir() / "saves"
SEED_LIMIT = 2_147_483_647
SEED_CHARS = 16


class SaveError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class SlotInfo:
    slot: int
    seed: int
    place: str
    played_seconds: float
    saved_at: float
    compatible: bool

    @property
    def played(self) -> str:
        minutes = int(self.played_seconds // 60)
        return f"{minutes // 60} h {minutes % 60:02d} min" if minutes >= 60 else f"{minutes} min"

    @property
    def date(self) -> str:
        return time.strftime("%d/%m %H:%M", time.localtime(self.saved_at))


def slot_path(slot: int, folder: Path | None = None) -> Path:
    if not 1 <= slot <= SLOTS:
        raise ValueError(f"slot {slot} outside 1..{SLOTS}")
    return (folder or SAVE_DIR) / f"espaco{slot}.sav"


def describe_place(session: GameSession) -> str:
    island = session.island
    name = island.name if island is not None else "Ilha"
    return name + {SpaceKind.CAVE: ", na mina", SpaceKind.INTERIOR: ", no abrigo"}.get(session.world.space_kind, "")


def save_session(session: GameSession, slot: int, folder: Path | None = None) -> SlotInfo:
    if session.voyage is not None:
        raise SaveError("Espere a travessia terminar para salvar.")
    info = SlotInfo(slot, session.home_world.seed, describe_place(session), session.played_seconds, time.time(), True)
    header = {"version": SAVE_VERSION, "seed": info.seed, "place": info.place,
              "played_seconds": round(info.played_seconds, 1), "saved_at": info.saved_at,
              "schema": schema(session)}
    navigation, config = session._navigation, session.config
    session._navigation, session.config = {}, None  # O mapa de navegação é reconstruído e a configuração é reaplicada ao carregar.
    try:
        body = zlib.compress(pickle.dumps(session, protocol=pickle.HIGHEST_PROTOCOL), 6)
    except Exception as error:
        raise SaveError(f"Não deu para salvar: {error}.") from error
    finally:
        session._navigation, session.config = navigation, config
    path = slot_path(slot, folder)
    temporary = path.with_suffix(".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_bytes(MAGIC + json.dumps(header).encode("utf-8") + b"\n" + body)
        os.replace(temporary, path)  # Substituir só depois da gravação preserva o save anterior se ela falhar.
    except OSError as error:
        raise SaveError("Não deu para gravar o arquivo do save.") from error
    return info


def _split(data: bytes) -> tuple[dict, bytes]:
    if not data.startswith(MAGIC):
        raise SaveError("Este arquivo não é um save do SpawnBound.")
    try:
        end = data.index(b"\n", len(MAGIC))
        header = json.loads(data[len(MAGIC):end].decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as error:
        raise SaveError("Este save está danificado.") from error
    if not isinstance(header, dict):
        raise SaveError("Este save está danificado.")
    return header, data[end + 1:]


def read_slot(slot: int, folder: Path | None = None) -> SlotInfo | None:
    path = slot_path(slot, folder)
    if not path.is_file():
        return None
    try:
        header, _ = _split(path.read_bytes())
        return SlotInfo(slot, int(header.get("seed", 0)), str(header.get("place", "?")),
                        float(header.get("played_seconds", 0.)), float(header.get("saved_at", path.stat().st_mtime)),
                        header.get("version") == SAVE_VERSION)
    except (SaveError, OSError, ValueError, TypeError):
        return SlotInfo(slot, 0, "save danificado", 0., path.stat().st_mtime, False)


def list_slots(folder: Path | None = None) -> list[SlotInfo | None]:
    return [read_slot(slot, folder) for slot in range(1, SLOTS + 1)]


def latest_slot(folder: Path | None = None) -> int | None:
    usable = [info for info in list_slots(folder) if info is not None and info.compatible]
    return max(usable, key=lambda info: info.saved_at).slot if usable else None


def load_session(slot: int, config: GameConfig, folder: Path | None = None) -> GameSession:
    path = slot_path(slot, folder)
    try:
        data = path.read_bytes()
    except FileNotFoundError as error:
        raise SaveError("Este espaço está vazio.") from error
    except OSError as error:
        raise SaveError("Não deu para ler o arquivo do save.") from error
    header, body = _split(data)
    if header.get("version") != SAVE_VERSION:
        raise SaveError("Este save é de outra versão do jogo.")
    try:
        # O pickle pode executar código ao carregar. A origem esperada é um save local do jogo.
        session = pickle.loads(zlib.decompress(body))
    except Exception as error:
        raise SaveError("Este save não abre nesta versão do jogo.") from error
    if not isinstance(session, GameSession):
        raise SaveError("Este save está danificado.")
    session.config = config
    session._navigation = {}
    try:
        upgrade(session, header.get("schema"))
    except SaveError:
        raise
    except Exception as error:
        raise SaveError("Este save não abre nesta versão do jogo.") from error
    return session


_LEAVES = (int, float, str, bytes, bool, type(None), Enum, random.Random, type)


def _domain_classes() -> list[type]:
    found = []
    for name, module in list(sys.modules.items()):
        if module is None or not name.startswith("spawnbound.domain."):
            continue
        found += [value for value in vars(module).values()
                  if isinstance(value, type) and value.__module__ == name and dataclasses.is_dataclass(value)]
    return found


def _key(cls: type) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


def _wildlife_names(session: GameSession) -> set[str]:
    names = getattr(Wildlife, "attribute_names", None)
    if names is None:
        names = frozenset(vars(Wildlife(session.world)))
    return set(names)


def schema(session: GameSession) -> dict[str, list[str]]:
    fields = {_key(cls): [f.name for f in dataclasses.fields(cls)] for cls in _domain_classes()}
    fields[_key(Wildlife)] = sorted(vars(session.wildlife))
    return fields


def upgrade(session: GameSession, saved: dict | None) -> None:
    changed: dict[type, tuple] = {}
    for cls in _domain_classes():
        names = [f.name for f in dataclasses.fields(cls)]
        old = None if saved is None else saved.get(_key(cls))
        if saved is not None and (old is None or old == names):
            continue
        # O pickle restaura estes campos por posição. Só o fim da sequência pode mudar.
        if old is not None and cls.__dataclass_params__.frozen and names[:len(old)] != old[:len(names)]:
            raise SaveError("Este save não abre nesta versão do jogo.")
        changed[cls] = dataclasses.fields(cls)
    expected = _wildlife_names(session)
    lives_changed = saved is None or set(saved.get(_key(Wildlife), ())) != expected
    if changed or lives_changed:
        _fill_missing(session, changed, expected)


def _default(field: dataclasses.Field):
    if field.default is not dataclasses.MISSING:
        return field.default
    if field.default_factory is not dataclasses.MISSING:
        return field.default_factory()
    raise SaveError("Este save não abre nesta versão do jogo.")


def _fill_missing(session: GameSession, changed: dict[type, tuple], expected: set[str]) -> None:
    names_of: dict[type, tuple[str, ...]] = {}
    lives, seen, stack = [], set(), [session]
    while stack:
        item = stack.pop()
        if isinstance(item, _LEAVES) or id(item) in seen:
            continue
        seen.add(id(item))
        if isinstance(item, dict):
            stack += item.keys()
            stack += item.values()
        elif isinstance(item, (list, tuple, set, frozenset, deque)):
            stack += item
        elif isinstance(item, Wildlife):
            lives.append(item)
            stack += vars(item).values()
        elif dataclasses.is_dataclass(item):
            cls = type(item)
            for field in changed.get(cls, ()):
                if not hasattr(item, field.name):
                    object.__setattr__(item, field.name, _default(field))
            names = names_of.get(cls)
            if names is None:
                names = names_of[cls] = tuple(f.name for f in dataclasses.fields(cls))
            stack += (getattr(item, name, None) for name in names)
        elif hasattr(item, "__dict__"):
            stack += vars(item).values()
    for life in lives:
        missing = expected - set(vars(life))
        if missing:
            fresh = Wildlife(life.world)
            for name in missing:
                setattr(life, name, getattr(fresh, name))


def parse_seed(text: str) -> int | None:
    text = text.strip()[:SEED_CHARS]
    if not text:
        return None
    if text.isdigit():
        return int(text) % SEED_LIMIT
    return int.from_bytes(hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest(), "big") % SEED_LIMIT

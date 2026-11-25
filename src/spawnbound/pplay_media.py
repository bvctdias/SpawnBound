from __future__ import annotations

import sys
from pathlib import Path

import pygame

from spawnbound.paths import resource_dir
# As ferramentas também carregam imagens sem passar pela configuração de caminhos do main.py.
_VENDORED = resource_dir() / "dependencias"
if str(_VENDORED) not in sys.path:
    sys.path.append(str(_VENDORED))
from PPlay.gameimage import GameImage  # noqa: E402


def load_image(path) -> pygame.Surface:
    # Sem janela, o GameImage não consegue converter a imagem. Ele também substitui arquivos ausentes por rosa.
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    if pygame.display.get_surface() is None:
        return pygame.image.load(str(path))
    return GameImage(str(path)).image


__all__ = ["load_image"]

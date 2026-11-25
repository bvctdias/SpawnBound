from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

from spawnbound.paths import resource_dir
from spawnbound.config import DEFAULT_CONFIG
from spawnbound.headless import smoke_session, validate_seeds


ISLAND_PREVIEW_SIZE = 128


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SpawnBound prototype")
    parser.add_argument("--seed", type=int, help="deterministic world seed")
    parser.add_argument("--start-at-estuary", action="store_true", help="start the playtest at this island's river mouth")
    parser.add_argument("--art-pack", type=Path, help="optional native prototype sprite manifest")
    # Comandos antigos ainda passam --fullscreen, hoje o padrão.
    parser.add_argument("--fullscreen", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--validate-seeds",
        type=int,
        metavar="N",
        help="validate N deterministic worlds without opening a window",
    )
    parser.add_argument(
        "--headless-smoke",
        action="store_true",
        help="create one session without importing PPlay/pygame",
    )
    parser.add_argument("--island-size", type=int, default=ISLAND_PREVIEW_SIZE,
                        help="exploration island side length (at least 8; default 128)")
    map_mode = parser.add_mutually_exclusive_group()
    map_mode.add_argument(
        "--chunk-preview",
        dest="chunk_preview",
        action="store_true",
        help="open the exploration island with procedural biome/vegetation noise",
    )
    map_mode.add_argument(
        "--prototype-map",
        dest="chunk_preview",
        action="store_false",
        help="open the previous two-island vertical-slice map",
    )
    parser.set_defaults(chunk_preview=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.island_size < 8:
        parser.error("--island-size must be at least 8")
    seed = args.seed if args.seed is not None else secrets.randbelow(2_147_483_647)

    if args.validate_seeds is not None:
        validate_seeds(args.validate_seeds)
        print(f"OK: {args.validate_seeds} seeds deterministicas com travessia validada.")
        return 0

    if args.headless_smoke:
        preview_size = args.island_size if args.chunk_preview else None
        session = smoke_session(seed, chunk_preview_size=preview_size)
        print(
            "OK: sessao criada "
            f"(seed={seed}, tiles={len(session.world.tile_map.tiles)}, "
            f"objetos={len(session.world.objects)})."
        )
        return 0

    try:
        from spawnbound.app import GameApplication

        preview_size = args.island_size if args.chunk_preview else None
        GameApplication(
            DEFAULT_CONFIG,
            seed,
            chunk_preview_size=preview_size,
            art_pack=args.art_pack or resource_dir() / "assets/native_32/manifest.json",
            fullscreen=True,
            start_at_estuary=args.start_at_estuary,
            start_in_menu=args.seed is None and not args.start_at_estuary,
        ).run()
    except ModuleNotFoundError as error:
        if error.name in {"pygame", "PPlay"}:
            print(
                "Dependencia de runtime ausente. No macOS, execute sh RUN_GAME_MAC.sh. "
                "No Windows, instale as dependências de requirements.txt. "
                "O Power PPlay acompanha o projeto em dependencias/PPlay.",
                file=sys.stderr,
            )
            return 2
        raise
    return 0

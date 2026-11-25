from __future__ import annotations

from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.generation import WorldGenerator, validate_world
from spawnbound.domain.session import GameSession


def validate_seeds(amount: int) -> None:
    if amount <= 0:
        raise ValueError("amount must be positive")

    generator = WorldGenerator()
    for seed in range(amount):
        first = generator.generate(seed)
        second = generator.generate(seed)
        if first.signature() != second.signature():
            raise AssertionError(f"seed {seed} is not deterministic")
        validation = validate_world(first)
        if not validation.valid:
            joined = "; ".join(validation.errors)
            raise AssertionError(f"seed {seed} is invalid: {joined}")


def smoke_session(seed: int, *, chunk_preview_size: int | None = None) -> GameSession:
    session = GameSession.create(
        seed,
        DEFAULT_CONFIG,
        chunk_preview_size=chunk_preview_size,
    )
    if session.world.seed != seed:
        raise AssertionError("session did not preserve its seed")
    return session

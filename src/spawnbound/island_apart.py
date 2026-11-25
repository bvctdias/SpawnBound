from __future__ import annotations

import multiprocessing
import pickle
import subprocess
import sys
import zlib
from pathlib import Path

MAGIC = b"SPAWNBOUND-ISLAND\n"
APART_FROM = 96  # Para ilhas menores, iniciar outro processo custa mais que gerar a ilha aqui.
TIMEOUT = 120.


def make_session(seed: int, config, size: int | None):
    from spawnbound.domain.session import GameSession
    if size is not None and size >= APART_FROM:
        data = _run_apart(seed, config, size)
        if data is not None:
            try:
                session = pickle.loads(zlib.decompress(data))
            except Exception:
                session = None
            if isinstance(session, GameSession):
                session.config = config
                session._navigation = {}
                return session
    return _make(seed, config, size)


def _make(seed: int, config, size: int | None):
    from spawnbound.domain.session import GameSession
    session = GameSession.create(seed, config, chunk_preview_size=size)
    session.spaces.prepare(session.island_life.world)
    return session


def _run_apart(seed: int, config, size: int | None) -> bytes | None:
    if getattr(sys, "frozen", False):
        return _frozen_island(seed, config, size)
    package = Path(__file__).resolve().parent
    paths = [str(package.parent), str(package.parents[1] / "dependencias")]
    code = f"import sys; sys.path[:0] = {paths!r}; from spawnbound.island_apart import child; child()"
    try:
        result = subprocess.run([sys.executable, "-I", "-B", "-c", code], input=pickle.dumps((seed, config, size)),
                                capture_output=True, timeout=TIMEOUT,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        return None
    output = result.stdout
    return output[len(MAGIC):] if result.returncode == 0 and output.startswith(MAGIC) else None


def _send_island(connection, seed, config, size):
    with connection:
        connection.send_bytes(_island_bytes(seed, config, size))


def _frozen_island(seed, config, size):
    context = multiprocessing.get_context("spawn")
    reader, writer = context.Pipe(duplex=False)
    process = context.Process(target=_send_island, args=(writer, seed, config, size), daemon=True)
    try:
        process.start()
        writer.close()
        return reader.recv_bytes() if reader.poll(TIMEOUT) else None
    except (EOFError, OSError, RuntimeError):
        return None
    finally:
        reader.close()
        writer.close()
        if process.pid is not None:
            process.join(1)
            if process.is_alive():
                process.terminate()
                process.join()
            process.close()


def _island_bytes(seed, config, size):
    return zlib.compress(pickle.dumps(_make(seed, config, size), protocol=pickle.HIGHEST_PROTOCOL), 1)


def child() -> None:
    seed, config, size = pickle.loads(sys.stdin.buffer.read())
    data = _island_bytes(seed, config, size)
    sys.stdout.buffer.write(MAGIC + data)
    sys.stdout.flush()

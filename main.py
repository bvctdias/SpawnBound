from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = PROJECT_ROOT / "src"
DEPENDENCIES_ROOT = PROJECT_ROOT / "dependencias"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))
if str(DEPENDENCIES_ROOT) not in sys.path:
    sys.path.insert(0, str(DEPENDENCIES_ROOT))

if __name__ == "__main__":
    from multiprocessing import freeze_support

    freeze_support()
    from spawnbound.cli import main

    raise SystemExit(main())

#!/bin/sh
set -eu
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
    if command -v python3.13 >/dev/null 2>&1; then
        interpreter=python3.13
    else
        interpreter=python3
    fi
    if ! "$interpreter" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
        echo "Instale o Python 3.13 universal2 para macOS em https://www.python.org/downloads/macos/ e abra um novo Terminal." >&2
        exit 1
    fi
    "$interpreter" -m venv .venv
fi

.venv/bin/python -m pip --disable-pip-version-check install --only-binary=:all: -r requirements.txt
exec .venv/bin/python main.py --art-pack assets/native_32/manifest.json "$@"

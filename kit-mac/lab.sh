#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PY_BIN="$(brew --prefix python@3.13 2>/dev/null || echo '/opt/homebrew')/bin/python3.13"
if [ ! -f "$PY_BIN" ]; then
  PY_BIN="python3"
fi
exec "$PY_BIN" "$ROOT/lab.py" "$@"

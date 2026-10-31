#!/bin/sh
set -eu
TASK_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TASK_PYTHON="$TASK_ROOT/tools/linux-x64/python/bin/python3"
if [ ! -f "$TASK_PYTHON" ]; then
    echo 'Kit incompleto. O professor precisa executar preparar.py montar antes de distribuir.' >&2
    exit 1
fi
# Windows/ZIP/pendrive podem perder os bits de execucao do Linux.
chmod u+x "$TASK_PYTHON"
"$TASK_PYTHON" -E - "$TASK_ROOT" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1]).resolve()
for name in json.loads((root / 'linux-executaveis.json').read_text()):
    path = (root / name).resolve()
    if path.is_relative_to(root) and path.is_file():
        path.chmod(path.stat().st_mode | 0o100)
PY
# Abrir BEM-VINDO.html no primeiro uso (fallback silencioso se xdg-open indisponível)
if [ ! -f "$TASK_ROOT/estado/linux-x64/credenciais.json" ]; then
    command -v xdg-open >/dev/null 2>&1 && xdg-open "$TASK_ROOT/BEM-VINDO.html" >/dev/null 2>&1 &
fi
exec "$TASK_PYTHON" -E "$TASK_ROOT/lab.py" "$@"

#!/bin/sh
set -eu

# 1. Localizar o kit (diretorio deste script)
TASK_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

# 2. Localizar Python de bootstrap (primeiro no armazenamento local, depois no pendrive)
LOCAL_BOOTSTRAP="${XDG_DATA_HOME:-$HOME/.local/share}/laboratorio-aulas/bootstrap/linux-x64/python/bin/python3"
TASK_PYTHON=""
if [ -f "$LOCAL_BOOTSTRAP" ]; then
    TASK_PYTHON="$LOCAL_BOOTSTRAP"
elif [ -f "$TASK_ROOT/ferramentas/linux-x64/python/bin/python3" ]; then
    TASK_PYTHON="$TASK_ROOT/ferramentas/linux-x64/python/bin/python3"
elif [ -f "$TASK_ROOT/tools/linux-x64/python/bin/python3" ]; then
    TASK_PYTHON="$TASK_ROOT/tools/linux-x64/python/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
    TASK_PYTHON="$(command -v python3)"
fi

if [ -z "$TASK_PYTHON" ]; then
    echo 'Kit incompleto. Python de inicializacao nao encontrado.' >&2
    exit 1
fi

chmod u+x "$TASK_PYTHON" 2>/dev/null || true

# Restaurar bits de execucao se o pendrive foi formatado em FAT/exFAT ou descompactado no Windows
manifest="$TASK_ROOT/ferramentas/linux-x64/linux-executaveis.json"
if [ ! -f "$manifest" ]; then
    manifest="$TASK_ROOT/tools/linux-x64/linux-executaveis.json"
fi
if [ ! -f "$manifest" ]; then
    manifest="$TASK_ROOT/linux-executaveis.json"
fi
if [ -f "$manifest" ]; then
    "$TASK_PYTHON" -E - "$TASK_ROOT" "$manifest" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1]).resolve()
manifest_file = pathlib.Path(sys.argv[2]).resolve()
try:
    for name in json.loads(manifest_file.read_text()):
        path = (root / name).resolve()
        if path.is_relative_to(root) and path.is_file():
            path.chmod(path.stat().st_mode | 0o755)
except Exception:
    pass
PY
fi

if [ ! -f "$TASK_ROOT/configuracoes/linux-x64/iniciado.txt" ]; then
    mkdir -p "$TASK_ROOT/configuracoes/linux-x64"
    touch "$TASK_ROOT/configuracoes/linux-x64/iniciado.txt"
    command -v xdg-open >/dev/null 2>&1 && xdg-open "$TASK_ROOT/BEM-VINDO.html" >/dev/null 2>&1 &
fi

exec "$TASK_PYTHON" -E "$TASK_ROOT/lab.py" "$@"

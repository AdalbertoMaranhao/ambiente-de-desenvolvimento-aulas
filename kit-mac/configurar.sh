#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if [ "$(uname -m)" != "arm64" ]; then
  echo "Este kit esta preparado para Apple Silicon (M1/M2/M3/M4), nao Intel." >&2
  exit 1
fi
if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew precisa estar instalado antes. Consulte https://brew.sh/." >&2
  exit 1
fi

mkdir -p "$ROOT/backups" "$ROOT/projetos/web" "$ROOT/projetos/java" "$ROOT/projetos/python" "$ROOT/dependencias/java"
HOMEBREW_BUNDLE_NO_UPGRADE=1 brew bundle install --file "$ROOT/Brewfile" --no-upgrade

if [ ! -f "$ROOT/dependencias/java/sqlite-jdbc.jar" ]; then
  echo "\n📦 Baixando driver SQLite JDBC para Java..."
  curl -fsSL -o "$ROOT/dependencias/java/sqlite-jdbc.jar" \
    "https://repo1.maven.org/maven2/org/xerial/sqlite-jdbc/3.54.1.0/sqlite-jdbc-3.54.1.0.jar"
fi

echo "\n✅ Ambiente do Mac configurado com sucesso!"
echo "--------------------------------------------------------"
echo "🛠️  Painel do Laboratório: execute ./lab.sh"
echo "🌐 Workspaces disponíveis:"
echo "   - Web (PHP & SQLite): code \"$ROOT/web.code-workspace\""
echo "   - POO Python:         code \"$ROOT/poo-python.code-workspace\""
echo "   - POO Java:           code \"$ROOT/poo-java.code-workspace\""
echo "💻 No Terminal do macOS, use: source \"$ROOT/ambiente.sh\""
echo "--------------------------------------------------------"

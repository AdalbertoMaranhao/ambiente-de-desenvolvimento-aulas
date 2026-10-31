#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
MARIADB_BASE="$(brew --prefix mariadb@11.4 2>/dev/null || echo '/opt/homebrew/opt/mariadb@11.4')"
BIN="$MARIADB_BASE/bin"
PIDFILE="$ROOT/estado/mariadb.pid"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "💾 Criando backup antes de encerrar..."
  "$ROOT/backup-mariadb.sh" aulas 2>/dev/null || true

  echo "⏹️  Parando MariaDB do laboratório..."
  "$BIN/mariadb-admin" --port=3307 --host=127.0.0.1 -u root -proot shutdown 2>/dev/null || kill "$(cat "$PIDFILE")" 2>/dev/null || true
  rm -f "$PIDFILE"
  echo "✅ MariaDB encerrado com segurança."
else
  echo "MariaDB do kit não está em execução."
fi

#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
MARIADB_BASE="$(brew --prefix mariadb@11.4 2>/dev/null || echo '/opt/homebrew/opt/mariadb@11.4')"
BIN="$MARIADB_BASE/bin"

db="${1:-aulas}"
case "$db" in
  ''|*[!A-Za-z0-9_]* ) echo "Nome de banco invalido: use letras, numeros e _" >&2; exit 2 ;;
esac

out_dir="$ROOT/backups"
mkdir -p "$out_dir"
out="$out_dir/${db}-mac-$(date +%Y%m%d-%H%M%S).sql"

"$BIN/mariadb-dump" --port=3307 --host=127.0.0.1 -u root -proot \
  --single-transaction --routines --events --databases "$db" > "$out"

printf "💾 Backup do banco '%s' salvo em: %s\n" "$db" "$out"

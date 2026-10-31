#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
MARIADB_BASE="$(brew --prefix mariadb@11.4 2>/dev/null || echo '/opt/homebrew/opt/mariadb@11.4')"
BIN="$MARIADB_BASE/bin"

if [ ! -d "$BIN" ]; then
  echo "MariaDB 11.4 não encontrado. Execute ./configurar.sh primeiro." >&2
  exit 1
fi

PORT=3307
STATE="$ROOT/estado/mariadb"
PIDFILE="$ROOT/estado/mariadb.pid"
LOGFILE="$ROOT/estado/mariadb.log"
mkdir -p "$ROOT/estado"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "✅ MariaDB deste kit já está em execução na porta $PORT."
  exit 0
fi

if [ ! -d "$STATE/mysql" ]; then
  echo "⏳ Inicializando banco de dados local do laboratório pela primeira vez..."
  "$BIN/mariadb-install-db" --basedir="$MARIADB_BASE" --datadir="$STATE" --auth-root-authentication-method=normal --skip-test-db >/dev/null 2>&1
fi

INIT_SQL="$ROOT/estado/bootstrap.sql"
cat <<'EOF' > "$INIT_SQL"
ALTER USER 'root'@'localhost' IDENTIFIED BY 'root';
CREATE USER IF NOT EXISTS 'root'@'127.0.0.1' IDENTIFIED BY 'root';
ALTER USER 'root'@'127.0.0.1' IDENTIFIED BY 'root';
GRANT ALL PRIVILEGES ON *.* TO 'root'@'127.0.0.1' WITH GRANT OPTION;
CREATE DATABASE IF NOT EXISTS aulas CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'aluno'@'127.0.0.1' IDENTIFIED BY 'aluno';
CREATE USER IF NOT EXISTS 'aluno'@'localhost' IDENTIFIED BY 'aluno';
GRANT ALL ON aulas.* TO 'aluno'@'127.0.0.1';
GRANT ALL ON aulas.* TO 'aluno'@'localhost';
FLUSH PRIVILEGES;
EOF

echo "🚀 Iniciando MariaDB na porta $PORT..."
"$BIN/mariadbd" --basedir="$MARIADB_BASE" --datadir="$STATE" \
  --bind-address=127.0.0.1 --port="$PORT" \
  --pid-file="$PIDFILE" --log-error="$LOGFILE" \
  --init-file="$INIT_SQL" >/dev/null 2>&1 &

for i in $(seq 1 30); do
  if "$BIN/mariadb-admin" --port="$PORT" --host=127.0.0.1 -u root -proot ping >/dev/null 2>&1; then
    echo "✅ MariaDB pronto na porta $PORT!"
    echo "   Host:    127.0.0.1 (Porta: $PORT)"
    echo "   Banco:   aulas"
    echo "   Aluno:   usuário 'aluno', senha 'aluno'"
    echo "   Root:    usuário 'root', senha 'root'"
    exit 0
  fi
  sleep 0.5
done

echo "⚠️  O MariaDB demorou para responder. Verifique $LOGFILE"

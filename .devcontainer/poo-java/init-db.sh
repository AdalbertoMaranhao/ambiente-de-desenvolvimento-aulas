#!/bin/bash
set -e

PORT=3307
DB_NAME="aulas"
DB_USER="aluno"
DB_PASSWORD="aluno"

if mysqladmin --port="$PORT" -u aluno -paluno ping >/dev/null 2>&1 || mysqladmin --port="$PORT" -u root -proot ping >/dev/null 2>&1; then
    exit 0
fi

mkdir -p /var/run/mysqld /var/lib/mysql
chown -R mysql:mysql /var/run/mysqld /var/lib/mysql

if [ ! -d /var/lib/mysql/mysql ]; then
    mariadb-install-db --user=mysql --datadir=/var/lib/mysql >/dev/null 2>&1
fi

mysqld_safe --port="$PORT" --bind-address=0.0.0.0 --datadir=/var/lib/mysql >/tmp/mariadb-init.log 2>&1 &

for i in $(seq 1 30); do
    if mysqladmin --port="$PORT" ping --silent 2>/dev/null; then
        break
    fi
    sleep 0.5
done

mysql --port="$PORT" -u root 2>/dev/null <<SQL || true
ALTER USER 'root'@'localhost' IDENTIFIED BY 'root';
CREATE USER IF NOT EXISTS 'root'@'127.0.0.1' IDENTIFIED BY 'root';
ALTER USER 'root'@'127.0.0.1' IDENTIFIED BY 'root';
CREATE USER IF NOT EXISTS 'root'@'%' IDENTIFIED BY 'root';
ALTER USER 'root'@'%' IDENTIFIED BY 'root';
GRANT ALL PRIVILEGES ON *.* TO 'root'@'127.0.0.1' WITH GRANT OPTION;
GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' WITH GRANT OPTION;
CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${DB_USER}'@'%' IDENTIFIED BY '${DB_PASSWORD}';
CREATE USER IF NOT EXISTS '${DB_USER}'@'127.0.0.1' IDENTIFIED BY '${DB_PASSWORD}';
CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASSWORD}';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'%';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'127.0.0.1';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'localhost';
FLUSH PRIVILEGES;
SQL

echo "✅ MariaDB pronto na porta ${PORT} (banco: ${DB_NAME}, usuário: ${DB_USER}, senha: ${DB_PASSWORD})"

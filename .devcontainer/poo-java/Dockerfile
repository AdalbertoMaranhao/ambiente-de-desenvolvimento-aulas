# syntax=docker/dockerfile:1
FROM eclipse-temurin:21-jdk

ENV DEBIAN_FRONTEND=noninteractive

# Instalar dependências básicas, sqlite e utilitários
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    sqlite3 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Baixar driver JDBC SQLite
RUN mkdir -p /opt/jdbc && \
    curl -fsSL -o /opt/jdbc/sqlite-jdbc.jar \
    "https://repo1.maven.org/maven2/org/xerial/sqlite-jdbc/3.54.1.0/sqlite-jdbc-3.54.1.0.jar"

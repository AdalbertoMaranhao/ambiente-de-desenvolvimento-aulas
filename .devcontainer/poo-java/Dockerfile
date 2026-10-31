# syntax=docker/dockerfile:1
FROM eclipse-temurin:21-jdk

ENV DEBIAN_FRONTEND=noninteractive

# Instalar dependências básicas, MariaDB e utilitários
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    mariadb-server \
    mariadb-client \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Baixar driver JDBC MariaDB
RUN mkdir -p /opt/jdbc && \
    curl -fsSL -o /opt/jdbc/mariadb-java-client.jar \
    "https://downloads.mariadb.com/Connectors/java/connector-j-3.5.11/mariadb-java-client-3.5.11.jar"

# Script de inicialização silenciosa do MariaDB
COPY init-db.sh /usr/local/bin/init-db.sh
RUN chmod +x /usr/local/bin/init-db.sh

# Variáveis padrão de banco
ENV DB_HOST=127.0.0.1
ENV DB_PORT=3307
ENV DB_NAME=aulas
ENV DB_USER=aluno
ENV DB_PASSWORD=aluno

EXPOSE 3307

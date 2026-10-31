# syntax=docker/dockerfile:1
FROM php:8.4-cli

ENV DEBIAN_FRONTEND=noninteractive

# Instalar dependências de sistema, MariaDB e utilitários
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    unzip \
    libzip-dev \
    libonig-dev \
    mariadb-server \
    mariadb-client \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Instalar extensões essenciais do PHP
RUN docker-php-ext-install -j$(nproc) \
    pdo \
    pdo_mysql \
    mysqli \
    zip \
    mbstring

# Instalar Composer oficial
COPY --from=composer:2 /usr/bin/composer /usr/local/bin/composer

# Script de inicialização silenciosa do MariaDB
COPY init-db.sh /usr/local/bin/init-db.sh
RUN chmod +x /usr/local/bin/init-db.sh

# Variáveis padrão de banco
ENV DB_HOST=127.0.0.1
ENV DB_PORT=3307
ENV DB_NAME=aulas
ENV DB_USER=aluno
ENV DB_PASSWORD=aluno

EXPOSE 3307 8080

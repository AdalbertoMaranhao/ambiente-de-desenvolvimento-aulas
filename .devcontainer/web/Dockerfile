# syntax=docker/dockerfile:1
FROM php:8.4-cli

ENV DEBIAN_FRONTEND=noninteractive

# Instalar dependências de sistema e utilitários
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    unzip \
    libzip-dev \
    libonig-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Instalar extensões essenciais do PHP
RUN docker-php-ext-install -j$(nproc) \
    zip \
    mbstring

# Instalar Composer oficial
COPY --from=composer:2 /usr/bin/composer /usr/local/bin/composer

EXPOSE 8080

# syntax=docker/dockerfile:1
FROM eclipse-temurin:21-jdk

ENV DEBIAN_FRONTEND=noninteractive

# Instalar dependências básicas e utilitários
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

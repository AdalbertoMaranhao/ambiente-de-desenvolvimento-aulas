# syntax=docker/dockerfile:1
FROM python:3.13-slim

ENV DEBIAN_FRONTEND=noninteractive

# Instalar dependências básicas, sqlite e utilitários
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    sqlite3 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

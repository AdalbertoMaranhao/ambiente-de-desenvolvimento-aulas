#!/usr/bin/env python3
"""
extensoes.py — Gerenciamento e Instalação Offline de Extensões VSIX no Armazenamento Local.

Responsabilidades:
  • Localizar arquivos VSIX no kit do pendrive (extensoes/<target>/*.vsix).
  • Validar integridade SHA-256 contra manifesto.
  • Consultar extensões já instaladas no SSD local para evitar reinstalações repetidas.
  • Instalar extensões ausentes via CLI do VS Code (--extensions-dir) de forma 100% offline.
  • Suportar fallback para extensões descompactadas existentes no kit.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def calcular_sha256(arquivo: Path) -> str:
    hasher = hashlib.sha256()
    with open(arquivo, "rb") as f:
        while chunk := f.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def obter_extensoes_instaladas(local_extensions: Path) -> set[str]:
    """Identifica quais extensões já estão instaladas no diretório local de extensões."""
    instaladas = set()
    manifest_local = local_extensions / "manifesto-instalacao.json"
    if manifest_local.exists():
        try:
            dados = json.loads(manifest_local.read_text(encoding="utf-8"))
            for item in dados.get("extensoes", []):
                identificador = item.get("id") or item.get("name")
                if identificador:
                    instaladas.add(identificador.lower())
        except Exception:
            pass

    # Também inspeciona as pastas existentes em local_extensions
    if local_extensions.exists():
        for item in local_extensions.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                # Formato padrão do VS Code: publisher.extname-version
                nome_base = item.name.rsplit("-", 1)[0].lower()
                instaladas.add(nome_base)
                instaladas.add(item.name.lower())

    return instaladas


def instalar_extensoes_locais(
    kit_root: Path,
    local_extensions: Path,
    target: str,
    disciplina: str,
    code_bin: Path | None = None
) -> dict[str, str]:
    """
    Instala as extensões VSIX do kit no diretório local do computador.
    Retorna dicionário {nome_extensao: status}.
    """
    local_extensions.mkdir(parents=True, exist_ok=True)
    resultados: dict[str, str] = {}

    # 1. Localizar manifesto de extensões do kit
    manifesto_candidatos = [
        kit_root / "manifestos" / "extensoes.json",
        kit_root / "extensoes" / "manifesto.json",
        kit_root / "extensoes" / target / "manifesto.json",
    ]
    manifesto_data = {}
    for mc in manifesto_candidatos:
        if mc.exists():
            try:
                manifesto_data = json.loads(mc.read_text(encoding="utf-8"))
                break
            except Exception:
                pass

    vsix_dir = kit_root / "extensoes" / target
    if not vsix_dir.exists():
        vsix_dir = kit_root / "extensoes"

    instaladas_previamente = obter_extensoes_instaladas(local_extensions)

    # 2. Localizar arquivos VSIX no kit
    arquivos_vsix = list(vsix_dir.glob("*.vsix")) if vsix_dir.exists() else []

    if arquivos_vsix and code_bin and code_bin.exists():
        for vsix_path in arquivos_vsix:
            ext_id = vsix_path.stem.lower()
            # Remover versão se presente no nome (ex: redhat.java-1.39.0 -> redhat.java)
            ext_id_simples = ext_id.rsplit("-", 1)[0] if "-" in ext_id else ext_id

            if ext_id_simples in instaladas_previamente or ext_id in instaladas_previamente:
                resultados[vsix_path.name] = "ja_instalada"
                continue

            # Validar SHA-256 se houver no manifesto
            sha_esperado = manifesto_data.get(vsix_path.name, {}).get("sha256")
            if sha_esperado:
                sha_obtido = calcular_sha256(vsix_path)
                if sha_obtido.lower() != sha_esperado.lower():
                    print(f"⚠️ Extensão {vsix_path.name} com hash corrompido. Pulando...")
                    resultados[vsix_path.name] = "hash_invalido"
                    continue

            # Executar instalação offline via CLI do VS Code
            print(f"🧩 Instalando extensão offline: {vsix_path.name}...")
            cmd = [
                str(code_bin),
                "--extensions-dir", str(local_extensions),
                "--install-extension", str(vsix_path),
                "--force"
            ]
            try:
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
                if res.returncode == 0:
                    resultados[vsix_path.name] = "instalada_sucesso"
                    instaladas_previamente.add(ext_id_simples)
                    instaladas_previamente.add(ext_id)
                else:
                    print(f"⚠️ Falha ao instalar {vsix_path.name}: {res.stderr.strip() or res.stdout.strip()}")
                    resultados[vsix_path.name] = "erro_instalacao"
            except Exception as e:
                print(f"⚠️ Exceção ao instalar {vsix_path.name}: {e}")
                resultados[vsix_path.name] = "erro_excecao"

    # 3. Fallback: Se o kit já possui pastas de extensões descompactadas em tools/extensions
    fallback_ext_dir = kit_root / "tools" / "extensions"
    if not fallback_ext_dir.exists():
        fallback_ext_dir = kit_root / "tools" / target / "extensions"

    if fallback_ext_dir.exists() and fallback_ext_dir.is_dir():
        for item in fallback_ext_dir.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                dest_item = local_extensions / item.name
                if not dest_item.exists():
                    try:
                        shutil.copytree(item, dest_item, dirs_exist_ok=True)
                        resultados[item.name] = "copiada_fallback"
                    except Exception:
                        pass
                else:
                    resultados[item.name] = "ja_instalada"

    # 4. Gravar manifesto local atualizado
    manifest_local = local_extensions / "manifesto-instalacao.json"
    manifest_local_data = {
        "disciplina": disciplina,
        "target": target,
        "extensoes": [{"id": k, "status": v} for k, v in resultados.items()]
    }
    try:
        manifest_local.write_text(json.dumps(manifest_local_data, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass

    return resultados

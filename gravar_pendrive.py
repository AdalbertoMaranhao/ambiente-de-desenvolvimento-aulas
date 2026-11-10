#!/usr/bin/env python3
"""
gravar_pendrive.py — Utilitário de Gravação e Preparação de Pendrives

Permite ao professor ou aluno gravar um Kit Universal (Web, POO Python ou POO Java)
diretamente em um pendrive (formatado em exFAT ou FAT32), validando integridade,
espaço em disco e permissões de execução.

Funciona de forma multiplataforma no macOS, Linux e Windows.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import sys
import zipfile

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / "dist"

KITS_MAP = {
    "web": ("kit-web.zip", "Desenvolvimento Web (PHP 8.5 + SQLite)"),
    "poo-python": ("kit-poo-python.zip", "POO com Python 3.13 + SQLite"),
    "poo-java": ("kit-poo-java.zip", "POO com Java 25 (Adoptium) + SQLite"),
}


def calcular_sha256(arquivo: Path) -> str:
    """Calcula o SHA-256 de um arquivo."""
    hasher = hashlib.sha256()
    with open(arquivo, "rb") as f:
        while chunk := f.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def obter_volumes_removiveis() -> list[dict[str, str | int]]:
    """Detecta partições ou volumes removíveis/montados de acordo com o SO."""
    volumes = []

    if sys.platform == "darwin":
        # macOS: volumes montados em /Volumes
        vols_dir = Path("/Volumes")
        if vols_dir.exists():
            for p in sorted(vols_dir.iterdir()):
                if p.is_dir() and not p.is_symlink():
                    name = p.name
                    # Ignorar disco principal e backups locais do sistema
                    if name in ("Macintosh HD", "Recovery", "Time Machine Backups", "Preboot"):
                        continue
                    try:
                        usage = shutil.disk_usage(p)
                        volumes.append({
                            "caminho": str(p),
                            "nome": name,
                            "livre_gb": round(usage.free / (1024**3), 2),
                            "total_gb": round(usage.total / (1024**3), 2),
                        })
                    except Exception:
                        pass

    elif sys.platform.startswith("linux"):
        # Linux: inspeciona /media e /run/media
        user = os.getenv("USER", "")
        candidatos = [
            Path("/media") / user if user else Path("/media"),
            Path("/run/media") / user if user else Path("/run/media"),
            Path("/media"),
        ]
        vistos = set()
        for base in candidatos:
            if base.exists() and base.is_dir():
                for p in sorted(base.iterdir()):
                    if p.is_dir() and str(p) not in vistos:
                        vistos.add(str(p))
                        try:
                            usage = shutil.disk_usage(p)
                            volumes.append({
                                "caminho": str(p),
                                "nome": p.name,
                                "livre_gb": round(usage.free / (1024**3), 2),
                                "total_gb": round(usage.total / (1024**3), 2),
                            })
                        except Exception:
                            pass

    elif sys.platform == "win32":
        # Windows: listar unidades lógicas
        import ctypes
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for letter in "EFGHIJKLMNOPQRSTUVWXYZ":
            if bitmask & (1 << (ord(letter) - ord("A"))):
                path_str = f"{letter}:\\"
                try:
                    usage = shutil.disk_usage(path_str)
                    volumes.append({
                        "caminho": path_str,
                        "nome": f"Unidade ({letter}:)",
                        "livre_gb": round(usage.free / (1024**3), 2),
                        "total_gb": round(usage.total / (1024**3), 2),
                    })
                except Exception:
                    pass

    return volumes


def validar_integridade_pacote(zip_path: Path) -> bool:
    """Valida o arquivo .zip comparando seu SHA256 com o .sha256 correspondente."""
    sha_file = zip_path.with_name(zip_path.name + ".sha256")
    if not sha_file.exists():
        print(f"⚠️  Arquivo {sha_file.name} não encontrado. Pulando verificação estrita de hash.")
        return True

    esperado = sha_file.read_text().strip().split()[0]
    print(f"⏳ Verificando integridade de {zip_path.name}...")
    obtido = calcular_sha256(zip_path)

    if obtido.lower() == esperado.lower():
        print("  ✅ Verificação SHA-256 aprovada.")
        return True
    else:
        print(f"  ❌ Erro de hash SHA-256!\n     Esperado: {esperado}\n     Obtido:   {obtido}")
        return False


def extrair_com_progresso(zip_path: Path, destino: Path) -> None:
    """Extrai o arquivo .zip no destino exibindo o progresso."""
    destino.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        infolist = zf.infolist()
        total = len(infolist)
        print(f"📦 Extraindo {total} arquivos para {destino}...")

        # Detectar se o zip possui uma pasta raiz única (ex: kit-web/)
        primeiro_segmento = infolist[0].filename.split("/")[0] if infolist else ""
        tem_prefixo_comum = bool(primeiro_segmento) and all(
            info.filename.startswith(primeiro_segmento + "/") or info.filename == primeiro_segmento
            for info in infolist
        )

        for i, info in enumerate(infolist, 1):
            # Extrair removendo o prefixo do kit se quisermos gravar direto na raiz do pendrive
            rel_path = info.filename
            if tem_prefixo_comum:
                if rel_path == primeiro_segmento:
                    continue
                rel_path = rel_path[len(primeiro_segmento) + 1 :]

            if not rel_path:
                continue

            target_path = destino / rel_path

            if info.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
            else:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(target_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)

                # Restaurar bits de permissão Unix (em sistemas POSIX)
                if sys.platform != "win32":
                    attr = info.external_attr >> 16
                    if attr & 0o111:
                        target_path.chmod(target_path.stat().st_mode | 0o111)

            if i % 250 == 0 or i == total:
                porcentagem = int((i / total) * 100)
                sys.stdout.write(f"\r  Progresso: [{porcentagem:3d}%] ({i}/{total} itens)")
                sys.stdout.flush()

        print("\n  ✅ Extração finalizada com sucesso!")


def ajustar_permissoes_pos_gravacao(destino: Path) -> None:
    """Garante permissões de execução para scripts no pendrive."""
    if sys.platform == "win32":
        return

    scripts_executaveis = [
        destino / "iniciar-linux.sh",
        destino / "laboratorio.desktop",
        destino / "diagnostico" / "linux.sh",
        destino / "diagnostico" / "verificar-sistema.sh",
    ]

    for script in scripts_executaveis:
        if script.exists():
            try:
                script.chmod(script.stat().st_mode | 0o755)
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Grava e prepara um Kit Universal de Programação diretamente no pendrive."
    )
    parser.add_argument(
        "--kit",
        choices=list(KITS_MAP.keys()),
        help="Perfil do Kit a ser gravado (web, poo-python ou poo-java).",
    )
    parser.add_argument(
        "--destino",
        help="Caminho do ponto de montagem ou letra do pendrive (ex: /Volumes/MEUPENDRIVE ou E:\\).",
    )
    parser.add_argument(
        "--pular-checksum",
        action="store_true",
        help="Ignora a conferência de hash SHA-256 antes da gravação.",
    )
    parser.add_argument(
        "-l", "--listar",
        action="store_true",
        help="Apenas lista as unidades removíveis/pendrives conectados e sai.",
    )

    args = parser.parse_args()

    if args.listar:
        vols = obter_volumes_removiveis()
        if not vols:
            print("Nenhuma unidade removível montada detectada.")
            return 0
        print(f"Unidades removíveis detectadas ({len(vols)}):")
        for idx, v in enumerate(vols, 1):
            print(f"  [{idx}] {v['nome']} ({v['caminho']}) — {v['livre_gb']} GB livres de {v['total_gb']} GB")
        return 0

    print("=" * 65)
    print("  🚀 Gravador de Pendrive do Laboratório Portátil Universal")
    print("=" * 65)
    print()

    # 1. Selecionar o Kit
    kit_key = args.kit
    if not kit_key:
        print("Escolha o kit a ser gravado no pendrive:")
        chaves = list(KITS_MAP.keys())
        for idx, k in enumerate(chaves, 1):
            zip_name, desc = KITS_MAP[k]
            status = "pronto" if (DIST_DIR / zip_name).exists() else "ausente em dist/"
            print(f"  [{idx}] {k.upper():<10} - {desc} ({status})")
        print()
        try:
            escolha = input("Digite o número desejado [1-3]: ").strip()
            num = int(escolha)
            kit_key = chaves[num - 1]
        except (ValueError, IndexError):
            print("❌ Opção inválida. Operação cancelada.")
            return 1

    zip_file, descricao = KITS_MAP[kit_key]
    zip_path = DIST_DIR / zip_file

    if not zip_path.exists():
        print(f"❌ O pacote {zip_path} não foi encontrado!")
        print("   Execute antes: python3 preparar.py zip --perfil", kit_key)
        return 1

    # 2. Selecionar o Destino
    destino_str = args.destino
    if not destino_str:
        print("\n🔍 Procurando unidades removíveis / pendrives conectados...")
        vols = obter_volumes_removiveis()
        if vols:
            print("Unidades detectadas:")
            for idx, v in enumerate(vols, 1):
                print(f"  [{idx}] {v['nome']} ({v['caminho']}) - {v['livre_gb']} GB livres de {v['total_gb']} GB")
            print("  [0] Digitar caminho manualmente")
            print()
            try:
                opc = input(f"Selecione a unidade [1-{len(vols)}] ou 0: ").strip()
                n = int(opc)
                if n == 0:
                    destino_str = input("Digite o caminho do pendrive: ").strip()
                elif 1 <= n <= len(vols):
                    destino_str = vols[n - 1]["caminho"]
                else:
                    print("❌ Opção inválida.")
                    return 1
            except ValueError:
                print("❌ Entrada inválida.")
                return 1
        else:
            print("ℹ️  Nenhuma unidade removível montada detectada automaticamente.")
            destino_str = input("Digite o caminho do pendrive (ex: /Volumes/MEUPENDRIVE ou E:\\): ").strip()

    if not destino_str:
        print("❌ Destino não informado.")
        return 1

    destino = Path(destino_str).resolve()
    if not destino.exists():
        print(f"❌ O destino especificado não existe: {destino}")
        return 1

    # 3. Validar Espaço em Disco
    try:
        usage = shutil.disk_usage(destino)
        livre_gb = usage.free / (1024**3)
        if livre_gb < 3.8:
            print(f"⚠️  Atenção: Apenas {livre_gb:.2f} GB livres no destino.")
            print("    O kit requer aproximadamente 3.8 GB. A extração pode falhar por falta de espaço.")
            confirma = input("Deseja continuar mesmo assim? [s/N]: ").strip().lower()
            if confirma != "s":
                print("Operação cancelada.")
                return 1
    except Exception as e:
        print(f"⚠️  Não foi possível verificar o espaço em disco: {e}")

    # 4. Validar Hash SHA-256
    if not args.pular-checksum:
        if not validar_integridade_pacote(zip_path):
            print("❌ Abortando gravação devido a arquivo corrompido.")
            return 1

    # 5. Confirmar Gravação
    print("\n" + "-" * 65)
    print(f"  Kit selecionado : {descricao}")
    print(f"  Arquivo origem  : {zip_path.name} ({round(zip_path.stat().st_size / (1024**2), 1)} MB)")
    print(f"  Destino         : {destino}")
    print("-" * 65)

    if not args.destino:
        confirma = input("\nConfirmar a gravação no pendrive? [S/n]: ").strip().lower()
        if confirma in ("n", "nao", "não"):
            print("Operação cancelada.")
            return 0

    # 6. Extrair
    print()
    extrair_com_progresso(zip_path, destino)
    ajustar_permissoes_pos_gravacao(destino)

    # 7. Resumo Final
    print("\n" + "=" * 65)
    print("  🎉 Pendrive preparado e pronto para uso nas aulas!")
    print("=" * 65)
    print("Instruções para o aluno:")
    print("  • No Windows : Dê duplo clique em 'Iniciar <Disciplina>.cmd'")
    print("  • No Linux   : Dê duplo clique em 'Iniciar <Disciplina>.desktop'")
    print("                 ou execute: sh iniciar-linux.sh")
    print("  • Banco      : O arquivo banco.db na pasta do projeto já está conectado.")
    print("=" * 65 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())

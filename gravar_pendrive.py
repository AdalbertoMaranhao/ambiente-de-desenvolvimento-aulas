#!/usr/bin/env python3
"""
gravar_pendrive.py — Utilitário de Gravação e Preparação de Pendrives de Alta Velocidade

Permite ao professor ou aluno gravar um Kit Universal de Programação
diretamente em um pendrive (formatado em exFAT ou FAT32), validando integridade,
espaço em disco e permissões de execução.

Destaques:
  • Barra de progresso visual em tempo real (compatível com UTF-8 e ASCII).
  • Detecção de motor nativo compilado em C (tar.exe / libarchive) para extração ultra-rápida.
  • Cópia direta de pasta SSD montada via robocopy /MT:8 (Windows) ou rsync (Unix).
  • Fallback Python otimizado com cache de diretórios e buffers I/O de 1 MB.
  • Detecção de sistema de arquivos com dicas de velocidade (exFAT vs FAT32).
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import zipfile

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / "dist"

KITS_MAP = {
    "web": ("kit-web.zip", "Desenvolvimento Web (PHP 8.5)"),
    "poo-java": ("kit-poo-java.zip", "POO com Java 25 (Adoptium)"),
}
# Suporte dinâmico para kit Python em branches que o possuam
if (DIST_DIR / "kit-poo-python.zip").exists() or (DIST_DIR / "kit-poo-python").exists():
    KITS_MAP["poo-python"] = ("kit-poo-python.zip", "POO com Python 3.13")


class ProgressBar:
    """Barra de progresso sem dependências externas, compatível com UTF-8 e ASCII."""

    def __init__(self, total: int, title: str = "Progresso", width: int = 25):
        self.total = max(1, total)
        self.current = 0
        self.title = title
        self.width = width
        self.lock = threading.Lock()
        self.is_tty = sys.stdout.isatty()
        self.unicode = True
        try:
            "█░".encode(sys.stdout.encoding or "utf-8")
        except (UnicodeEncodeError, LookupError):
            self.unicode = False

    def update(self, step: int = 1, detail: str = ""):
        with self.lock:
            self.current = min(self.total, self.current + step)
            self._render(detail)

    def set_current(self, current: int, detail: str = ""):
        with self.lock:
            self.current = min(self.total, current)
            self._render(detail)

    def _render(self, detail: str = ""):
        fraction = self.current / self.total
        percent = int(fraction * 100)
        filled = int(fraction * self.width)
        empty = self.width - filled

        fill_char = "█" if self.unicode else "="
        empty_char = "░" if self.unicode else "-"
        bar = fill_char * filled + empty_char * empty

        detail_str = f" - {detail}" if detail else ""
        line = f"\r{self.title} [{bar}] {self.current}/{self.total} ({percent:3d}%){detail_str}"

        try:
            term_cols = shutil.get_terminal_size((80, 24)).columns
            if len(line) > term_cols - 1:
                line = line[: term_cols - 4] + "..."
        except Exception:
            pass

        if self.is_tty:
            sys.stdout.write(line + "\033[K")
            sys.stdout.flush()
        else:
            if self.current == self.total or percent % 20 == 0:
                sys.stdout.write(f"{self.title} [{bar}] {self.current}/{self.total} ({percent}%){detail_str}\n")
                sys.stdout.flush()

    def finish(self, message: str = ""):
        with self.lock:
            self.current = self.total
            self._render(message)
            sys.stdout.write("\n")
            sys.stdout.flush()


def calcular_sha256(arquivo: Path, exibir_progresso: bool = False) -> str:
    """Calcula o SHA-256 de um arquivo em chunks de 1 MB exibindo barra de progresso."""
    hasher = hashlib.sha256()
    size = arquivo.stat().st_size
    total_mb = max(1, size // (1024 * 1024))
    bar = ProgressBar(total_mb, title=f"⏳ SHA-256 {arquivo.name[:20]}") if (exibir_progresso and size > 5 * 1024 * 1024) else None

    with open(arquivo, "rb") as f:
        mb_read = 0
        while chunk := f.read(1024 * 1024):
            hasher.update(chunk)
            mb_read += 1
            if bar:
                bar.set_current(mb_read, f"{mb_read} MB")

    if bar:
        bar.finish("Concluído!")
    return hasher.hexdigest()


def obter_sistema_arquivos(caminho: Path) -> str:
    """Identifica o sistema de arquivos da unidade montada (ex: FAT32, exFAT, NTFS)."""
    try:
        if sys.platform == "win32":
            import ctypes
            drive = str(caminho)[:3]
            fs_buffer = ctypes.create_unicode_buffer(256)
            res = ctypes.windll.kernel32.GetVolumeInformationW(
                ctypes.c_wchar_p(drive), None, 0, None, None, None, fs_buffer, ctypes.sizeof(fs_buffer)
            )
            return fs_buffer.value if res != 0 else ""
        elif sys.platform == "darwin":
            res = subprocess.run(["diskutil", "info", str(caminho)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
            for line in res.stdout.splitlines():
                if "File System Personality:" in line or "Type (Bundle):" in line:
                    return line.split(":", 1)[1].strip()
        elif sys.platform.startswith("linux"):
            res = subprocess.run(["df", "-T", str(caminho)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
            lines = res.stdout.strip().splitlines()
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 2:
                    return parts[1]
    except Exception:
        pass
    return ""


def eh_sistema_ideal(fs: str) -> bool:
    """Retorna True se o sistema de arquivos for exFAT (ideal para máxima velocidade e compatibilidade)."""
    return bool(fs) and "exfat" in fs.lower()


def obter_dispositivo_linux(caminho: Path) -> str:
    """Identifica o nó de dispositivo de bloco (/dev/sdXn) associado ao ponto de montagem no Linux."""
    try:
        res = subprocess.run(["findmnt", "-n", "-o", "SOURCE", str(caminho)], stdout=subprocess.PIPE, text=True, timeout=2)
        dev = res.stdout.strip()
        if dev.startswith("/dev/"):
            return dev
    except Exception:
        pass
    try:
        res = subprocess.run(["df", str(caminho)], stdout=subprocess.PIPE, text=True, timeout=2)
        lines = res.stdout.strip().splitlines()
        if len(lines) >= 2:
            dev = lines[1].split()[0]
            if dev.startswith("/dev/"):
                return dev
    except Exception:
        pass
    return ""


def confirmar_formatacao_segura(caminho: Path, fs: str) -> bool:
    """Exibe alerta de segurança e requer confirmação explícita por digitação para evitar perda de dados."""
    print("\n" + "!" * 65)
    print("  🚨 ATENÇÃO: A FORMATAÇÃO APAGARÁ PERMANENTEMENTE TODOS OS DADOS!")
    print(f"  Unidade alvo   : {caminho}")
    if fs:
        print(f"  Sistema atual  : {fs}")
    print("!" * 65)
    try:
        resp = input("Para confirmar e APAGAR todos os dados, digite FORMATAR (ou Enter para cancelar): ").strip()
        return resp.upper() == "FORMATAR"
    except (EOFError, KeyboardInterrupt):
        return False


def formatar_pendrive(caminho: Path, rotulo: str = "AULAS") -> Path | None:
    """
    Formata o pendrive no sistema de arquivos ideal (exFAT de 128 KB, com rótulo AULAS).
    Retorna o Path do novo ponto de montagem (ou caminho atual), ou None em caso de falha.
    """
    # 1. Windows
    if sys.platform == "win32":
        drive = str(caminho)[:2]
        print(f"⚡ Formatando {drive} em exFAT (cluster 128 KB, rótulo {rotulo})...")
        cmd = ["format", drive, "/FS:exFAT", "/Q", "/A:128K", f"/V:{rotulo}", "/Y"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            cmd_fallback = ["format", drive, "/FS:exFAT", "/Q", f"/V:{rotulo}", "/Y"]
            res = subprocess.run(cmd_fallback, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        if res.returncode == 0:
            print(f"  ✅ Unidade {drive} formatada com sucesso em exFAT!")
            return Path(f"{drive}\\")
        else:
            print(f"  ❌ Falha na formatação de {drive}:\n{res.stderr or res.stdout}")
            return None

    # 2. macOS
    elif sys.platform == "darwin":
        print(f"⚡ Formatando volume {caminho} em exFAT via diskutil (rótulo {rotulo})...")
        cmd = ["diskutil", "eraseVolume", "ExFAT", rotulo, str(caminho)]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0:
            novo_caminho = Path(f"/Volumes/{rotulo}")
            for _ in range(10):
                if novo_caminho.exists():
                    break
                time.sleep(0.5)
            print(f"  ✅ Volume formatado com sucesso em exFAT e montado em {novo_caminho}!")
            return novo_caminho if novo_caminho.exists() else caminho
        else:
            print(f"  ❌ Falha na formatação no macOS:\n{res.stderr or res.stdout}")
            return None

    # 3. Linux
    elif sys.platform.startswith("linux"):
        dev = obter_dispositivo_linux(caminho)
        if not dev:
            print("  ❌ Não foi possível identificar o dispositivo de bloco correspondente.")
            return None

        print(f"⚡ Formatando {dev} em exFAT (rótulo {rotulo})...")
        if shutil.which("udisksctl"):
            subprocess.run(["udisksctl", "unmount", "-b", dev], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            res = subprocess.run(
                ["udisksctl", "format", "-b", dev, "-t", "exfat", "--name", rotulo, "--no-user-interaction"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            if res.returncode == 0:
                res_mount = subprocess.run(
                    ["udisksctl", "mount", "-b", dev],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
                for part in res_mount.stdout.split():
                    if part.startswith("/media/") or part.startswith("/run/media/"):
                        p = Path(part)
                        if p.exists():
                            print(f"  ✅ Formatado com sucesso e montado em {p}!")
                            return p
                user = os.getenv("USER", "")
                candidatos = [Path("/media") / user / rotulo, Path("/run/media") / user / rotulo, Path("/media") / rotulo]
                for c in candidatos:
                    if c.exists():
                        print(f"  ✅ Formatado com sucesso e montado em {c}!")
                        return c

        if shutil.which("mkfs.exfat"):
            subprocess.run(["umount", dev], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            res = subprocess.run(["mkfs.exfat", "-s", "256", "-L", rotulo, dev], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode != 0:
                res = subprocess.run(["mkfs.exfat", "-L", rotulo, dev], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0:
                print(f"  ✅ Partição {dev} formatada em exFAT.")
                return caminho
        elif shutil.which("mkfs.vfat"):
            subprocess.run(["umount", dev], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            res = subprocess.run(["mkfs.vfat", "-F", "32", "-n", rotulo, dev], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0:
                print(f"  ✅ Partição {dev} formatada em FAT32.")
                return caminho

        print("  ❌ Ferramenta de formatação não disponível ou falhou.")
        return None

    return None


def calcular_pasta_destino(destino_base: Path, kit_key: str, subpasta: str | None = None, na_raiz: bool = False) -> Path:
    """Calcula o caminho final do kit no pendrive (subpasta dedicada por padrão, ou raiz se solicitado)."""
    if na_raiz:
        return destino_base
    nome_padrao = subpasta.strip() if (subpasta and subpasta.strip()) else f"kit-{kit_key}"
    if destino_base.name == nome_padrao:
        return destino_base
    return destino_base / nome_padrao


def criar_leia_me_raiz(pendrive_raiz: Path, kit_key: str) -> None:
    """Cria ou atualiza um arquivo LEIA-ME.txt informativo na raiz do pendrive."""
    try:
        leia_me = pendrive_raiz / "LEIA-ME.txt"
        kits_encontrados = set()
        if pendrive_raiz.exists() and pendrive_raiz.is_dir():
            for p in pendrive_raiz.iterdir():
                if p.is_dir() and p.name.startswith("kit-"):
                    kits_encontrados.add(p.name)
        kits_encontrados.add(f"kit-{kit_key}")

        linhas = [
            "=================================================================",
            "  LABORATÓRIO PORTÁTIL UNIVERSAL - KITS DE AULA",
            "=================================================================",
            "",
            "Os kits de programação estão instalados em suas respectivas pastas:",
        ]
        for k in sorted(kits_encontrados):
            linhas.append(f"  • {k}/")

        linhas.extend([
            "",
            "Como iniciar seus estudos:",
            "  1. Acesse a pasta do kit desejado (ex: kit-web ou kit-poo-java).",
            "  2. No Windows : dê dois cliques no arquivo 'iniciar-windows.cmd'",
            "  3. No Linux   : dê dois cliques em 'laboratorio.desktop' ou",
            "                  abra o terminal na pasta e execute: ./iniciar-linux.sh",
            "=================================================================",
        ])
        leia_me.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    except Exception:
        pass


def obter_volumes_removiveis() -> list[dict[str, str | int]]:
    """Detecta partições ou volumes removíveis/montados de acordo com o SO."""
    volumes = []

    if sys.platform == "darwin":
        vols_dir = Path("/Volumes")
        if vols_dir.exists():
            for p in sorted(vols_dir.iterdir()):
                if p.is_dir() and not p.is_symlink():
                    name = p.name
                    if name in ("Macintosh HD", "Recovery", "Time Machine Backups", "Preboot"):
                        continue
                    try:
                        usage = shutil.disk_usage(p)
                        fs = obter_sistema_arquivos(p)
                        volumes.append({
                            "caminho": str(p),
                            "nome": name,
                            "fs": fs,
                            "livre_gb": round(usage.free / (1024**3), 2),
                            "total_gb": round(usage.total / (1024**3), 2),
                        })
                    except Exception:
                        pass

    elif sys.platform.startswith("linux"):
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
                            fs = obter_sistema_arquivos(p)
                            volumes.append({
                                "caminho": str(p),
                                "nome": p.name,
                                "fs": fs,
                                "livre_gb": round(usage.free / (1024**3), 2),
                                "total_gb": round(usage.total / (1024**3), 2),
                            })
                        except Exception:
                            pass

    elif sys.platform == "win32":
        import ctypes
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for letter in "EFGHIJKLMNOPQRSTUVWXYZ":
            if bitmask & (1 << (ord(letter) - ord("A"))):
                path_str = f"{letter}:\\"
                try:
                    usage = shutil.disk_usage(path_str)
                    fs = obter_sistema_arquivos(Path(path_str))
                    volumes.append({
                        "caminho": path_str,
                        "nome": f"Unidade ({letter}:)",
                        "fs": fs,
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
    obtido = calcular_sha256(zip_path, exibir_progresso=True)

    if obtido.lower() == esperado.lower():
        print("  ✅ Verificação SHA-256 aprovada.")
        return True
    else:
        print(f"  ❌ Erro de hash SHA-256!\n     Esperado: {esperado}\n     Obtido:   {obtido}")
        return False


def testar_suporte_nativo_tar(zip_path: Path) -> bool:
    """Verifica se o comando tar do SO suporta leitura/descompactação do arquivo zip."""
    try:
        res = subprocess.run(
            ["tar", "-tf", str(zip_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5
        )
        return res.returncode == 0
    except Exception:
        return False


def extrair_nativo_tar(zip_path: Path, destino: Path) -> bool:
    """Extrai o arquivo .zip usando o tar nativo do SO com barra de progresso em tempo real."""
    try:
        total_files = 0
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                total_files = len(zf.infolist())
        except Exception:
            pass

        bar = ProgressBar(total_files if total_files > 0 else 100, title=f"⚡ {zip_path.name} (tar)")
        t0 = time.time()

        proc = subprocess.Popen(
            ["tar", "-xvf", str(zip_path), "--strip-components=1", "-C", str(destino)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )

        count = 0
        if proc.stderr:
            for line in proc.stderr:
                count += 1
                parts = line.strip().split()
                fname = parts[-1].split("/")[-1] if parts else ""
                if count % 15 == 0 or (total_files > 0 and count == total_files):
                    bar.set_current(min(total_files or count, count), fname[:25])
            proc.stderr.close()

        proc.wait()
        if proc.returncode == 0:
            elapsed = time.time() - t0
            bar.finish(f"Concluído em {elapsed:.1f}s!")
            return True
    except Exception as e:
        print(f"⚠️  Falha ao executar extração nativa ({e}). Alternando para extrator otimizado em Python...")
    return False


def copiar_pasta_direta(origem: Path, destino: Path) -> bool:
    """Copia uma pasta já montada diretamente para o pendrive em alta velocidade."""
    print(f"🚀 Pasta montada detectada ({origem.name}). Iniciando transferência direta...")
    destino.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    # No Windows, utilizar o robocopy multi-thread (/MT:8)
    if sys.platform == "win32":
        try:
            print("⚡ Executando cópia acelerada via robocopy (8 threads paralelas)...")
            cmd = ["robocopy", str(origem), str(destino), "/E", "/MT:8", "/R:1", "/W:1", "/NFL", "/NDL", "/NP"]
            res = subprocess.run(cmd)
            if res.returncode < 8:
                elapsed = time.time() - t0
                print(f"  ✅ Cópia direta finalizada em {elapsed:.1f}s!")
                return True
        except Exception:
            pass

    # No Linux/macOS, utilizar rsync com barra de progresso
    if sys.platform != "win32":
        if shutil.which("rsync"):
            try:
                print("⚡ Executando cópia acelerada via rsync...")
                cmd = ["rsync", "-a", f"{origem}/", f"{destino}/"]
                res = subprocess.run(cmd)
                if res.returncode == 0:
                    elapsed = time.time() - t0
                    print(f"  ✅ Cópia direta finalizada em {elapsed:.1f}s!")
                    return True
            except Exception:
                pass

    # Fallback em Python com barra de progresso e buffer de 1 MB
    return copiar_pasta_python(origem, destino)


def copiar_pasta_python(origem: Path, destino: Path) -> bool:
    """Cópia recursiva em Python com cache de diretórios, buffers de 1 MB e barra de progresso."""
    dirs_criados = set([destino])
    total_files = sum(1 for _ in origem.rglob("*") if _.is_file())
    bar = ProgressBar(total_files, title=f"🚀 {origem.name}")
    count = 0

    for root, _, files in os.walk(origem):
        rel_root = Path(root).relative_to(origem)
        target_dir = destino / rel_root

        if target_dir not in dirs_criados:
            target_dir.mkdir(parents=True, exist_ok=True)
            dirs_criados.add(target_dir)

        for f in files:
            src_f = Path(root) / f
            dst_f = target_dir / f
            with open(src_f, "rb") as s, open(dst_f, "wb") as d:
                while chunk := s.read(1024 * 1024):
                    d.write(chunk)
            count += 1
            if count % 15 == 0 or count == total_files:
                bar.set_current(count, f[:25])

    bar.finish("Concluído!")
    return True


def extrair_com_progresso(zip_path: Path, destino: Path, forcar_python: bool = False) -> None:
    """Extrai o arquivo .zip no destino utilizando o melhor motor disponível com barra de progresso."""
    destino.mkdir(parents=True, exist_ok=True)

    # 1. Tentar motor nativo tar (se disponível e não forçado Python)
    if not forcar_python and testar_suporte_nativo_tar(zip_path):
        if extrair_nativo_tar(zip_path, destino):
            return

    # 2. Motor Python Otimizado (Cache de diretórios + buffer de 1 MB + ProgressBar)
    with zipfile.ZipFile(zip_path, "r") as zf:
        infolist = zf.infolist()
        total = len(infolist)
        bar = ProgressBar(total, title=f"📦 {zip_path.name}")

        primeiro_segmento = infolist[0].filename.split("/")[0] if infolist else ""
        tem_prefixo_comum = bool(primeiro_segmento) and all(
            info.filename.startswith(primeiro_segmento + "/") or info.filename == primeiro_segmento
            for info in infolist
        )

        dirs_criados = set([destino])
        CHUNK = 1024 * 1024  # Buffer de 1 MB

        for i, info in enumerate(infolist, 1):
            rel_path = info.filename
            if tem_prefixo_comum:
                if rel_path == primeiro_segmento:
                    continue
                rel_path = rel_path[len(primeiro_segmento) + 1 :]

            if not rel_path:
                continue

            target_path = destino / rel_path

            if info.is_dir():
                if target_path not in dirs_criados:
                    target_path.mkdir(parents=True, exist_ok=True)
                    dirs_criados.add(target_path)
            else:
                parent = target_path.parent
                if parent not in dirs_criados:
                    parent.mkdir(parents=True, exist_ok=True)
                    dirs_criados.add(parent)

                with zf.open(info) as src, open(target_path, "wb") as dst:
                    while chunk := src.read(CHUNK):
                        dst.write(chunk)

                if sys.platform != "win32":
                    attr = info.external_attr >> 16
                    if attr & 0o111:
                        try:
                            target_path.chmod(target_path.stat().st_mode | 0o111)
                        except OSError:
                            pass

            if i % 15 == 0 or i == total:
                fname = rel_path.split("/")[-1]
                bar.set_current(i, fname[:25])

        bar.finish("Concluído!")


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
        description="Grava e prepara um Kit Universal de Programação diretamente no pendrive em alta velocidade."
    )
    parser.add_argument(
        "--kit",
        choices=list(KITS_MAP.keys()),
        help="Perfil do Kit a ser gravado (web ou poo-java).",
    )
    parser.add_argument(
        "--destino",
        help="Caminho do ponto de montagem ou letra do pendrive (ex: /Volumes/MEUPENDRIVE ou E:\\).",
    )
    parser.add_argument(
        "--motor",
        choices=["auto", "nativo", "python"],
        default="auto",
        help="Motor de extração (auto = detecta o mais rápido; nativo = tar; python = interno).",
    )
    parser.add_argument(
        "--direto",
        action="store_true",
        help="Se a pasta dist/kit-* estiver montada, copia direto sem descompactar o zip.",
    )
    parser.add_argument(
        "--pular-checksum",
        action="store_true",
        help="Ignora a conferência de hash SHA-256 antes da gravação.",
    )
    parser.add_argument(
        "--pasta",
        help="Nome da subpasta no pendrive onde o kit será gravado (padrão: kit-<disciplina>).",
    )
    parser.add_argument(
        "--raiz",
        action="store_true",
        help="Grava diretamente na raiz do pendrive (sem criar subpasta kit-<disciplina>).",
    )
    parser.add_argument(
        "--formatar",
        action="store_true",
        help="Formata a unidade no sistema ideal (exFAT de 128 KB, rótulo AULAS) antes de gravar.",
    )
    parser.add_argument(
        "--confirmar-formatacao",
        action="store_true",
        help="Confirma a formatação sem solicitar digitação no terminal (para automação).",
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
            fs_info = f" [{v['fs']}]" if v.get("fs") else ""
            print(f"  [{idx}] {v['nome']} ({v['caminho']}){fs_info} — {v['livre_gb']} GB livres de {v['total_gb']} GB")
        return 0

    print("=" * 65)
    print("  🚀 Gravador de Pendrive do Laboratório Portátil Universal")
    print("     (Modo de Alta Performance com Desduplicação de Arquivos)")
    print("=" * 65)
    print()

    # 1. Selecionar o Kit
    kit_key = args.kit
    if not kit_key:
        print("Escolha o kit a ser gravado no pendrive:")
        chaves = list(KITS_MAP.keys())
        for idx, k in enumerate(chaves, 1):
            zip_name, desc = KITS_MAP[k]
            pasta_montada = DIST_DIR / f"kit-{k}"
            status = "pronto (.zip)" if (DIST_DIR / zip_name).exists() else "ausente"
            if pasta_montada.exists():
                status += " + pasta SSD montada"
            print(f"  [{idx}] {k.upper():<10} - {desc} ({status})")
        print()
        try:
            escolha = input(f"Digite o número desejado [1-{len(chaves)}]: ").strip()
            num = int(escolha)
            kit_key = chaves[num - 1]
        except (ValueError, IndexError):
            print("❌ Opção inválida. Operação cancelada.")
            return 1

    zip_file, descricao = KITS_MAP[kit_key]
    zip_path = DIST_DIR / zip_file
    pasta_montada = DIST_DIR / f"kit-{kit_key}"

    if not zip_path.exists() and not pasta_montada.exists():
        print(f"❌ O pacote {zip_path.name} não foi encontrado!")
        print("   Execute antes: python3 preparar.py tudo --perfil", kit_key)
        return 1

    # 2. Selecionar o Destino
    destino_str = args.destino
    selected_fs = ""
    if not destino_str:
        print("\n🔍 Procurando unidades removíveis / pendrives conectados...")
        vols = obter_volumes_removiveis()
        if vols:
            print("Unidades detectadas:")
            for idx, v in enumerate(vols, 1):
                fs_label = f" (Sistema: {v['fs']})" if v.get("fs") else ""
                print(f"  [{idx}] {v['nome']} ({v['caminho']}){fs_label} - {v['livre_gb']} GB livres de {v['total_gb']} GB")
            print("  [0] Digitar caminho manualmente")
            print()
            try:
                opc = input(f"Selecione a unidade [1-{len(vols)}] ou 0: ").strip()
                n = int(opc)
                if n == 0:
                    destino_str = input("Digite o caminho do pendrive: ").strip()
                elif 1 <= n <= len(vols):
                    destino_str = vols[n - 1]["caminho"]
                    selected_fs = vols[n - 1].get("fs", "")
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

    if not selected_fs:
        selected_fs = obter_sistema_arquivos(destino)

    # 3. Verificar Formatação (se sistema não for o ideal ou se --formatar foi solicitado)
    deseja_formatar = args.formatar
    if not deseja_formatar and not eh_sistema_ideal(selected_fs):
        print("\n" + "-" * 65)
        print(f"💡 Sistema de arquivos detectado: {selected_fs or 'Desconhecido / Não otimizado'}")
        print("   Recomendação de Desempenho e Compatibilidade:")
        print("   • O sistema ideal para pendrives de aula é exFAT (cluster de 128 KB).")
        print("   • Ele é compatível nativamente com Windows, macOS e Linux.")
        print("   • Evita lentidão com milhares de arquivos pequenos e o limite de 4 GB do FAT32.")
        print("-" * 65)
        try:
            perg = input(f"Deseja formatar a unidade ({destino}) em exFAT de alta performance agora? [s/N]: ").strip().lower()
            if perg in ("s", "sim", "y", "yes"):
                deseja_formatar = True
        except (EOFError, KeyboardInterrupt):
            deseja_formatar = False

    if deseja_formatar:
        confirmado = args.confirmar_formatacao or confirmar_formatacao_segura(destino, selected_fs)
        if confirmado:
            novo_destino = formatar_pendrive(destino, rotulo="AULAS")
            if novo_destino and novo_destino.exists():
                destino = novo_destino
                selected_fs = "exFAT"
            else:
                print("⚠️  Não foi possível formatar automaticamente. Prosseguindo no estado atual...")
        else:
            print("ℹ️  Formatação cancelada pelo usuário. Prosseguindo com os dados existentes...")

    # 4. Calcular Subpasta do Kit no Pendrive
    kit_destino = calcular_pasta_destino(destino, kit_key, subpasta=args.pasta, na_raiz=args.raiz)

    # 5. Validar Espaço em Disco
    try:
        usage = shutil.disk_usage(destino)
        livre_gb = usage.free / (1024**3)
        if livre_gb < 3.0:
            print(f"⚠️  Atenção: Apenas {livre_gb:.2f} GB livres no destino.")
            print("    O kit requer aproximadamente 3.0 GB. A extração pode falhar por falta de espaço.")
            confirma = input("Deseja continuar mesmo assim? [s/N]: ").strip().lower()
            if confirma != "s":
                print("Operação cancelada.")
                return 1
    except Exception as e:
        print(f"⚠️  Não foi possível verificar o espaço em disco: {e}")

    # 6. Decidir se faz cópia direta de pasta ou descompactação
    usar_copia_direta = (args.direto or (pasta_montada.exists() and not zip_path.exists()))

    # 7. Validar Hash SHA-256 (se gravando a partir do zip)
    if not usar_copia_direta and not args.pular_checksum and zip_path.exists():
        if not validar_integridade_pacote(zip_path):
            print("❌ Abortando gravação devido a arquivo corrompido.")
            return 1

    # 8. Confirmar Gravação
    print("\n" + "-" * 65)
    print(f"  Kit selecionado : {descricao}")
    if usar_copia_direta:
        print(f"  Origem          : Pasta montada no SSD ({pasta_montada.name})")
    else:
        print(f"  Arquivo origem  : {zip_path.name} ({round(zip_path.stat().st_size / (1024**2), 1)} MB)")
    print(f"  Pendrive        : {destino}")
    print(f"  Pasta do kit    : {kit_destino}")
    if selected_fs:
        print(f"  Sistema arquivos: {selected_fs}")
    print("-" * 65)

    if not args.destino:
        confirma = input("\nConfirmar a gravação no pendrive? [S/n]: ").strip().lower()
        if confirma in ("n", "nao", "não"):
            print("Operação cancelada.")
            return 0

    # 9. Executar Transferência
    print()
    kit_destino.mkdir(parents=True, exist_ok=True)
    if usar_copia_direta and pasta_montada.exists():
        copiar_pasta_direta(pasta_montada, kit_destino)
    else:
        forcar_py = (args.motor == "python")
        extrair_com_progresso(zip_path, kit_destino, forcar_python=forcar_py)

    ajustar_permissoes_pos_gravacao(kit_destino)

    if kit_destino != destino:
        criar_leia_me_raiz(destino, kit_key)

    # 10. Resumo Final
    print("\n" + "=" * 65)
    print("  🎉 Pendrive preparado e pronto para uso nas aulas!")
    print("=" * 65)
    print(f"Local do kit gravado: {kit_destino}")
    print("Instruções para o aluno:")
    if kit_destino != destino:
        print(f"  1. Abra a pasta: {kit_destino.name}")
        print("  2. No Windows : Dê duplo clique em 'iniciar-windows.cmd'")
        print("  3. No Linux   : Dê duplo clique em 'laboratorio.desktop'")
        print("                  ou execute no terminal: ./iniciar-linux.sh")
    else:
        print("  • No Windows : Dê duplo clique em 'iniciar-windows.cmd'")
        print("  • No Linux   : Dê duplo clique em 'laboratorio.desktop'")
        print("                 ou execute no terminal: ./iniciar-linux.sh")
    print("=" * 65 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())

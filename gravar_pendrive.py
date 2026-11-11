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

    if selected_fs and ("fat" in selected_fs.lower() or "ms-dos" in selected_fs.lower()):
        print("\n💡 Dica de Desempenho:")
        print(f"   Seu pendrive está em {selected_fs}. Pendrives formatados em exFAT (cluster de 128 KB)")
        print("   podem transferir arquivos até 3x mais rápido em relação ao FAT32 tradicional.")

    # 3. Validar Espaço em Disco
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

    # 4. Decidir se faz cópia direta de pasta ou descompactação
    usar_copia_direta = (args.direto or (pasta_montada.exists() and not zip_path.exists()))

    # 5. Validar Hash SHA-256 (se gravando a partir do zip)
    if not usar_copia_direta and not args.pular_checksum and zip_path.exists():
        if not validar_integridade_pacote(zip_path):
            print("❌ Abortando gravação devido a arquivo corrompido.")
            return 1

    # 6. Confirmar Gravação
    print("\n" + "-" * 65)
    print(f"  Kit selecionado : {descricao}")
    if usar_copia_direta:
        print(f"  Origem          : Pasta montada no SSD ({pasta_montada.name})")
    else:
        print(f"  Arquivo origem  : {zip_path.name} ({round(zip_path.stat().st_size / (1024**2), 1)} MB)")
    print(f"  Destino         : {destino}")
    print("-" * 65)

    if not args.destino:
        confirma = input("\nConfirmar a gravação no pendrive? [S/n]: ").strip().lower()
        if confirma in ("n", "nao", "não"):
            print("Operação cancelada.")
            return 0

    # 7. Executar Transferência
    print()
    if usar_copia_direta and pasta_montada.exists():
        copiar_pasta_direta(pasta_montada, destino)
    else:
        forcar_py = (args.motor == "python")
        extrair_com_progresso(zip_path, destino, forcar_python=forcar_py)

    ajustar_permissoes_pos_gravacao(destino)

    # 8. Resumo Final
    print("\n" + "=" * 65)
    print("  🎉 Pendrive preparado e pronto para uso nas aulas!")
    print("=" * 65)
    print("Instruções para o aluno:")
    print("  • No Windows : Dê duplo clique em 'Iniciar <Disciplina>.cmd'")
    print("  • No Linux   : Dê duplo clique em 'Iniciar <Disciplina>.desktop'")
    print("                 ou execute: sh iniciar-linux.sh")
    print("=" * 65 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())

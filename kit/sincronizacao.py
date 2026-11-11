"""
Módulo de Sincronização Inteligente de Projetos (3-way sync).
Sincroniza os projetos entre o armazenamento local (SSD) e o pendrive do aluno,
com detecção de conflitos, isolamento seguro, preservação atômica do Git (.git)
e tolerância a falhas em laboratórios com múltiplos computadores.
"""

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
from typing import Dict, List, Optional, Set, Tuple

# Padrões e pastas ignoradas na sincronização de projetos (arquivos voláteis / de compilação)
IGNORAR_DIR_NOMES = {
    "node_modules",
    "target",
    "bin",
    "build",
    "dist",
    ".cache",
    ".idea",
    ".vscode-test",
    "__pycache__",
}

IGNORAR_ARQUIVO_NOMES = {
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    "sync.lock",
}

IGNORAR_EXTENSOES = {
    ".tmp",
    ".part",
    ".crdownload",
}


@dataclass
class RelatorioSincronizacao:
    copiados_para_local: List[str] = field(default_factory=list)
    copiados_para_pendrive: List[str] = field(default_factory=list)
    deletados_no_local: List[str] = field(default_factory=list)
    deletados_no_pendrive: List[str] = field(default_factory=list)
    conflitos: List[str] = field(default_factory=list)
    erros: List[str] = field(default_factory=list)
    sucesso: bool = True
    duracao_segundos: float = 0.0

    def resumo(self) -> str:
        linhas = []
        linhas.append(f"⏱️  Tempo de sincronização: {self.duracao_segundos:.2f}s")
        if self.copiados_para_local:
            linhas.append(f"⬇️  Atualizados no computador (SSD): {len(self.copiados_para_local)} arquivo(s)")
        if self.copiados_para_pendrive:
            linhas.append(f"⬆️  Salvos no pendrive: {len(self.copiados_para_pendrive)} arquivo(s)")
        if self.deletados_no_local:
            linhas.append(f"🗑️  Removidos do computador: {len(self.deletados_no_local)} arquivo(s)")
        if self.deletados_no_pendrive:
            linhas.append(f"🗑️  Removidos do pendrive: {len(self.deletados_no_pendrive)} arquivo(s)")
        if self.conflitos:
            linhas.append(f"⚠️  Conflitos isolados com segurança: {len(self.conflitos)} arquivo(s)")
        if self.erros:
            linhas.append(f"❌ Erros durante sincronização: {len(self.erros)}")
        if not (self.copiados_para_local or self.copiados_para_pendrive or self.deletados_no_local or self.deletados_no_pendrive or self.conflitos):
            linhas.append("✅ Tudo atualizado! Nenhum arquivo precisou ser transferido.")
        return "\n".join(linhas)


def calcular_sha256(caminho: Path, bloco: int = 65536) -> str:
    """Calcula o hash SHA-256 de um arquivo em blocos."""
    h = hashlib.sha256()
    try:
        with caminho.open("rb") as f:
            while chunk := f.read(bloco):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return ""


def eh_arquivo_ignorado(rel_path: Path) -> bool:
    """Verifica se o arquivo ou parte do seu caminho deve ser ignorado na sincronização."""
    partes = rel_path.parts
    # Ignora arquivos de trava temporários do git, mas PRESERVA o .git
    if "index.lock" in partes:
        return True

    for p in partes[:-1]:
        if p in IGNORAR_DIR_NOMES:
            return True

    nome = rel_path.name
    if nome in IGNORAR_ARQUIVO_NOMES or nome.startswith(".sync_"):
        return True

    for ext in IGNORAR_EXTENSOES:
        if nome.endswith(ext):
            return True

    return False


def escanear_diretorio(diretorio: Path) -> Dict[str, dict]:
    """
    Escaneia recursivamente o diretório retornando mapa de caminho relativo normalizado -> metadados.
    Preserva completamente repositórios Git (.git), exceto index.lock.
    """
    mapa = {}
    if not diretorio.exists():
        return mapa

    for raiz, dirs, arquivos in os.walk(diretorio):
        # Evita descer em diretórios ignorados
        dirs[:] = [d for d in dirs if d not in IGNORAR_DIR_NOMES]

        for arq in arquivos:
            arq_path = Path(raiz) / arq
            try:
                rel = arq_path.relative_to(diretorio)
            except ValueError:
                continue

            if eh_arquivo_ignorado(rel):
                continue

            rel_str = rel.as_posix()
            try:
                st = arq_path.stat()
                mapa[rel_str] = {
                    "size": st.st_size,
                    "mtime": st.st_mtime,
                    "hash": None,  # Calculado sob demanda (lazy) para velocidade
                    "_path": arq_path
                }
            except OSError:
                continue

    return mapa


def obter_hash_com_cache(item: dict) -> str:
    """Obtém ou calcula o hash SHA-256 de um item escaneado."""
    if item.get("hash") is None:
        caminho = item.get("_path")
        if caminho and isinstance(caminho, Path) and caminho.exists():
            item["hash"] = calcular_sha256(caminho)
        else:
            item["hash"] = ""
    return item["hash"]


def copia_atomica(origem: Path, destino: Path):
    """
    Copia um arquivo com gravação atômica: cria <destino>.part no mesmo diretório
    e renomeia para o nome final, garantindo integridade contra interrupções.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    part_file = destino.parent / f".{destino.name}.part_{os.getpid()}_{int(time.time()*1000)}"
    try:
        shutil.copy2(origem, part_file)
        if sys.platform == "win32" and destino.exists():
            destino.unlink(missing_ok=True)
        part_file.replace(destino)
    except Exception:
        part_file.unlink(missing_ok=True)
        raise


class LockSincronizacao:
    """Gerenciador de lock de arquivo para evitar sincronizações simultâneas."""
    def __init__(self, lock_file: Path):
        self.lock_file = lock_file
        self.acquired = False

    def __enter__(self):
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        if self.lock_file.exists():
            try:
                data = json.loads(self.lock_file.read_text(encoding="utf-8"))
                pid = data.get("pid")
                tempo = data.get("time", 0)
                # Se o lock tem mais de 10 minutos (600s), considera obsoleto (stale lock)
                if time.time() - tempo < 600:
                    if pid and self._processo_esta_ativo(pid):
                        raise RuntimeError(f"Outro processo de sincronização está ativo (PID {pid}).")
            except (json.JSONDecodeError, OSError):
                pass

        try:
            lock_data = {
                "pid": os.getpid(),
                "time": time.time(),
                "data": datetime.now().isoformat()
            }
            self.lock_file.write_text(json.dumps(lock_data, indent=2), encoding="utf-8")
            self.acquired = True
        except OSError as e:
            raise RuntimeError(f"Não foi possível criar o arquivo de trava ({self.lock_file}): {e}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.acquired:
            self.lock_file.unlink(missing_ok=True)

    @staticmethod
    def _processo_esta_ativo(pid: int) -> bool:
        if sys.platform == "win32":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                process = kernel32.OpenProcess(0x1000, False, pid)
                if process:
                    kernel32.CloseHandle(process)
                    return True
                return False
            except Exception:
                return True
        else:
            try:
                os.kill(pid, 0)
                return True
            except OSError:
                return False


def sincronizar_projetos(
    pendrive_projetos: Path,
    local_projetos: Path,
    sync_dir: Path,
    disciplina: Optional[str] = None
) -> RelatorioSincronizacao:
    """
    Executa sincronização inteligente de 3 vias (Pendrive <-> Local SSD <-> Snapshots).
    Garante restauração segura em novos computadores sem perda de dados no pendrive.
    """
    relatorio = RelatorioSincronizacao()
    inicio = time.time()

    lock_file = sync_dir / "sync.lock"
    try:
        with LockSincronizacao(lock_file):
            _executar_sincronizacao(
                pendrive_projetos,
                local_projetos,
                sync_dir,
                disciplina,
                relatorio
            )
    except Exception as e:
        relatorio.sucesso = False
        relatorio.erros.append(str(e))

    relatorio.duracao_segundos = time.time() - inicio
    return relatorio


def _executar_sincronizacao(
    pendrive_projetos: Path,
    local_projetos: Path,
    sync_dir: Path,
    disciplina: Optional[str],
    relatorio: RelatorioSincronizacao
):
    pen_base = pendrive_projetos / disciplina if disciplina else pendrive_projetos
    loc_base = local_projetos / disciplina if disciplina else local_projetos

    pen_base.mkdir(parents=True, exist_ok=True)
    loc_base.mkdir(parents=True, exist_ok=True)

    # Identifica snapshots no pendrive e na máquina local
    snap_nome = f"snapshot{'_' + disciplina if disciplina else ''}.json"
    pen_snap_file = sync_dir / snap_nome

    local_estado_dir = local_projetos.parent / "estado"
    if local_estado_dir.exists():
        loc_snap_file = local_estado_dir / snap_nome
    else:
        loc_snap_file = loc_base / f".sync_{snap_nome}"

    pen_snap = {}
    if pen_snap_file.exists():
        try:
            pen_snap = json.loads(pen_snap_file.read_text(encoding="utf-8"))
        except Exception:
            pen_snap = {}

    loc_snap = {}
    loc_eh_novo = True
    if loc_snap_file.exists():
        try:
            loc_snap = json.loads(loc_snap_file.read_text(encoding="utf-8"))
            loc_eh_novo = False
        except Exception:
            loc_snap = {}

    pen_files = escanear_diretorio(pen_base)
    loc_files = escanear_diretorio(loc_base)

    if not loc_files:
        loc_eh_novo = True

    todos_caminhos: Set[str] = set(pen_snap.keys()) | set(loc_snap.keys()) | set(pen_files.keys()) | set(loc_files.keys())

    novo_snapshot: Dict[str, dict] = {}
    conflitos_dir = sync_dir / "conflitos" / datetime.now().strftime("%Y%m%d-%H%M%S")

    for rel_str in sorted(todos_caminhos):
        no_pen = rel_str in pen_files
        no_loc = rel_str in loc_files
        pen_item = pen_files.get(rel_str)
        loc_item = loc_files.get(rel_str)
        base_snap = pen_snap.get(rel_str) or loc_snap.get(rel_str)

        # Caso 1: Arquivo existe em ambos os lados
        if no_pen and no_loc:
            tamanhos_iguais = (pen_item["size"] == loc_item["size"])
            mesmo_mtime = abs(pen_item["mtime"] - loc_item["mtime"]) < 1.0

            if tamanhos_iguais and mesmo_mtime:
                novo_snapshot[rel_str] = {
                    "size": pen_item["size"],
                    "mtime": loc_item["mtime"],
                    "hash": base_snap.get("hash") if base_snap else obter_hash_com_cache(loc_item)
                }
                continue

            hash_pen = obter_hash_com_cache(pen_item)
            hash_loc = obter_hash_com_cache(loc_item)

            if hash_pen == hash_loc:
                novo_snapshot[rel_str] = {
                    "size": loc_item["size"],
                    "mtime": loc_item["mtime"],
                    "hash": hash_loc
                }
                continue

            hash_base = base_snap.get("hash") if base_snap else None

            if hash_base:
                if hash_pen == hash_base and hash_loc != hash_base:
                    # Modificado somente no local -> salvar no pendrive
                    try:
                        copia_atomica(loc_item["_path"], pen_item["_path"])
                        relatorio.copiados_para_pendrive.append(rel_str)
                        novo_snapshot[rel_str] = {
                            "size": loc_item["size"],
                            "mtime": loc_item["mtime"],
                            "hash": hash_loc
                        }
                    except Exception as e:
                        relatorio.erros.append(f"Erro ao salvar {rel_str} no pendrive: {e}")
                    continue
                elif hash_loc == hash_base and hash_pen != hash_base:
                    # Modificado somente no pendrive -> atualizar no local
                    try:
                        copia_atomica(pen_item["_path"], loc_item["_path"])
                        relatorio.copiados_para_local.append(rel_str)
                        novo_snapshot[rel_str] = {
                            "size": pen_item["size"],
                            "mtime": pen_item["mtime"],
                            "hash": hash_pen
                        }
                    except Exception as e:
                        relatorio.erros.append(f"Erro ao atualizar {rel_str} no local: {e}")
                    continue

            # Conflito real entre as duas pontas
            conflitos_dir.mkdir(parents=True, exist_ok=True)
            iso_pen = conflitos_dir / f"{Path(rel_str).name}.pendrive"
            iso_loc = conflitos_dir / f"{Path(rel_str).name}.local"
            try:
                shutil.copy2(pen_item["_path"], iso_pen)
                shutil.copy2(loc_item["_path"], iso_loc)
                info_conflito = {
                    "arquivo": rel_str,
                    "data": datetime.now().isoformat(),
                    "hash_pendrive": hash_pen,
                    "hash_local": hash_loc,
                    "resolucao_adotada": "Arquivo local mantido ativo; versão do pendrive isolada."
                }
                (conflitos_dir / f"{Path(rel_str).name}.conflito.json").write_text(
                    json.dumps(info_conflito, indent=2, ensure_ascii=False),
                    encoding="utf-8"
                )
                relatorio.conflitos.append(rel_str)
                copia_atomica(loc_item["_path"], pen_item["_path"])
                novo_snapshot[rel_str] = {
                    "size": loc_item["size"],
                    "mtime": loc_item["mtime"],
                    "hash": hash_loc
                }
            except Exception as e:
                relatorio.erros.append(f"Erro ao isolar conflito de {rel_str}: {e}")

        # Caso 2: Existe no pendrive, mas NÃO no local
        elif no_pen and not no_loc:
            hash_pen = obter_hash_com_cache(pen_item)

            if not loc_eh_novo and rel_str in loc_snap:
                # O arquivo existia neste computador local e foi intencionalmente deletado aqui
                snap_local_item = loc_snap[rel_str]
                if snap_local_item.get("hash") == hash_pen:
                    # Deletado intencionalmente no computador -> remover do pendrive
                    try:
                        pen_item["_path"].unlink(missing_ok=True)
                        relatorio.deletados_no_pendrive.append(rel_str)
                    except Exception as e:
                        relatorio.erros.append(f"Erro ao remover {rel_str} do pendrive: {e}")
                else:
                    # Pendrive foi modificado enquanto local apagou -> restaura do pendrive
                    dest = loc_base / rel_str
                    try:
                        copia_atomica(pen_item["_path"], dest)
                        relatorio.copiados_para_local.append(rel_str)
                        novo_snapshot[rel_str] = {
                            "size": pen_item["size"],
                            "mtime": pen_item["mtime"],
                            "hash": hash_pen
                        }
                    except Exception as e:
                        relatorio.erros.append(f"Erro ao restaurar {rel_str} do pendrive: {e}")
            else:
                # Novo computador ou arquivo novo trazido de outra máquina -> copia do pendrive para local!
                dest = loc_base / rel_str
                try:
                    copia_atomica(pen_item["_path"], dest)
                    relatorio.copiados_para_local.append(rel_str)
                    novo_snapshot[rel_str] = {
                        "size": pen_item["size"],
                        "mtime": pen_item["mtime"],
                        "hash": hash_pen
                    }
                except Exception as e:
                    relatorio.erros.append(f"Erro ao copiar {rel_str} para local: {e}")

        # Caso 3: Existe no local, mas NÃO no pendrive
        elif no_loc and not no_pen:
            hash_loc = obter_hash_com_cache(loc_item)

            if rel_str in pen_snap:
                # O arquivo existia no pendrive e foi deletado nele (ou em outro PC)
                snap_pen_item = pen_snap[rel_str]
                if snap_pen_item.get("hash") == hash_loc:
                    # Não foi alterado localmente -> remover do local
                    try:
                        loc_item["_path"].unlink(missing_ok=True)
                        relatorio.deletados_no_local.append(rel_str)
                    except Exception as e:
                        relatorio.erros.append(f"Erro ao remover {rel_str} do local: {e}")
                else:
                    # Foi alterado localmente enquanto apagado no pendrive -> ressuscita no pendrive
                    dest = pen_base / rel_str
                    try:
                        copia_atomica(loc_item["_path"], dest)
                        relatorio.copiados_para_pendrive.append(rel_str)
                        novo_snapshot[rel_str] = {
                            "size": loc_item["size"],
                            "mtime": loc_item["mtime"],
                            "hash": hash_loc
                        }
                    except Exception as e:
                        relatorio.erros.append(f"Erro ao recriar {rel_str} no pendrive: {e}")
            else:
                # Arquivo novo criado no local -> copia para pendrive
                dest = pen_base / rel_str
                try:
                    copia_atomica(loc_item["_path"], dest)
                    relatorio.copiados_para_pendrive.append(rel_str)
                    novo_snapshot[rel_str] = {
                        "size": loc_item["size"],
                        "mtime": loc_item["mtime"],
                        "hash": hash_loc
                    }
                except Exception as e:
                    relatorio.erros.append(f"Erro ao salvar {rel_str} no pendrive: {e}")

        # Caso 4: Foi deletado em ambos
        else:
            pass

    # Limpeza de pastas vazias residuais
    _limpar_pastas_vazias(pen_base)
    _limpar_pastas_vazias(loc_base)

    # Gravação atômica do snapshot no pendrive e no computador local
    for target_snap in [pen_snap_file, loc_snap_file]:
        tmp_snap = target_snap.parent / f".{target_snap.name}.tmp_{int(time.time()*1000)}"
        try:
            tmp_snap.parent.mkdir(parents=True, exist_ok=True)
            tmp_snap.write_text(json.dumps(novo_snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            tmp_snap.replace(target_snap)
        except Exception as e:
            tmp_snap.unlink(missing_ok=True)
            relatorio.erros.append(f"Erro ao salvar snapshot em {target_snap}: {e}")


def _limpar_pastas_vazias(diretorio: Path):
    """Remove recursivamente diretórios vazios preservando a raiz e diretórios de controle como .git."""
    if not diretorio.exists():
        return
    for raiz, dirs, _ in os.walk(diretorio, topdown=False):
        for d in dirs:
            if d == ".git":
                continue
            p = Path(raiz) / d
            try:
                if not any(p.iterdir()):
                    p.rmdir()
            except OSError:
                pass

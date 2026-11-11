#!/usr/bin/env python3
"""Controle local do laboratório portátil universal. Não instala serviços nem modifica o sistema."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import zipfile

try:
    from aluno import Aluno, obter_ou_solicitar_aluno, validar_identificador
    from extensoes import instalar_extensoes_locais
    from sincronizacao import sincronizar_projetos, RelatorioSincronizacao
except ImportError:
    try:
        from kit.aluno import Aluno, obter_ou_solicitar_aluno, validar_identificador
        from kit.extensoes import instalar_extensoes_locais
        from kit.sincronizacao import sincronizar_projetos, RelatorioSincronizacao
    except ImportError:
        Aluno = None
        sincronizar_projetos = None
        RelatorioSincronizacao = None

ROOT = Path(__file__).resolve().parent
WINDOWS = sys.platform == "win32"
TARGET = "windows-x64" if WINDOWS else "linux-x64"


def obter_local_root() -> Path:
    """Determina o diretório base de armazenamento persistente no SSD local."""
    custom = os.environ.get("LAB_LOCAL_ROOT")
    if custom:
        return Path(custom)
    if WINDOWS:
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            return Path(local_app) / "LaboratorioAulas"
        return Path.home() / "AppData" / "Local" / "LaboratorioAulas"
    elif sys.platform.startswith("linux"):
        xdg_data = os.environ.get("XDG_DATA_HOME")
        if xdg_data:
            return Path(xdg_data) / "laboratorio-aulas"
        return Path.home() / ".local" / "share" / "laboratorio-aulas"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "LaboratorioAulas"
    return Path.home() / ".laboratorio-aulas"


def detectar_disciplina(kit_root: Path) -> str:
    """Detecta se o kit corresponde a Web ou Java a partir de arquivos e manifestos."""
    prep = kit_root / "PREPARACAO.json"
    if prep.exists():
        try:
            data = json.loads(prep.read_text(encoding="utf-8"))
            p = data.get("perfil")
            if p in ("web", "poo-java"):
                return "web" if p == "web" else "java"
        except Exception:
            pass
    if (kit_root / "projetos" / "web").exists() or (kit_root / "tools" / TARGET / "php").exists() or (kit_root / "ferramentas" / TARGET / "php").exists():
        return "web"
    if (kit_root / "projetos" / "java").exists() or (kit_root / "tools" / TARGET / "jdk").exists() or (kit_root / "ferramentas" / TARGET / "jdk").exists():
        return "java"
    return "web"


# Caminhos canônicos da nova arquitetura
LOCAL_ROOT = obter_local_root()
DISCIPLINA = detectar_disciplina(ROOT)
LOCAL_KITS = LOCAL_ROOT / "kits" / DISCIPLINA / TARGET
LOCAL_TOOLS = LOCAL_KITS / "tools"
LOCAL_EXTENSIONS = LOCAL_KITS / "extensions"
LOCAL_BOOTSTRAP = LOCAL_ROOT / "bootstrap"

# Definições retrocompatíveis
TOOLS_PENDRIVE = ROOT / "ferramentas" / TARGET if (ROOT / "ferramentas" / TARGET).exists() else ROOT / "tools" / TARGET
TOOLS = LOCAL_TOOLS
STATE = LOCAL_ROOT / "estado" / TARGET
VSCODE_USER = LOCAL_ROOT / "configuracoes" / "vscode"


def provisionar_ferramentas_locais(kit_root: Path, local_tools: Path, target: str, disciplina: str) -> Path:
    """
    Provisiona ou atualiza as ferramentas de desenvolvimento no SSD local.
    Compartilhadas entre alunos por disciplina e arquitetura de sistema para máxima velocidade.
    """
    src_tools = kit_root / "ferramentas" / target
    if not src_tools.exists():
        src_tools = kit_root / "tools" / target

    if not src_tools.exists():
        return local_tools if local_tools.exists() else src_tools

    lock_file = kit_root / "componentes.lock.json"
    if lock_file.exists():
        try:
            import hashlib
            lock_hash = hashlib.sha256(lock_file.read_bytes()).hexdigest()
        except Exception:
            lock_hash = f"{disciplina}-{target}"
    else:
        lock_hash = f"{disciplina}-{target}"

    manifest_file = local_tools / "manifesto-instalacao.json"
    if manifest_file.exists() and (local_tools / "bin").exists():
        try:
            m = json.loads(manifest_file.read_text(encoding="utf-8"))
            if m.get("lock_hash") == lock_hash and m.get("status") == "ok":
                return local_tools
        except Exception:
            pass

    local_tools.parent.mkdir(parents=True, exist_ok=True)
    import time
    tmp_target = local_tools.parent / f"tools_tmp_{int(time.time())}"
    if tmp_target.exists():
        shutil.rmtree(tmp_target, ignore_errors=True)

    try:
        shutil.copytree(src_tools, tmp_target, dirs_exist_ok=True)

        src_deps = kit_root / "dependencias"
        if src_deps.exists():
            dest_deps = local_tools.parent / "dependencias"
            shutil.copytree(src_deps, dest_deps, dirs_exist_ok=True)

        manifest_data = {
            "disciplina": disciplina,
            "target": target,
            "lock_hash": lock_hash,
            "data_instalacao": datetime.now().isoformat(),
            "status": "ok"
        }
        (tmp_target / "manifesto-instalacao.json").write_text(
            json.dumps(manifest_data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8"
        )

        if not WINDOWS:
            for bin_file in tmp_target.rglob("*"):
                if bin_file.is_file():
                    if (bin_file.parent.name == "bin" or
                        bin_file.name in ("frankenphp", "python3", "git") or
                        "jdk/bin" in str(bin_file)):
                        try:
                            bin_file.chmod(bin_file.stat().st_mode | 0o755)
                        except OSError:
                            pass

        if local_tools.exists():
            backup_dir = local_tools.parent / f"tools_old_{int(time.time())}"
            try:
                local_tools.rename(backup_dir)
                tmp_target.rename(local_tools)
                shutil.rmtree(backup_dir, ignore_errors=True)
            except OSError:
                shutil.copytree(tmp_target, local_tools, dirs_exist_ok=True)
                shutil.rmtree(tmp_target, ignore_errors=True)
        else:
            tmp_target.rename(local_tools)

        return local_tools

    except Exception as e:
        shutil.rmtree(tmp_target, ignore_errors=True)
        return src_tools


def find_vscode():
    """Localiza o executável do Visual Studio Code instalado na máquina hospedeira."""
    # 1. PATH do sistema
    for name in ("code.cmd", "code.exe", "code"):
        found = shutil.which(name)
        if found:
            return Path(found)

    # 2. Diretórios conhecidos no Windows
    if WINDOWS:
        candidates = []
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            candidates.append(Path(local_app) / "Programs" / "Microsoft VS Code" / "Code.exe")
            candidates.append(Path(local_app) / "Programs" / "Microsoft VS Code" / "bin" / "code.cmd")
        prog_files = os.environ.get("ProgramFiles")
        if prog_files:
            candidates.append(Path(prog_files) / "Microsoft VS Code" / "Code.exe")
            candidates.append(Path(prog_files) / "Microsoft VS Code" / "bin" / "code.cmd")
        prog_files_x86 = os.environ.get("ProgramFiles(x86)")
        if prog_files_x86:
            candidates.append(Path(prog_files_x86) / "Microsoft VS Code" / "Code.exe")
            candidates.append(Path(prog_files_x86) / "Microsoft VS Code" / "bin" / "code.cmd")

        for c in candidates:
            if c.exists():
                return c

    # 3. Diretórios conhecidos no Linux
    elif sys.platform.startswith("linux"):
        for path_str in [
            "/usr/bin/code",
            "/usr/share/code/bin/code",
            "/snap/bin/code",
            "/var/lib/flatpak/exports/bin/com.visualstudio.code"
        ]:
            c = Path(path_str)
            if c.exists():
                return c

    # 4. macOS (desenvolvimento / teste)
    elif sys.platform == "darwin":
        mac_app = Path("/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code")
        if mac_app.exists():
            return mac_app

    return None


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


class Lab:
    def __init__(self, kit_root=None, local_root=None, aluno_id=None, interativo=False):
        if sys.platform not in ("win32", "linux"):
            raise RuntimeError("Execute o kit no Windows 11 ou Linux Mint x64.")
        if platform.machine().lower() not in ("amd64", "x86_64"):
            raise RuntimeError("Este kit destina-se a computadores x86 de 64 bits.")

        self.kit_root = kit_root or ROOT
        self.local_root = local_root or LOCAL_ROOT
        self.disciplina = detectar_disciplina(self.kit_root)

        # 1. Aluno e perfil individual
        if Aluno is not None:
            if aluno_id:
                self.aluno = Aluno(aluno_id, self.kit_root, self.local_root)
                self.aluno.garantir_pastas()
                self.aluno.inicializar_perfil_vscode(self.kit_root / "configuracoes" / "vscode")
                self.aluno.recuperar_git()
            else:
                self.aluno = obter_ou_solicitar_aluno(self.kit_root, self.local_root, interativo=interativo)
        else:
            self.aluno = None

        # 2. Se TOOLS foi explicitamente patcheado/sobrescrito (ex: em teste unitário)
        if TOOLS != LOCAL_TOOLS and TOOLS.exists():
            self.tools = TOOLS
        else:
            local_target_tools = self.local_root / "kits" / self.disciplina / TARGET / "tools"
            self.tools = provisionar_ferramentas_locais(self.kit_root, local_target_tools, TARGET, self.disciplina)
            if not self.tools.exists() and TOOLS_PENDRIVE.exists():
                self.tools = TOOLS_PENDRIVE

        # 3. Extensões locais
        self.local_extensions = self.local_root / "kits" / self.disciplina / TARGET / "extensions"
        if "instalar_extensoes_locais" in globals() and callable(instalar_extensoes_locais):
            try:
                instalar_extensoes_locais(self.kit_root, self.local_extensions, TARGET, self.disciplina, find_vscode())
            except Exception:
                pass

        if STATE != (LOCAL_ROOT / "estado" / TARGET):
            self.state = STATE
        else:
            self.state = self.aluno.local_estado if self.aluno else STATE
        self.state.mkdir(parents=True, exist_ok=True)
        VSCODE_USER.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            try:
                import ctypes
                for p in [self.kit_root / "configuracoes", self.tools]:
                    if p.exists():
                        ctypes.windll.kernel32.SetFileAttributesW(str(p), 2)
            except Exception:
                pass

        self.python = self.tools / ("python/python.exe" if WINDOWS else "python/bin/python3")
        self.php = self.tools / ("php/php.exe" if WINDOWS else "bin/php")
        self.vscode = find_vscode()

        self.env = os.environ.copy()
        for key in ["PYTHONHOME", "VIRTUAL_ENV", "COMPOSER", "COMPOSER_AUTH", "PIP_PREFIX", "PIP_ROOT",
                    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES"]:
            self.env.pop(key, None)

        paths = [
            self.tools / "bin", self.tools / "python", self.tools / "python/bin", self.tools / "php",
            self.tools / "jdk/bin", self.tools / "git/cmd"
        ]
        self.env["PATH"] = os.pathsep.join(str(p) for p in paths if p.exists()) + os.pathsep + self.env.get("PATH", "")
        if (self.tools / "jdk").exists():
            self.env["JAVA_HOME"] = str(self.tools / "jdk")
        self.env["LAB_ROOT"] = str(self.kit_root)
        self.env["LAB_LOCAL_ROOT"] = str(self.local_root)
        self.env["LAB_LOCAL_TOOLS"] = str(self.tools)

        # Python offline
        self.env["PYTHONPATH"] = str(self.state / "python-packages")
        self.env["PYTHONNOUSERSITE"] = "1"
        self.env["PIP_CONFIG_FILE"] = os.devnull
        self.env["PIP_NO_INDEX"] = "1"
        self.env["PIP_FIND_LINKS"] = str(self.kit_root / "dependencias/python")
        self.env["PIP_TARGET"] = str(self.state / "python-packages")
        self.env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        self.env["PIP_REQUIRE_VIRTUALENV"] = "0"
        self.env["PIP_USER"] = "0"

        # Composer offline
        self.env["COMPOSER_HOME"] = str(self.state / "composer-home")
        self.env["COMPOSER_CACHE_DIR"] = str(self.state / "composer-cache")
        self.env["COMPOSER_DISABLE_NETWORK"] = "1"
        self.env["COMPOSER_NO_INTERACTION"] = "1"

        # Git offline individual
        if self.aluno and self.aluno.local_gitconfig.exists():
            self.env["GIT_CONFIG_GLOBAL"] = str(self.aluno.local_gitconfig)
        else:
            self.env["GIT_CONFIG_GLOBAL"] = str(self.state / "gitconfig")
            if not (self.state / "gitconfig").exists():
                (self.state / "gitconfig").write_text('[init]\n\tdefaultBranch = main\n[core]\n\teditor = code --wait\n\tautocrlf = input\n\tlongpaths = true\n', encoding="utf-8")
        self.env["GIT_CONFIG_NOSYSTEM"] = "1"

        for name in ["tmp", "python-packages", "composer-home", "composer-cache", "php-conf"]:
            (self.state / name).mkdir(exist_ok=True)
        for key in ["TMP", "TEMP", "TMPDIR"]:
            self.env[key] = str(self.state / "tmp")

        # Configuração do PHP
        self.env["PHPRC"] = str(self.state / "php-conf")
        self.env["PHP_INI_SCAN_DIR"] = str(self.state / "php-conf/extra")
        (self.state / "php-conf/extra").mkdir(exist_ok=True)
        ini = 'date.timezone=America/Fortaleza\ndefault_charset=UTF-8\ndisplay_errors=On\nerror_reporting=E_ALL\nmemory_limit=256M\n'
        if WINDOWS:
            ini += 'extension_dir="ext"\n'
            ini += 'extension=mbstring\nextension=openssl\nextension=curl\nextension=fileinfo\nextension=zip\n'
            if (self.tools / "php").exists():
                try:
                    (self.tools / "php/php.ini").write_text(ini, encoding="utf-8")
                except OSError:
                    pass
        (self.state / "php-conf/php.ini").write_text(ini, encoding="utf-8")

        config = {"config": {"allow-plugins": False}, "repositories": {"packagist.org": False}}
        (self.state / "composer-home/config.json").write_text(json.dumps(config), encoding="utf-8")

    def editor(self, **kwargs):
        code_bin = self.vscode or find_vscode()
        if not code_bin:
            print("\n" + "=" * 60)
            print("❌ Visual Studio Code não encontrado neste computador!")
            print("=" * 60)
            print("Para utilizar o ambiente das aulas, o Visual Studio Code precisa")
            print("estar instalado na máquina.")
            print("\nVocê pode baixá-lo gratuitamente em:")
            print("👉 https://code.visualstudio.com/")
            print("=" * 60 + "\n")
            try:
                import webbrowser
                resp = input("Deseja abrir a página de download do VS Code agora? [S/n]: ").strip().lower()
                if resp in ("", "s", "sim", "y", "yes"):
                    webbrowser.open("https://code.visualstudio.com/")
            except Exception:
                pass
            return False

        user_data_dir = self.aluno.local_vscode_user_data if self.aluno else (self.local_root / "configuracoes" / "vscode")
        ext_dir = self.local_extensions
        if not ext_dir.exists():
            ext_dir = self.tools / "extensions"
        if not ext_dir.exists():
            ext_dir = self.kit_root / "tools" / "extensions"
        if not ext_dir.exists() and (self.tools / "vscode/data/extensions").exists():
            ext_dir = self.tools / "vscode/data/extensions"

        cmd = [
            str(code_bin),
            "--user-data-dir", str(user_data_dir),
            "--extensions-dir", str(ext_dir),
            "--locale", "pt-BR",
            "--new-window"
        ]
        if not WINDOWS:
            cmd.append("--no-sandbox")

        if self.aluno:
            # Sincronização inicial inteligente antes de abrir o editor
            try:
                self.aluno.sincronizar_projetos(self.disciplina)
            except Exception:
                pass
            proj_local = self.aluno.local_projetos / self.disciplina
            if not proj_local.exists():
                proj_local.mkdir(parents=True, exist_ok=True)
                src_template = self.kit_root / "projetos" / self.disciplina
                if src_template.exists():
                    shutil.copytree(src_template, proj_local, dirs_exist_ok=True)
            target_dir = proj_local
        else:
            target_dir = None
            for sub in ["web", "java"]:
                candidate = self.kit_root / "projetos" / sub
                if candidate.is_dir():
                    target_dir = candidate
                    break
            if not target_dir or not target_dir.exists():
                target_dir = self.kit_root / "projetos"

        cmd.append(str(target_dir))
        try:
            subprocess.Popen(cmd, env=self.env)
            aluno_nome = self.aluno.id if self.aluno else "padrão"
            print(f"🚀 Editor VS Code iniciado para o aluno '{aluno_nome}'!")
            return True
        except Exception as e:
            print(f"❌ Erro ao iniciar o VS Code ({code_bin}): {e}")
            return False

    def terminal(self):
        shell = os.environ.get("COMSPEC", "cmd.exe") if WINDOWS else os.environ.get("SHELL", "bash")
        if self.aluno and (self.aluno.local_projetos / self.disciplina).is_dir():
            cwd = self.aluno.local_projetos / self.disciplina
        elif (self.kit_root / "projetos" / self.disciplina).is_dir():
            cwd = self.kit_root / "projetos" / self.disciplina
        else:
            cwd = self.kit_root / "projetos"
        subprocess.run([shell], env=self.env, cwd=cwd)

    def configurar_git_aluno(self):
        """Permite ao aluno definir seu nome e e-mail Git individual."""
        if not self.aluno:
            print("Nenhum perfil de aluno ativo.")
            return
        print("\n" + "=" * 55)
        print("  ⚙️ CONFIGURAR IDENTIDADE GIT DO ALUNO")
        print("=" * 55)
        try:
            nome = input("Seu Nome (ex: Maria Silva): ").strip()
            email = input("Seu E-mail (ex: maria@escola.edu.br): ").strip()
            if nome and email:
                self.aluno.configurar_git(nome, email)
                self.env["GIT_CONFIG_GLOBAL"] = str(self.aluno.local_gitconfig)
                print("  ✅ Identidade Git salva com sucesso!")
            else:
                print("  ⚠️ Nome ou e-mail vazio. Nenhuma alteração feita.")
        except (EOFError, KeyboardInterrupt):
            print("\nOperação cancelada.")

    def git(self, *args, **kwargs):
        git_exe = self.tools / ("git/cmd/git.exe" if WINDOWS else "sysroot/usr/bin/git")
        env = self.env.copy()
        if not WINDOWS:
            env["LD_LIBRARY_PATH"] = os.pathsep.join(str(p) for p in [
                self.tools / "sysroot/usr/lib/x86_64-linux-gnu",
                self.tools / "sysroot/lib/x86_64-linux-gnu"
            ])
            env["GIT_EXEC_PATH"] = str(self.tools / "sysroot/usr/lib/git-core")
            env["GIT_TEMPLATE_DIR"] = str(self.tools / "sysroot/usr/share/git-core/templates")
        return run([git_exe, *args], env=env, **kwargs)

    def doctor(self):
        print("\n🔍 Verificando integridade das ferramentas...\n")
        failures = []

        # Python
        try:
            res = run([self.python, "--version"], capture_output=True, text=True, env=self.env)
            print(f"  ✅ Python ({res.stdout.strip()})")
        except Exception as e:
            failures.append("Python")
            print(f"  ❌ Python — {e}")

        # Git
        try:
            with tempfile.TemporaryDirectory() as d:
                folder = Path(d)
                self.git("-C", folder, "init", capture_output=True)
                (folder / "teste.txt").write_text("ok")
                self.git("-C", folder, "add", "teste.txt", capture_output=True)
                self.git("-C", folder, "-c", "user.name=Diagnostico", "-c", "user.email=teste@localhost", "commit", "-m", "teste", capture_output=True)
                self.git("-C", folder, "bundle", "create", "teste.bundle", "--all", capture_output=True)
                self.git("-C", folder, "bundle", "verify", "teste.bundle", capture_output=True)
            print("  ✅ Git (init/add/commit/bundle)")
        except Exception as e:
            failures.append("Git")
            print(f"  ❌ Git — {e}")

        # PHP (se aplicável)
        if (self.tools / ("php/php.exe" if WINDOWS else "bin/php")).exists():
            try:
                res = run([self.php, "-v"], capture_output=True, text=True, env=self.env)
                ver = res.stdout.splitlines()[0]
                print(f"  ✅ PHP ({ver})")
            except Exception as e:
                failures.append("PHP")
                print(f"  ❌ PHP — {e}")

        # Java (se aplicável)
        if (self.tools / "jdk").exists():
            try:
                javac = self.tools / ("jdk/bin/javac.exe" if WINDOWS else "jdk/bin/javac")
                res = run([javac, "--version"], capture_output=True, text=True, env=self.env)
                print(f"  ✅ Java JDK ({res.stdout.strip()})")
            except Exception as e:
                failures.append("Java")
                print(f"  ❌ Java — {e}")

        # VS Code na máquina
        code_bin = self.vscode or find_vscode()
        if code_bin:
            print(f"  ✅ VS Code da máquina ({code_bin})")
        else:
            print("  ⚠️  VS Code não encontrado na máquina (instale em https://code.visualstudio.com/)")

        if failures:
            raise RuntimeError("Componentes com falha: " + ", ".join(failures))
        print("\n✅ Todas as ferramentas verificadas estão funcionando perfeitamente!")

    def backup(self):
        folder = self.kit_root / "backups"
        folder.mkdir(exist_ok=True)
        dest = folder / ("projetos-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".zip")
        part = dest.with_suffix(".zip.part")
        try:
            with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as zf:
                for p in (self.kit_root / "projetos").rglob("*"):
                    if p.is_file():
                        arcname = p.relative_to(self.kit_root)
                        zf.write(p, str(arcname))
            part.replace(dest)
        except Exception:
            part.unlink(missing_ok=True)
            raise
        print(f"💾 Cópia de segurança salva em: {dest}")
        return dest

    def sincronizar(self, silencioso: bool = False):
        """Sincroniza os projetos do aluno entre o computador e o pendrive."""
        if not self.aluno:
            if not silencioso:
                print("Nenhum perfil de aluno ativo para sincronizar.")
            return None
        if not silencioso:
            print(f"\n🔄 Sincronizando projetos do aluno '{self.aluno.id}'...")
        relatorio = self.aluno.sincronizar_projetos(self.disciplina)
        if relatorio and not silencioso:
            print(relatorio.resumo())
        return relatorio

    def sincronizar_tudo(self, silencioso: bool = False):
        """Sincroniza perfil e projetos do aluno para o pendrive ao encerrar ou salvar."""
        if not self.aluno:
            return None
        if not silencioso:
            print(f"\n💾 Salvando configurações e projetos no pendrive para '{self.aluno.id}'...")
        try:
            self.aluno.sincronizar_perfil_para_pendrive()
        except Exception as e:
            if not silencioso:
                print(f"  ⚠️ Erro ao salvar perfil pessoal: {e}")
        relatorio = self.aluno.sincronizar_projetos(self.disciplina)
        if relatorio and not silencioso:
            print(relatorio.resumo())
        return relatorio

    def web(self):
        web_root = self.kit_root / "projetos/web" if (self.kit_root / "projetos/web").exists() else self.kit_root / "projetos/php"
        print("🌐 Servidor web iniciado! Abra http://127.0.0.1:8080 no navegador.")
        print("   Pressione Ctrl+C para encerrar o servidor.")
        command = [self.php, "-S", "127.0.0.1:8080", "-t", web_root] if WINDOWS else [self.tools / "php/frankenphp", "php-server", "--listen", "127.0.0.1:8080", "--root", web_root]
        run(command, env=self.env)

    def ajuda(self):
        print("""
╔══════════════════════════════════════════════════════════════╗
║  ❓ AJUDA DO LABORATÓRIO PORTÁTIL UNIVERSAL                   ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  1  📝 Abrir editor de código (VS Code)                      ║
║     Abre o editor de código com a pasta do seu projeto.      ║
║                                                              ║
║  2  💻 Abrir terminal do laboratório                         ║
║     Abre um terminal com todas as ferramentas prontas.       ║
║                                                              ║
║  3  🔄 Sincronizar projetos com o pendrive                   ║
║     Sincroniza alterações do SSD local com o pendrive.       ║
║                                                              ║
║  4  💾 Fazer cópia de segurança (Backup dos projetos)        ║
║     Gera um .zip em backups/ com todos os seus códigos.      ║
║                                                              ║
║  5  🌐 Iniciar servidor web PHP                              ║
║     Disponibiliza o servidor local em http://127.0.0.1:8080  ║
║                                                              ║
║  6  ⚙️ Configurar identidade Git (Nome/E-mail)                ║
║     Configura seu nome e e-mail para commits locais.         ║
║                                                              ║
║  7  🔍 Verificar integridade (Doctor)                        ║
║     Testa compiladores, git e caminhos do sistema.           ║
║                                                              ║
║  0  🚪 Sair (com sincronização automática)                   ║
║     Salva seus projetos e configurações no pendrive.         ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
""")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("acao", nargs="?", default="menu", choices=["menu", "abrir", "terminal", "diagnostico", "backup", "web", "sincronizar"])
    parser.add_argument("--aluno", help="Identificador do aluno para sessao")
    args = parser.parse_args()
    lab = Lab(aluno_id=args.aluno, interativo=(args.acao == "menu"))
    actions = {
        "abrir": lab.editor,
        "terminal": lab.terminal,
        "diagnostico": lab.doctor,
        "backup": lab.backup,
        "web": lab.web,
        "sincronizar": lab.sincronizar
    }
    if args.acao != "menu":
        actions[args.acao]()
    else:
        choices = {
            "1": lab.editor,
            "2": lab.terminal,
            "3": lab.sincronizar,
            "4": lab.backup,
            "5": lab.web,
            "6": lab.configurar_git_aluno,
            "7": lab.doctor,
            "8": lab.ajuda
        }
        aluno_tag = lab.aluno.id if lab.aluno else "padrão"
        while True:
            print(f"""
╔════════════════════════════════════════════════════╗
║  🧪 LABORATÓRIO PORTÁTIL UNIVERSAL                 ║
║  👤 Aluno: {aluno_tag:<39} ║
╠════════════════════════════════════════════════════╣
║                                                    ║
║  1  📝 Abrir editor de código (VS Code)            ║
║  2  💻 Abrir terminal do laboratório               ║
║  3  🔄 Sincronizar projetos com o pendrive         ║
║  4  💾 Fazer cópia de segurança (Backup)           ║
║  5  🌐 Iniciar servidor web PHP                    ║
║  6  ⚙️ Configurar identidade Git (Nome/E-mail)      ║
║  7  🔍 Verificar integridade (Doctor)              ║
║  8  ❓ Ajuda                                       ║
║  0  🚪 Sair (com sincronização automática)         ║
║                                                    ║
╚════════════════════════════════════════════════════╝""")
            choice = input("\n👉 Escolha uma opção: ").strip()
            if choice == "0":
                lab.sincronizar_tudo()
                print("\n👋 Até logo! Lembre-se de ejetar o pendrive com segurança antes de remover.")
                return
            action = choices.get(choice)
            if action:
                try:
                    action()
                except Exception as exc:
                    print(f"❌ Erro: {exc}")
            else:
                print("⚠️ Opção inválida. Tente novamente.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Encerrado pelo usuário.")
        sys.exit(0)
    except Exception as exc:
        print(f"❌ {exc}", file=sys.stderr)
        sys.exit(1)

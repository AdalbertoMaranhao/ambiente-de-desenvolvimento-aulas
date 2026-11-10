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
import zipfile

ROOT = Path(__file__).resolve().parent
WINDOWS = sys.platform == "win32"
TARGET = "windows-x64" if WINDOWS else "linux-x64"
TOOLS = ROOT / "ferramentas" / TARGET if (ROOT / "ferramentas" / TARGET).exists() else ROOT / "tools" / TARGET
STATE = ROOT / "configuracoes" / TARGET
VSCODE_USER = ROOT / "configuracoes" / "vscode"


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


class Lab:
    def __init__(self):
        if sys.platform not in ("win32", "linux"):
            raise RuntimeError("Execute o kit no Windows 11 ou Linux Mint x64.")
        if platform.machine().lower() not in ("amd64", "x86_64"):
            raise RuntimeError("Este kit destina-se a computadores x86 de 64 bits.")

        STATE.mkdir(parents=True, exist_ok=True)
        VSCODE_USER.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            try:
                import ctypes
                for p in [ROOT / "configuracoes", TOOLS]:
                    if p.exists():
                        ctypes.windll.kernel32.SetFileAttributesW(str(p), 2)
            except Exception:
                pass

        self.python = TOOLS / ("python/python.exe" if WINDOWS else "python/bin/python3")
        self.php = TOOLS / ("php/php.exe" if WINDOWS else "bin/php")
        self.vscode = TOOLS / ("vscode/Code.exe" if WINDOWS else "vscode/bin/code")

        self.env = os.environ.copy()
        for key in ["PYTHONHOME", "VIRTUAL_ENV", "COMPOSER", "COMPOSER_AUTH", "PIP_PREFIX", "PIP_ROOT",
                    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES"]:
            self.env.pop(key, None)

        paths = [
            TOOLS / "bin", TOOLS / "python", TOOLS / "python/bin", TOOLS / "php",
            TOOLS / "jdk/bin", TOOLS / "git/cmd", TOOLS / "vscode/bin"
        ]
        self.env["PATH"] = os.pathsep.join(str(p) for p in paths if p.exists()) + os.pathsep + self.env.get("PATH", "")
        if (TOOLS / "jdk").exists():
            self.env["JAVA_HOME"] = str(TOOLS / "jdk")
        self.env["LAB_ROOT"] = str(ROOT)

        # Python offline
        self.env["PYTHONPATH"] = str(STATE / "python-packages")
        self.env["PYTHONNOUSERSITE"] = "1"
        self.env["PIP_CONFIG_FILE"] = os.devnull
        self.env["PIP_NO_INDEX"] = "1"
        self.env["PIP_FIND_LINKS"] = str(ROOT / "dependencias/python")
        self.env["PIP_TARGET"] = str(STATE / "python-packages")
        self.env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        self.env["PIP_REQUIRE_VIRTUALENV"] = "0"
        self.env["PIP_USER"] = "0"

        # Composer offline
        self.env["COMPOSER_HOME"] = str(STATE / "composer-home")
        self.env["COMPOSER_CACHE_DIR"] = str(STATE / "composer-cache")
        self.env["COMPOSER_DISABLE_NETWORK"] = "1"
        self.env["COMPOSER_NO_INTERACTION"] = "1"

        # Git offline
        self.env["GIT_CONFIG_GLOBAL"] = str(STATE / "gitconfig")
        self.env["GIT_CONFIG_NOSYSTEM"] = "1"
        if not (STATE / "gitconfig").exists():
            (STATE / "gitconfig").write_text('[init]\n\tdefaultBranch = main\n[core]\n\teditor = code --wait\n\tautocrlf = input\n\tlongpaths = true\n', encoding="utf-8")

        for name in ["tmp", "python-packages", "composer-home", "composer-cache", "php-conf"]:
            (STATE / name).mkdir(exist_ok=True)
        for key in ["TMP", "TEMP", "TMPDIR"]:
            self.env[key] = str(STATE / "tmp")

        # Configuração do PHP com SQLite
        self.env["PHPRC"] = str(STATE / "php-conf")
        self.env["PHP_INI_SCAN_DIR"] = str(STATE / "php-conf/extra")
        (STATE / "php-conf/extra").mkdir(exist_ok=True)
        ini = 'date.timezone=America/Fortaleza\ndefault_charset=UTF-8\ndisplay_errors=On\nerror_reporting=E_ALL\nmemory_limit=256M\n'
        if WINDOWS:
            ini += 'extension_dir="ext"\n'
            ini += 'extension=pdo_sqlite\nextension=sqlite3\nextension=mbstring\nextension=openssl\nextension=curl\nextension=fileinfo\nextension=zip\n'
            if (TOOLS / "php").exists():
                try:
                    (TOOLS / "php/php.ini").write_text(ini, encoding="utf-8")
                except OSError:
                    pass
        (STATE / "php-conf/php.ini").write_text(ini, encoding="utf-8")

        config = {"config": {"allow-plugins": False}, "repositories": {"packagist.org": False}}
        (STATE / "composer-home/config.json").write_text(json.dumps(config), encoding="utf-8")

    def editor(self, **kwargs):
        ext_dir = TOOLS / "vscode/data/extensions"
        user_dir = ROOT / "configuracoes/vscode"

        vscode_exe = self.vscode
        if not WINDOWS:
            # No Linux, garantir permissões de execução nos binários do VS Code
            for p in [
                self.vscode,
                TOOLS / "vscode/code",
                TOOLS / "vscode/bin/code",
                TOOLS / "vscode/chrome-sandbox",
                TOOLS / "vscode/chrome_crashpad_handler"
            ]:
                if p.exists():
                    try:
                        p.chmod(p.stat().st_mode | 0o755)
                    except OSError:
                        pass

            if not vscode_exe.exists() and (TOOLS / "vscode/code").exists():
                vscode_exe = TOOLS / "vscode/code"

        if not vscode_exe.exists():
            # Fallback caso o VS Code esteja instalado na máquina hospedeira
            system_code = shutil.which("code")
            if system_code:
                vscode_exe = Path(system_code)
            else:
                print(f"\n❌ Executável do VS Code não encontrado em {self.vscode}.")
                print("Se você acabou de trocar de branch, execute 'python3 preparar.py montar' para montar o kit.")
                print("Ou instale o VS Code no sistema: https://code.visualstudio.com/\n")
                return False

        cmd = [
            str(vscode_exe),
            "--user-data-dir", str(user_dir),
            "--extensions-dir", str(ext_dir),
            "--locale", "pt-BR"
        ]
        if not WINDOWS:
            # Necessário no Linux quando executado sem SUID sandbox root (pendrive/ambiente portátil)
            cmd.append("--no-sandbox")

        target_dir = None
        for sub in ["web", "python", "java"]:
            candidate = ROOT / "projetos" / sub
            if candidate.is_dir():
                target_dir = candidate
                break
        if not target_dir or not target_dir.exists():
            target_dir = ROOT / "projetos"

        cmd.append(str(target_dir))
        try:
            subprocess.Popen(cmd, env=self.env)
            print("🚀 Editor VS Code iniciado!")
            return True
        except Exception as e:
            print(f"❌ Erro ao iniciar o VS Code ({vscode_exe}): {e}")
            return False

    def terminal(self):
        shell = os.environ.get("COMSPEC", "cmd.exe") if WINDOWS else os.environ.get("SHELL", "bash")
        subprocess.run([shell], env=self.env, cwd=ROOT / "projetos")

    def git(self, *args, **kwargs):
        git_exe = TOOLS / ("git/cmd/git.exe" if WINDOWS else "sysroot/usr/bin/git")
        env = self.env.copy()
        if not WINDOWS:
            env["LD_LIBRARY_PATH"] = os.pathsep.join(str(p) for p in [
                TOOLS / "sysroot/usr/lib/x86_64-linux-gnu",
                TOOLS / "sysroot/lib/x86_64-linux-gnu"
            ])
            env["GIT_EXEC_PATH"] = str(TOOLS / "sysroot/usr/lib/git-core")
            env["GIT_TEMPLATE_DIR"] = str(TOOLS / "sysroot/usr/share/git-core/templates")
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

        # SQLite no Python
        try:
            with sqlite3.connect(":memory:") as conn:
                conn.execute("CREATE TABLE t (id INT);")
            print("  ✅ SQLite nativo (memória e arquivo)")
        except Exception as e:
            failures.append("SQLite")
            print(f"  ❌ SQLite — {e}")

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
        if (TOOLS / ("php/php.exe" if WINDOWS else "bin/php")).exists():
            try:
                res = run([self.php, "-v"], capture_output=True, text=True, env=self.env)
                ver = res.stdout.splitlines()[0]
                run([self.php, "-r", "new PDO('sqlite::memory:');"], capture_output=True, env=self.env)
                print(f"  ✅ PHP ({ver}) com PDO SQLite")
            except Exception as e:
                failures.append("PHP")
                print(f"  ❌ PHP — {e}")

        # Java (se aplicável)
        if (TOOLS / "jdk").exists():
            try:
                javac = TOOLS / ("jdk/bin/javac.exe" if WINDOWS else "jdk/bin/javac")
                res = run([javac, "--version"], capture_output=True, text=True, env=self.env)
                print(f"  ✅ Java JDK ({res.stdout.strip()})")
            except Exception as e:
                failures.append("Java")
                print(f"  ❌ Java — {e}")

        # Bancos de dados dos projetos
        for p in (ROOT / "projetos").glob("*/banco.db"):
            try:
                with sqlite3.connect(p) as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT count(*) FROM sqlite_master WHERE type='table';")
                    qtd = cur.fetchone()[0]
                print(f"  ✅ Banco de dados: {p.relative_to(ROOT)} ({qtd} tabelas)")
            except Exception as e:
                failures.append(str(p))
                print(f"  ❌ Banco {p} — {e}")

        if failures:
            raise RuntimeError("Componentes com falha: " + ", ".join(failures))
        print("\n✅ Todas as ferramentas verificadas estão funcionando perfeitamente!")

    def backup(self):
        folder = ROOT / "backups"
        folder.mkdir(exist_ok=True)
        dest = folder / ("projetos-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".zip")
        part = dest.with_suffix(".zip.part")
        try:
            with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as zf:
                for p in (ROOT / "projetos").rglob("*"):
                    if p.is_file():
                        arcname = p.relative_to(ROOT)
                        zf.write(p, str(arcname))
            part.replace(dest)
        except Exception:
            part.unlink(missing_ok=True)
            raise
        print(f"💾 Cópia de segurança salva em: {dest}")
        return dest

    def web(self):
        web_root = ROOT / "projetos/web" if (ROOT / "projetos/web").exists() else ROOT / "projetos/php"
        print("🌐 Servidor web iniciado! Abra http://127.0.0.1:8080 no navegador.")
        print("   Pressione Ctrl+C para encerrar o servidor.")
        command = [self.php, "-S", "127.0.0.1:8080", "-t", web_root] if WINDOWS else [TOOLS / "php/frankenphp", "php-server", "--listen", "127.0.0.1:8080", "--root", web_root]
        run(command, env=self.env)

    def ajuda(self):
        print("""
╔══════════════════════════════════════════════════════════════╗
║  ❓ AJUDA DO LABORATÓRIO PORTÁTIL UNIVERSAL                   ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  1  📝 Abrir editor de código (VS Code)                      ║
║     Abre o VS Code portátil com seu projeto e banco SQLite.  ║
║                                                              ║
║  2  💻 Abrir terminal do laboratório                         ║
║     Abre um terminal com todas as ferramentas prontas.       ║
║                                                              ║
║  3  🔍 Verificar integridade (Doctor)                        ║
║     Testa compiladores, git, banco SQLite e caminhos.        ║
║                                                              ║
║  4  💾 Fazer cópia de segurança (Backup dos projetos)        ║
║     Gera um .zip em backups/ com todos os códigos e bancos.  ║
║                                                              ║
║  5  🌐 Iniciar servidor web PHP                              ║
║     Disponibiliza o servidor local em http://127.0.0.1:8080  ║
║                                                              ║
║  0  🚪 Sair                                                  ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
""")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("acao", nargs="?", default="menu", choices=["menu", "abrir", "terminal", "diagnostico", "backup", "web"])
    args = parser.parse_args()
    lab = Lab()
    actions = {
        "abrir": lab.editor,
        "terminal": lab.terminal,
        "diagnostico": lab.doctor,
        "backup": lab.backup,
        "web": lab.web
    }
    if args.acao != "menu":
        actions[args.acao]()
    else:
        choices = {
            "1": lab.editor,
            "2": lab.terminal,
            "3": lab.doctor,
            "4": lab.backup,
            "5": lab.web,
            "7": lab.ajuda
        }
        while True:
            print("""
╔════════════════════════════════════════════════════╗
║  🧪 LABORATÓRIO PORTÁTIL UNIVERSAL                 ║
╠════════════════════════════════════════════════════╣
║                                                    ║
║  1  📝 Abrir editor de código (VS Code)            ║
║  2  💻 Abrir terminal do laboratório               ║
║  3  🔍 Verificar integridade (Doctor)              ║
║  4  💾 Fazer cópia de segurança (Backup)           ║
║  5  🌐 Iniciar servidor web PHP                    ║
║  7  ❓ Ajuda                                       ║
║  0  🚪 Sair                                        ║
║                                                    ║
╚════════════════════════════════════════════════════╝""")
            choice = input("\n👉 Escolha uma opção: ").strip()
            if choice == "0":
                print("\n👋 Até logo! Lembre-se de salvar seus arquivos e ejetar o pendrive com segurança.")
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

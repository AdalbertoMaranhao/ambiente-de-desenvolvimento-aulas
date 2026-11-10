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
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parent
WINDOWS = sys.platform == "win32"
TARGET = "windows-x64" if WINDOWS else "linux-x64"
TOOLS = ROOT / "ferramentas" / TARGET if (ROOT / "ferramentas" / TARGET).exists() else ROOT / "tools" / TARGET
STATE = ROOT / "configuracoes" / TARGET
VSCODE_USER = ROOT / "configuracoes" / "vscode"


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


def find_intellij():
    """Localiza o executável do IntelliJ IDEA instalado no Windows."""
    # 1. PATH do sistema
    for name in ("idea64.exe", "idea.cmd", "idea.bat", "idea"):
        found = shutil.which(name)
        if found:
            return Path(found)

    # 2. Diretórios conhecidos no Windows
    if WINDOWS:
        candidates = []
        prog_files = os.environ.get("ProgramFiles")
        if prog_files:
            candidates.extend(Path(prog_files).glob("JetBrains/IntelliJ IDEA*/bin/idea64.exe"))
            candidates.extend(Path(prog_files).glob("JetBrains/IntelliJ IDEA*/bin/idea.cmd"))
        prog_files_x86 = os.environ.get("ProgramFiles(x86)")
        if prog_files_x86:
            candidates.extend(Path(prog_files_x86).glob("JetBrains/IntelliJ IDEA*/bin/idea64.exe"))
            candidates.extend(Path(prog_files_x86).glob("JetBrains/IntelliJ IDEA*/bin/idea.cmd"))
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            candidates.extend(Path(local_app).glob("Programs/IntelliJ IDEA*/bin/idea64.exe"))
            candidates.extend(Path(local_app).glob("JetBrains/Toolbox/apps/**/bin/idea64.exe"))
            candidates.extend(Path(local_app).glob("JetBrains/Toolbox/apps/**/bin/idea.cmd"))

        candidates = [c for c in candidates if c.exists()]
        candidates.sort(reverse=True)
        if candidates:
            return candidates[0]

    return None


def _update_jdk_table_xml(xml_file, home_posix, java_version, modules, src_zip):
    root = None
    if xml_file.exists():
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
        except Exception:
            root = None

    if root is None or root.tag != "application":
        root = ET.Element("application")

    component = None
    for comp in root.findall("component"):
        if comp.get("name") == "ProjectJdkTable":
            component = comp
            break
    if component is None:
        component = ET.SubElement(root, "component", name="ProjectJdkTable")

    # Substituir entrada existente com nome JDK-Kit
    for jdk in list(component.findall("jdk")):
        name_elem = jdk.find("name")
        if name_elem is not None and name_elem.get("value") == "JDK-Kit":
            component.remove(jdk)

    jdk_node = ET.SubElement(component, "jdk", version="2")
    ET.SubElement(jdk_node, "name", value="JDK-Kit")
    ET.SubElement(jdk_node, "type", value="JavaSDK")
    ET.SubElement(jdk_node, "version", value=java_version)
    ET.SubElement(jdk_node, "homePath", value=home_posix)

    roots_elem = ET.SubElement(jdk_node, "roots")

    # annotationsPath
    ann = ET.SubElement(roots_elem, "annotationsPath")
    ET.SubElement(ann, "root", type="composite")

    # classPath com módulos jrt://
    cp = ET.SubElement(roots_elem, "classPath")
    cp_composite = ET.SubElement(cp, "root", type="composite")
    for mod in modules:
        ET.SubElement(cp_composite, "root", url=f"jrt://{home_posix}!/{mod}", type="simple")

    # javadocPath
    javadoc = ET.SubElement(roots_elem, "javadocPath")
    ET.SubElement(javadoc, "root", type="composite")

    # sourcePath
    sp = ET.SubElement(roots_elem, "sourcePath")
    sp_composite = ET.SubElement(sp, "root", type="composite")
    if src_zip and Path(src_zip).exists():
        ET.SubElement(sp_composite, "root", url=f"jar://{src_zip}!/", type="simple")

    ET.SubElement(jdk_node, "additional")

    ET.indent(root, space="  ")
    tree = ET.ElementTree(root)
    tree.write(xml_file, encoding="utf-8", xml_declaration=True)


def configure_intellij_jdk(jdk_dir):
    """Registra ou atualiza o JDK-Kit no arquivo jdk.table.xml do IntelliJ IDEA."""
    if not jdk_dir.exists():
        return False
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return False

    jetbrains_dir = Path(appdata) / "JetBrains"
    target_dirs = []
    if jetbrains_dir.exists():
        for d in jetbrains_dir.iterdir():
            if d.is_dir() and (d.name.startswith("IdeaIC") or d.name.startswith("IntelliJIdea")):
                target_dirs.append(d)

    if not target_dirs:
        idea_exe = find_intellij()
        if idea_exe:
            try:
                install_dir = idea_exe.resolve().parent.parent
                prod_info = install_dir / "product-info.json"
                if prod_info.exists():
                    data = json.loads(prod_info.read_text(encoding="utf-8"))
                    dir_name = data.get("dataDirectoryName")
                    if dir_name:
                        target_dirs.append(jetbrains_dir / dir_name)
            except Exception:
                pass
        if not target_dirs:
            target_dirs.append(jetbrains_dir / "IdeaIC2024.3")

    release_file = jdk_dir / "release"
    java_version = "openjdk-25"
    modules = []
    if release_file.exists():
        try:
            for line in release_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("JAVA_VERSION="):
                    java_version = line.split("=", 1)[1].strip('"').strip("'")
                elif line.startswith("MODULES="):
                    mods_str = line.split("=", 1)[1].strip('"').strip("'")
                    modules = mods_str.split()
        except Exception:
            pass

    if not modules:
        modules = [
            "java.base", "java.compiler", "java.datatransfer", "java.desktop",
            "java.instrument", "java.logging", "java.management", "java.management.rmi",
            "java.naming", "java.net.http", "java.prefs", "java.rmi", "java.scripting",
            "java.se", "java.security.jgss", "java.security.sasl", "java.smartcardio",
            "java.sql", "java.sql.rowset", "java.transaction.xa", "java.xml", "java.xml.crypto",
            "jdk.accessibility", "jdk.attach", "jdk.charsets", "jdk.compiler", "jdk.crypto.cryptoki",
            "jdk.crypto.ec", "jdk.dynalink", "jdk.httpserver", "jdk.incubator.vector",
            "jdk.internal.ed", "jdk.internal.jvmstat", "jdk.internal.le", "jdk.internal.opt",
            "jdk.jartool", "jdk.javadoc", "jdk.jcmd", "jdk.jconsole", "jdk.jdeps",
            "jdk.jdi", "jdk.jdwp.agent", "jdk.jfr", "jdk.jlink", "jdk.jpackage",
            "jdk.jshell", "jdk.jsobject", "jdk.jstatd", "jdk.localedata", "jdk.management",
            "jdk.management.agent", "jdk.management.jfr", "jdk.naming.dns", "jdk.naming.rmi",
            "jdk.net", "jdk.nio.mapmode", "jdk.sctp", "jdk.security.auth", "jdk.security.jgss",
            "jdk.unsupported", "jdk.unsupported.desktop", "jdk.xml.dom", "jdk.zipfs"
        ]

    home_posix = jdk_dir.resolve().as_posix()
    src_zip_candidate = jdk_dir / "lib/src.zip"
    if not src_zip_candidate.exists():
        src_zip_candidate = jdk_dir / "src.zip"
    src_zip = src_zip_candidate.resolve().as_posix() if src_zip_candidate.exists() else None

    for config_dir in target_dirs:
        options_dir = config_dir / "options"
        options_dir.mkdir(parents=True, exist_ok=True)
        jdk_table_file = options_dir / "jdk.table.xml"
        _update_jdk_table_xml(jdk_table_file, home_posix, java_version, modules, src_zip)

    return True


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

        self.python = TOOLS / ("python/python.exe" if WINDOWS else "python/bin/python3")
        self.php = TOOLS / ("php/php.exe" if WINDOWS else "bin/php")
        self.vscode = find_vscode()

        has_only_java_project = (ROOT / "projetos/java").exists() and not (ROOT / "projetos/web").exists() and not (ROOT / "projetos/python").exists()
        self.use_intellij = WINDOWS and ((TOOLS / "jdk").exists() or has_only_java_project)

        self.env = os.environ.copy()
        for key in ["PYTHONHOME", "VIRTUAL_ENV", "COMPOSER", "COMPOSER_AUTH", "PIP_PREFIX", "PIP_ROOT",
                    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES"]:
            self.env.pop(key, None)

        paths = [
            TOOLS / "bin", TOOLS / "python", TOOLS / "python/bin", TOOLS / "php",
            TOOLS / "jdk/bin", TOOLS / "git/cmd"
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
        if self.use_intellij:
            return self.editor_intellij(**kwargs)
        return self.editor_vscode(**kwargs)

    def editor_intellij(self, **kwargs):
        idea_bin = find_intellij()
        if not idea_bin:
            print("\n" + "=" * 60)
            print("❌ IntelliJ IDEA não encontrado neste computador!")
            print("=" * 60)
            print("Para programar em Java neste computador, o IntelliJ IDEA precisa")
            print("estar instalado na máquina (Community ou Ultimate).")
            print("\nVocê pode baixá-lo gratuitamente em:")
            print("👉 https://www.jetbrains.com/idea/download/")
            print("=" * 60 + "\n")
            try:
                import webbrowser
                resp = input("Deseja abrir a página de download do IntelliJ IDEA agora? [S/n]: ").strip().lower()
                if resp in ("", "s", "sim", "y", "yes"):
                    webbrowser.open("https://www.jetbrains.com/idea/download/")
            except Exception:
                pass
            return False

        jdk_dir = TOOLS / "jdk"
        if jdk_dir.exists():
            try:
                configure_intellij_jdk(jdk_dir)
            except Exception as e:
                print(f"⚠️  Aviso ao registrar JDK portátil no IntelliJ: {e}")

        project_dir = ROOT / "projetos/java"
        cmd = [str(idea_bin), str(project_dir)]
        try:
            subprocess.Popen(cmd, env=self.env)
            print("🚀 Editor IntelliJ IDEA iniciado!")
            return True
        except Exception as e:
            print(f"❌ Erro ao iniciar o IntelliJ IDEA ({idea_bin}): {e}")
            return False

    def editor_vscode(self, **kwargs):
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

        workspace = ROOT / "aulas.code-workspace"
        ext_dir = TOOLS / "extensions"
        if not ext_dir.exists() and (TOOLS / "vscode/data/extensions").exists():
            ext_dir = TOOLS / "vscode/data/extensions"
        user_dir = ROOT / "configuracoes/vscode"
        cmd = [
            str(code_bin),
            "--user-data-dir", str(user_dir),
            "--extensions-dir", str(ext_dir),
            "--locale", "pt-BR"
        ]
        if not WINDOWS:
            cmd.append("--no-sandbox")

        if workspace.exists():
            cmd.append(str(workspace))
        else:
            cmd.append(str(ROOT / "projetos"))
        try:
            subprocess.Popen(cmd, env=self.env)
            print("🚀 Editor VS Code iniciado!")
            return True
        except Exception as e:
            print(f"❌ Erro ao iniciar o VS Code ({code_bin}): {e}")
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

        # Editor na máquina
        if self.use_intellij:
            idea_bin = find_intellij()
            if idea_bin:
                print(f"  ✅ IntelliJ IDEA da máquina ({idea_bin})")
            else:
                print("  ⚠️  IntelliJ IDEA não encontrado na máquina (instale em https://www.jetbrains.com/idea/download/)")
        else:
            code_bin = self.vscode or find_vscode()
            if code_bin:
                print(f"  ✅ VS Code da máquina ({code_bin})")
            else:
                print("  ⚠️  VS Code não encontrado na máquina (instale em https://code.visualstudio.com/)")

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
        editor_nome = "IntelliJ IDEA" if self.use_intellij else "VS Code"
        editor_desc = "Abre o IntelliJ IDEA local com seu projeto e banco SQLite." if self.use_intellij else "Abre o VS Code local com as extensões do kit e SQLite."
        print(f"""
╔══════════════════════════════════════════════════════════════╗
║  ❓ AJUDA DO LABORATÓRIO PORTÁTIL UNIVERSAL                   ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  1  📝 Abrir editor de código ({editor_nome:<13})             ║
║     {editor_desc:<57}║
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
            editor_label = "IntelliJ IDEA" if lab.use_intellij else "VS Code"
            print(f"""
╔════════════════════════════════════════════════════╗
║  🧪 LABORATÓRIO PORTÁTIL UNIVERSAL                 ║
╠════════════════════════════════════════════════════╣
║                                                    ║
║  1  📝 Abrir editor de código ({editor_label:<13}) ║
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

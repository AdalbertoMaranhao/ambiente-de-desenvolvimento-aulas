#!/usr/bin/env python3
"""Controle local do laboratorio. Nao instala servicos nem modifica o sistema."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent
WINDOWS = sys.platform == "win32"
TARGET = "windows-x64" if WINDOWS else "linux-x64"
TOOLS = ROOT / "tools" / TARGET
STATE = ROOT / "estado" / TARGET
PORT = 3307

# Mensagens amigaveis para erros tecnicos
FRIENDLY_ERRORS = [
    ("inicio.lock", "O laboratório já está sendo aberto em outra janela. Aguarde ou feche a outra janela e tente novamente."),
    ("porta 3307", "Outro programa está usando a porta do banco. Feche outras janelas do laboratório e tente novamente."),
    ("mariadb.pid", "O banco ainda está desligando. Aguarde alguns segundos."),
    ("Kit incompleto", "As ferramentas não foram preparadas. Peça ao professor para montar o pacote."),
    ("Inicializacao incompleta", "A criação do banco foi interrompida anteriormente. Consulte o professor."),
    ("MariaDB encerrou", "O banco de dados não iniciou. Consulte o professor e o arquivo mariadb.log."),
    ("MariaDB ainda nao respondeu", "O banco demorou muito para iniciar. Tente novamente ou consulte o professor."),
    ("Encerramento em curso", "O banco ainda está desligando. Aguarde alguns segundos antes de copiar a pasta."),
    ("nao foi identificada", "A instância do banco não pertence a este kit. Encerramento recusado para proteger seus dados."),
    ("Inicie o MariaDB", "O banco de dados precisa estar ligado. Escolha a opção 2 no menu antes de continuar."),
]


def friendly_error(exc):
    """Traduz erro tecnico para linguagem humana."""
    msg = str(exc)
    for keyword, friendly in FRIENDLY_ERRORS:
        if keyword.lower() in msg.lower():
            return friendly
    return msg


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


class Lab:
    def __init__(self):
        if sys.platform not in ("win32", "linux"):
            raise RuntimeError("Execute o kit no Windows 11 ou Linux Mint x64.")
        if platform.machine().lower() not in ("amd64", "x86_64"):
            raise RuntimeError("Este kit destina-se a computadores x86 de 64 bits.")
        STATE.mkdir(parents=True, exist_ok=True)
        self.credentials = STATE / "credenciais.json"
        first_run = not self.credentials.exists()
        if first_run:
            try:
                with self.credentials.open("x", encoding="utf-8") as f:
                    json.dump({"root": "root", "aluno": "aluno"}, f)
                self.credentials.chmod(0o600)
            except FileExistsError:
                first_run = False
        self.secret = json.loads(self.credentials.read_text()) if self.credentials.exists() else {"root": "root", "aluno": "aluno"}
        if first_run:
            print("\n🔑 Primeira execução! Credenciais padrão do banco de dados configuradas:")
            print("   Host:    127.0.0.1 (Porta 3307)")
            print("   Banco:   aulas")
            print("   Aluno:   usuário 'aluno', senha 'aluno'")
            print("   Root:    usuário 'root', senha 'root'")
            print("   💡 As conexões já estão salvas no VS Code (SQLTools) e em BEM-VINDO.html\n")
        self.python = TOOLS / ("python/python.exe" if WINDOWS else "python/bin/python3")
        self.php = TOOLS / ("php/php.exe" if WINDOWS else "bin/php")
        self.dbhome = TOOLS / "mariadb"
        self.data = STATE / "mariadb"
        self.env = os.environ.copy()
        for key in ["PYTHONHOME", "VIRTUAL_ENV", "COMPOSER", "COMPOSER_AUTH", "PIP_PREFIX", "PIP_ROOT",
                    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES"]:
            self.env.pop(key, None)
        paths = [TOOLS / "bin", TOOLS / "python", TOOLS / "python/bin", TOOLS / "php",
                 TOOLS / "jdk/bin", TOOLS / "git/cmd", TOOLS / "vscode/bin", self.dbhome / "bin"]
        self.env["PATH"] = os.pathsep.join(map(str, paths)) + os.pathsep + self.env.get("PATH", "")
        self.env["JAVA_HOME"] = str(TOOLS / "jdk")
        self.env["LAB_ROOT"] = str(ROOT)
        self.env["DB_HOST"] = "127.0.0.1"
        self.env["DB_PORT"] = str(PORT)
        self.env["DB_NAME"] = "aulas"
        self.env["DB_USER"] = "aluno"
        self.env["DB_PASSWORD"] = self.secret["aluno"]
        self.env["PYTHONPATH"] = str(STATE / "python-packages")
        self.env["PYTHONNOUSERSITE"] = "1"
        self.env["PIP_CONFIG_FILE"] = os.devnull
        self.env["PIP_NO_INDEX"] = "1"
        self.env["PIP_FIND_LINKS"] = str(ROOT / "dependencias/python")
        self.env["PIP_TARGET"] = str(STATE / "python-packages")
        self.env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        self.env["PIP_REQUIRE_VIRTUALENV"] = "0"
        self.env["PIP_USER"] = "0"
        self.env["COMPOSER_HOME"] = str(STATE / "composer-home")
        self.env["COMPOSER_CACHE_DIR"] = str(STATE / "composer-cache")
        self.env["COMPOSER_DISABLE_NETWORK"] = "1"
        self.env["COMPOSER_NO_INTERACTION"] = "1"
        self.env["GIT_CONFIG_GLOBAL"] = str(STATE / "gitconfig")
        self.env["GIT_CONFIG_NOSYSTEM"] = "1"
        if not (STATE / "gitconfig").exists():
            (STATE / "gitconfig").write_text('[init]\n\tdefaultBranch = main\n[core]\n\teditor = code --wait\n\tautocrlf = input\n\tlongpaths = true\n', encoding="utf-8")
        for name in ["tmp", "python-packages", "composer-home", "composer-cache", "php-conf"]:
            (STATE / name).mkdir(exist_ok=True)
        for key in ["TMP", "TEMP", "TMPDIR"]:
            self.env[key] = str(STATE / "tmp")
        self.env["PHPRC"] = str(STATE / "php-conf")
        self.env["PHP_INI_SCAN_DIR"] = str(STATE / "php-conf/extra")
        (STATE / "php-conf/extra").mkdir(exist_ok=True)
        # Regenerate absolute paths every launch to tolerate a different drive letter.
        ini = 'date.timezone=America/Fortaleza\ndefault_charset=UTF-8\ndisplay_errors=On\nerror_reporting=E_ALL\nmemory_limit=256M\n'
        if WINDOWS:
            ini += 'extension_dir="' + (TOOLS / "php/ext").as_posix() + '"\n'
            ini += 'extension=pdo_mysql\nextension=mysqli\nextension=mbstring\nextension=openssl\nextension=curl\nextension=fileinfo\nextension=zip\n'
        (STATE / "php-conf/php.ini").write_text(ini, encoding="utf-8")
        config = {"config": {"allow-plugins": False}, "repositories": {"packagist.org": False}}
        (STATE / "composer-home/config.json").write_text(json.dumps(config), encoding="utf-8")
        self.client = STATE / "admin.cnf"
        self.client.write_text('[client]\nuser=root\npassword=' + self.secret["root"] + '\nhost=127.0.0.1\nport=' + str(PORT) + '\nprotocol=tcp\n', encoding="utf-8")
        self.client.chmod(0o600)

    def dbexe(self, name):
        return self.dbhome / "bin" / (name + (".exe" if WINDOWS else ""))

    def dbenv(self):
        env = self.env.copy()
        if not WINDOWS:
            env["LD_LIBRARY_PATH"] = os.pathsep.join(map(str, [TOOLS / "sysroot/usr/lib/x86_64-linux-gnu", TOOLS / "sysroot/lib/x86_64-linux-gnu", self.dbhome / "lib"]))
        return env

    def sql(self, query, capture=True):
        return run([self.dbexe("mariadb"), "--defaults-file=" + str(self.client), "--batch", "--skip-column-names", "-e", query],
                   env=self.dbenv(), capture_output=capture, text=True, timeout=10)

    def owns_server(self):
        try:
            current = self.sql("SELECT @@datadir;").stdout.strip()
            return os.path.normcase(os.path.realpath(current)) == os.path.normcase(os.path.realpath(self.data))
        except (subprocess.SubprocessError, OSError):
            return False

    def port_used(self):
        with socket.socket() as sock:
            sock.settimeout(0.5)
            return sock.connect_ex(("127.0.0.1", PORT)) == 0

    def start(self):
        # A file lock serializes first initialization/start, including separate terminals.
        lockfile = STATE / "inicio.lock"
        try:
            fd = os.open(lockfile, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise RuntimeError("Outra inicializacao pode estar em curso. Se foi interrompida, confirme que nao ha MariaDB deste kit em execucao e remova estado/" + TARGET + "/inicio.lock.")
        try:
            os.close(fd)
            self._start()
        finally:
            lockfile.unlink(missing_ok=True)

    def _start(self):
        if self.owns_server():
            print("MariaDB deste kit ja esta ativo.")
            return
        if self.port_used():
            raise RuntimeError("A porta 3307 esta ocupada por outra instancia ou por um kit movido enquanto estava ativo. Encerre essa instancia antes de continuar.")
        if not (self.data / "mysql").is_dir():
            if self.data.exists() and any(self.data.iterdir()):
                raise RuntimeError("Inicializacao anterior incompleta. Preserve os arquivos em " + str(self.data) + " antes de tentar novamente.")
            print("⏳ Criando banco local pela primeira vez...", flush=True)
            print("   Isso pode levar alguns segundos. Aguarde...\n", flush=True)
            if WINDOWS:
                run([self.dbexe("mariadb-install-db"), "--datadir=" + str(self.data), "--password=" + self.secret["root"], "--port=" + str(PORT)], cwd=self.dbhome, env=self.dbenv())
            else:
                run(["sh", self.dbhome / "scripts/mariadb-install-db", "--no-defaults", "--basedir=" + str(self.dbhome), "--datadir=" + str(self.data), "--auth-root-authentication-method=socket", "--skip-test-db"], env=self.dbenv())
        init = STATE / "bootstrap.sql"
        init.write_text("ALTER USER 'root'@'localhost' IDENTIFIED BY '" + self.secret["root"] + "';\n"
                        "CREATE USER IF NOT EXISTS 'root'@'127.0.0.1' IDENTIFIED BY '" + self.secret["root"] + "';\n"
                        "ALTER USER 'root'@'127.0.0.1' IDENTIFIED BY '" + self.secret["root"] + "';\n"
                        "GRANT ALL PRIVILEGES ON *.* TO 'root'@'127.0.0.1' WITH GRANT OPTION;\n"
                        "CREATE DATABASE IF NOT EXISTS aulas CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n"
                        "CREATE USER IF NOT EXISTS 'aluno'@'127.0.0.1' IDENTIFIED BY '" + self.secret["aluno"] + "';\n"
                        "CREATE USER IF NOT EXISTS 'aluno'@'localhost' IDENTIFIED BY '" + self.secret["aluno"] + "';\n"
                        "GRANT ALL ON aulas.* TO 'aluno'@'127.0.0.1';\n"
                        "GRANT ALL ON aulas.* TO 'aluno'@'localhost';\n"
                        "DROP USER IF EXISTS ''@'localhost';\n", encoding="utf-8")
        init.chmod(0o600)
        # Short socket path avoids Unix domain socket length limits in student home paths.
        sock = str(Path(tempfile.gettempdir()) / ("aula-" + self.secret["root"][:12] + ".sock"))
        args = [self.dbexe("mariadbd"), "--no-defaults", "--basedir=" + str(self.dbhome),
                "--datadir=" + str(self.data), "--bind-address=127.0.0.1", "--port=" + str(PORT),
                "--character-set-server=utf8mb4", "--collation-server=utf8mb4_unicode_ci",
                "--innodb-buffer-pool-size=64M", "--max-connections=30", "--skip-name-resolve",
                "--pid-file=" + str(STATE / "mariadb.pid"), "--log-error=" + str(STATE / "mariadb.log"),
                "--init-file=" + str(init)]
        if not WINDOWS:
            args += ["--socket=" + sock]
        with (STATE / "mariadb-console.log").open("ab") as log:
            proc = subprocess.Popen([str(a) for a in args], env=self.dbenv(), cwd=self.dbhome,
                                    stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                                    **({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS else {"start_new_session": True}))
        for _ in range(90):
            if proc.poll() is not None:
                raise RuntimeError("MariaDB encerrou durante a inicializacao. Consulte " + str(STATE / "mariadb.log"))
            if self.owns_server():
                print("✅ Banco de dados pronto! (127.0.0.1:3307, banco: aulas, usuário: aluno)")
                return
            time.sleep(0.5)
        raise RuntimeError("MariaDB ainda nao respondeu. Consulte os logs e use 'parar' antes de tentar novamente.")

    def stop(self):
        if not self.owns_server():
            if self.port_used():
                raise RuntimeError("A instancia da porta 3307 nao foi identificada como pertencente a este kit; encerramento recusado.")
            print("⏹️  Banco de dados já está parado.")
            return
        # Backup automático silencioso antes de encerrar
        if (self.data / "mysql").is_dir():
            try:
                print("💾 Backup automático antes de encerrar...", flush=True)
                self.backup()
                print("✅ Backup salvo com sucesso.")
            except Exception:
                pass  # Falha no backup não impede o encerramento
        run([self.dbexe("mariadb-admin"), "--defaults-file=" + str(self.client), "shutdown"], env=self.dbenv(), timeout=45)
        for _ in range(60):
            if not self.port_used() and not (STATE / "mariadb.pid").exists():
                print("⏹️  Banco de dados encerrado com segurança. Pode copiar a pasta ou remover a unidade.")
                return
            time.sleep(0.5)
        raise RuntimeError("Encerramento em curso. Aguarde a remocao de mariadb.pid e confira mariadb.log antes de copiar.")

    def packages(self):
        req = ROOT / "dependencias/python/requirements.txt"
        if not req.exists():
            return
        check = subprocess.run([str(self.python), "-c", "import pymysql"], env=self.env, capture_output=True)
        if check.returncode:
            run([self.python, "-m", "pip", "install", "--no-index", "--find-links", ROOT / "dependencias/python", "-r", req], env=self.env)

    def editor(self, com_banco=False):
        if com_banco:
            self.start()
            self.packages()
        settings_file = TOOLS / "vscode/data/user-data/User/settings.json"
        settings = json.loads(settings_file.read_text()) if settings_file.exists() else {}
        settings.update({"update.mode": "none", "extensions.autoUpdate": False, "extensions.autoCheckUpdates": False,
                         "telemetry.telemetryLevel": "off", "workbench.enableExperiments": False,
                         "git.autofetch": False, "git.path": str(TOOLS / ("git/cmd/git.exe" if WINDOWS else "bin/git")),
                         "editor.inlineSuggest.enabled": False, "github.copilot.enable": {"*": False}, "chat.commandCenter.enabled": False,
                         "chat.disableAIFeatures": True})

        # Pre-configuracao da conexao no SQLTools
        connections = settings.get("sqltools.connections", [])
        if not any(c.get("name") == "MariaDB - Aulas" for c in connections):
            connections.append({
                "name": "MariaDB - Aulas",
                "dialect": "MySQL",
                "server": "127.0.0.1",
                "port": PORT,
                "database": "aulas",
                "username": "aluno",
                "password": "aluno",
                "connectString": f"mysql://aluno:aluno@127.0.0.1:{PORT}/aulas",
                "isActive": True
            })
            settings["sqltools.connections"] = connections

        # O kit nao inclui Node.js: o SQLTools deve usar o runtime do proprio VS Code
        settings["sqltools.useNodeRuntime"] = False

        # Configuracoes especificas das linguagens presentes
        php_exe = TOOLS / ("php/php.exe" if WINDOWS else "bin/php")
        if php_exe.exists():
            settings["php.validate.executablePath"] = str(self.php)
            settings["intelephense.environment.phpVersion"] = "8.4"

        jdk_dir = TOOLS / "jdk"
        if jdk_dir.exists():
            settings["java.jdt.ls.java.home"] = str(jdk_dir)
            settings["java.configuration.runtimes"] = [{"name": "JavaSE-25", "path": str(jdk_dir), "default": True}]
            settings["java.import.maven.enabled"] = False
            settings["java.import.gradle.enabled"] = False
            settings["java.autobuild.enabled"] = False
            settings["java.jdt.ls.vmargs"] = "-Xmx512m -Xms64m"

        req = ROOT / "dependencias/python/requirements.txt"
        if req.exists() or (ROOT / "projetos/python").exists():
            settings["python.defaultInterpreterPath"] = str(self.python)
            settings["python.analysis.extraPaths"] = [str(STATE / "python-packages")]
            settings["python.terminal.activateEnvironment"] = False
            settings["python.experiments.enabled"] = False

        settings_file.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
        code = TOOLS / ("vscode/Code.exe" if WINDOWS else "vscode/code")
        subprocess.Popen([str(code), "--new-window", str(ROOT / "aulas.code-workspace")], env=self.env, cwd=ROOT)
        print("✅ Editor de código aberto! Aguarde o VS Code carregar.")
        print("   ⚠️  Se o Linux bloquear o sandbox, consulte LEIA-ME.html.")

    def terminal(self):
        self.start()
        self.packages()
        print("💻 Terminal do kit aberto. Use 'exit' para voltar ao menu.")
        print("   Git: configure nome e e-mail nesta cópia antes de usar.")
        proj_dir = ROOT / "projetos"
        run([os.environ.get("COMSPEC", "cmd.exe")] if WINDOWS else ["bash", "--noprofile", "--norc"], cwd=proj_dir, env=self.env)

    def git(self, *args, **kwargs):
        return run([TOOLS / ("git/cmd/git.exe" if WINDOWS else "bin/git"), *args], env=self.env, **kwargs)

    def doctor(self):
        print("🔍 Verificando ferramentas do laboratório...\n")
        checks = [("MariaDB", [self.dbexe("mariadbd"), "--no-defaults", "--version"])]

        req = ROOT / "dependencias/python/requirements.txt"
        if req.exists():
            checks.append(("Python/pip", [self.python, "-m", "pip", "--version"]))
        elif self.python.exists():
            checks.append(("Python (Runtime)", [self.python, "--version"]))

        jdk_javac = TOOLS / ("jdk/bin/javac.exe" if WINDOWS else "jdk/bin/javac")
        if jdk_javac.exists():
            checks.append(("Java", [jdk_javac, "-version"]))

        php_exe = TOOLS / ("php/php.exe" if WINDOWS else "bin/php")
        if php_exe.exists():
            checks.append(("PHP", [self.php, "-r", "if (!extension_loaded('pdo_mysql') || !extension_loaded('openssl') || !extension_loaded('zip')) { exit(1); } echo PHP_VERSION, PHP_EOL;"]))
            composer_phar = ROOT / "dependencias/composer/composer.phar"
            if composer_phar.exists():
                checks.append(("Composer", [self.php, composer_phar, "--version"]))
        failures = []
        for name, args in checks:
            try:
                run(args, env=self.dbenv() if name == "MariaDB" else self.env, timeout=25)
                print(f"  ✅ {name}")
            except (subprocess.SubprocessError, OSError) as exc:
                failures.append(name)
                print(f"  ❌ {name} — {exc}")
        try:
            with tempfile.TemporaryDirectory(dir=STATE) as folder:
                self.git("init", folder, capture_output=True)
                Path(folder, "arquivo.txt").write_text("aula\n")
                self.git("-C", folder, "add", ".", capture_output=True)
                self.git("-C", folder, "-c", "user.name=Diagnostico", "-c", "user.email=teste@localhost", "commit", "-m", "teste offline", capture_output=True)
                self.git("-C", folder, "bundle", "create", "teste.bundle", "--all", capture_output=True)
                self.git("-C", folder, "bundle", "verify", "teste.bundle", capture_output=True)
            print("  ✅ Git (init/add/commit/bundle)")
        except (subprocess.SubprocessError, OSError) as exc:
            failures.append("Git")
            print(f"  ❌ Git — {exc}")
        if failures:
            raise RuntimeError("Componentes com falha: " + ", ".join(failures))
        print("\n✅ Todas as ferramentas estão funcionando corretamente!")
        print("   💡 Valide também o VS Code e a conexão com o banco com a rede desconectada.")

    def backup(self):
        if not self.owns_server():
            raise RuntimeError("Inicie o MariaDB deste kit antes de exportar.")
        folder = ROOT / "backups"
        folder.mkdir(exist_ok=True)
        dest = folder / ("aulas-" + TARGET + "-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".sql")
        part = dest.with_suffix(".sql.part")
        try:
            with part.open("wb") as f:
                run([self.dbexe("mariadb-dump"), "--defaults-file=" + str(self.client), "--single-transaction", "--routines", "--events", "--databases", "aulas"], stdout=f, env=self.dbenv())
            part.replace(dest)
        except Exception:
            part.unlink(missing_ok=True)
            raise
        print(f"💾 Cópia de segurança salva em: {dest}")
        return dest

    def restore(self, path):
        if not path.is_file():
            raise RuntimeError("Arquivo SQL nao encontrado: " + str(path))
        self.start()
        print("⚠️  Esta ação vai substituir os dados do banco de dados.")
        print("   Uma cópia de segurança será feita automaticamente.")
        resp = input("\nDeseja continuar? (S/N): ").strip().upper()
        if resp not in ("S", "SIM"):
            print("❌ Importação cancelada.")
            return
        self.backup()
        with path.open("rb") as f:
            run([self.dbexe("mariadb"), "--defaults-file=" + str(self.client)], stdin=f, env=self.dbenv())
        print("✅ Dados importados com sucesso!")

    def ajuda(self):
        """Exibe ajuda contextual detalhada."""
        print("""
╔══════════════════════════════════════════════════════════════╗
║  ❓ AJUDA DO LABORATÓRIO                                     ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  O que cada opção faz:                                       ║
║                                                              ║
║  1  📝 Abrir editor de código                                ║
║     Abre o VS Code sem o banco de dados.                     ║
║     Use quando a aula não precisa de banco.                  ║
║                                                              ║
║  2  📝 Abrir editor + banco de dados                         ║
║     Abre o VS Code e liga o banco de dados automaticamente.  ║
║     Use quando a aula usa banco de dados.                    ║
║                                                              ║
║  3  💻 Abrir terminal                                        ║
║     Abre um terminal com todas as ferramentas disponíveis    ║
║     (PHP, Python, Java, Git, Composer).                      ║
║     Use para executar comandos ou scripts.                   ║
║                                                              ║
║  4  🔍 Verificar ferramentas                                 ║
║     Testa se todas as ferramentas estão funcionando.         ║
║     Use se algo não estiver certo.                           ║
║                                                              ║
║  5  💾 Salvar cópia do banco                                 ║
║     Salva uma cópia de segurança do banco de dados.          ║
║     Use para não perder seus dados.                          ║
║                                                              ║
║  6  ⏹️  Parar banco de dados                                 ║
║     Desliga o banco de dados com segurança.                  ║
║     Use antes de copiar a pasta ou remover o pendrive.       ║
║     Um backup automático é feito antes de encerrar.          ║
║                                                              ║
║  7  ❓ Ajuda (esta tela)                                     ║
║                                                              ║
║  0  🚪 Sair                                                  ║
║     Sai do laboratório e encerra o banco de dados.           ║
║                                                              ║
╠══════════════════════════════════════════════════════════════╣
║  ⌨️  ATALHOS ÚTEIS                                          ║
║                                                              ║
║  Ctrl+C    - Para o servidor web ou interrompe uma ação      ║
║  exit      - Sai do terminal e volta ao menu                 ║
║                                                              ║
║  💡 Quer saber mais? Abra o arquivo BEM-VINDO.html           ║
║     no navegador para ver instruções visuais.                ║
║     O guia completo está em LEIA-ME.html.                    ║
╚══════════════════════════════════════════════════════════════╝
""")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("acao", nargs="?", default="menu", choices=["menu", "abrir", "terminal", "iniciar", "parar", "diagnostico", "backup", "importar", "web"])
    parser.add_argument("arquivo", nargs="?")
    args = parser.parse_args()
    lab = Lab()
    actions = {"abrir": lab.editor, "terminal": lab.terminal, "iniciar": lab.start, "parar": lab.stop,
               "diagnostico": lab.doctor, "backup": lab.backup}
    if args.acao == "importar":
        if not args.arquivo:
            parser.error("importar exige o caminho de um arquivo SQL")
        lab.restore(Path(args.arquivo).resolve())
    elif args.acao == "web":
        lab.start()
        print("🌐 Servidor web iniciado! Abra http://127.0.0.1:8080 no navegador.")
        print("   Ctrl+C para encerrar o servidor.")
        web_root = ROOT / "projetos/web" if (ROOT / "projetos/web").exists() else ROOT / "projetos/php"
        command = [lab.php, "-S", "127.0.0.1:8080", "-t", web_root] if WINDOWS else [TOOLS / "php/frankenphp", "php-server", "--listen", "127.0.0.1:8080", "--root", web_root]
        run(command, env=lab.env)
    elif args.acao != "menu":
        actions[args.acao]()
    else:
        choices = {"1": lab.editor, "2": lambda: lab.editor(com_banco=True), "3": lab.terminal,
                   "4": lab.doctor, "5": lab.backup, "6": lab.stop, "7": lab.ajuda}
        while True:
            print("""
╔════════════════════════════════════════════════════╗
║  🧪 LABORATÓRIO DE PROGRAMAÇÃO                     ║
╠════════════════════════════════════════════════════╣
║                                                    ║
║  1  📝 Abrir editor de código                      ║
║  2  📝 Abrir editor + banco de dados               ║
║  3  💻 Abrir terminal                              ║
║  4  🔍 Verificar ferramentas                       ║
║  5  💾 Salvar cópia do banco                       ║
║  6  ⏹️  Parar banco de dados                       ║
║  7  ❓ Ajuda                                       ║
║  0  🚪 Sair                                        ║
║                                                    ║
╚════════════════════════════════════════════════════╝""")
            choice = input("\n👉 Escolha uma opção: ").strip()
            try:
                if choice == "0":
                    lab.stop()
                    print("\n👋 Até logo! Lembre-se de fazer backup antes de copiar a pasta.")
                    return
                action = choices.get(choice)
                if action:
                    action()
                else:
                    print("⚠️  Opção inválida. Tente novamente.")
            except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
                msg = friendly_error(exc)
                print(f"❌ {msg}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️  Operação interrompida.")
        print("   Use a opção 'Parar banco de dados' para encerrar com segurança.")
        sys.exit(130)
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        msg = friendly_error(exc)
        print(f"❌ {msg}", file=sys.stderr)
        sys.exit(1)

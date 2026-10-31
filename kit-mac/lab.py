#!/usr/bin/env python3
"""Painel de controle do laboratório no macOS (kit-mac)."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
PORT = 3307


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


class MacLab:
    def __init__(self):
        self.state = ROOT / "estado"
        self.state.mkdir(exist_ok=True)
        self.mariadb_pid = self.state / "mariadb.pid"

    def is_db_running(self):
        if not self.mariadb_pid.exists():
            return False
        try:
            pid = int(self.mariadb_pid.read_text().strip())
            os.kill(pid, 0)
            return True
        except (ValueError, OSError):
            return False

    def start_db(self):
        if self.is_db_running():
            print(f"✅ MariaDB já está em execução na porta {PORT}.")
            return
        run([ROOT / "iniciar-mariadb.sh"])

    def stop_db(self):
        if not self.is_db_running():
            print("⏹️  MariaDB já está parado.")
            return
        run([ROOT / "parar-mariadb.sh"])

    def backup_db(self):
        if not self.is_db_running():
            print("⚠️  Iniciando MariaDB para realizar o backup...")
            self.start_db()
        run([ROOT / "backup-mariadb.sh", "aulas"])

    def open_editor(self, with_db=False):
        if with_db:
            self.start_db()
        print("""
Qual workspace deseja abrir no VS Code?
  [1] Web (PHP 8.5 & MariaDB)
  [2] POO Python (CPython 3.13 & MariaDB)
  [3] POO Java (Adoptium JDK 25 & MariaDB)""")
        choice = input("\n👉 Escolha (1-3) [1]: ").strip()
        ws_map = {
            "1": "web.code-workspace",
            "2": "poo-python.code-workspace",
            "3": "poo-java.code-workspace",
            "": "web.code-workspace"
        }
        ws_file = ROOT / ws_map.get(choice, "web.code-workspace")
        if shutil.which("code"):
            subprocess.Popen(["code", str(ws_file)], cwd=ROOT)
            print(f"✅ VS Code aberto com o workspace '{ws_file.name}'!")
        else:
            print(f"❌ Comando 'code' não encontrado no PATH. Abra manualmente: {ws_file}")

    def open_terminal(self):
        self.start_db()
        print("💻 Abrindo terminal com variáveis do kit carregadas...")
        env = os.environ.copy()
        env["DB_HOST"] = "127.0.0.1"
        env["DB_PORT"] = str(PORT)
        env["DB_NAME"] = "aulas"
        env["DB_USER"] = "aluno"
        env["DB_PASSWORD"] = "aluno"
        run(["zsh", "-l"], cwd=ROOT / "projetos", env=env)

    def doctor(self):
        print("🔍 Verificando ferramentas no macOS (Homebrew)...\n")
        checks = [
            ("Homebrew", ["brew", "--version"]),
            ("PHP", ["php", "-v"]),
            ("Composer", ["composer", "--version"]),
            ("Python 3.13", ["python3.13", "--version"]),
            ("PyMySQL", ["python3.13", "-c", "import pymysql; print('PyMySQL OK')"]),
            ("Java 25", ["javac", "-version"]),
            ("MariaDB Driver (JDBC)", ["test", "-f", str(ROOT / "dependencias/java/mariadb-java-client.jar")])
        ]
        failures = []
        for name, cmd in checks:
            try:
                subprocess.run(cmd, capture_output=True, check=True)
                print(f"  ✅ {name}")
            except (subprocess.SubprocessError, OSError, FileNotFoundError) as e:
                failures.append(name)
                print(f"  ❌ {name} — {e}")

        if self.is_db_running():
            print("  ✅ MariaDB (ativo na porta 3307)")
        else:
            print("  ℹ️  MariaDB (parado - use a opção 2 ou 'iniciar' para ligar)")

        if failures:
            print(f"\n⚠️  Componentes com aviso: {', '.join(failures)}")
            print("   Execute ./configurar.sh para instalar ou atualizar dependências.")
        else:
            print("\n🎉 Todas as ferramentas estão disponíveis e configuradas no Mac!")

    def ajuda(self):
        print("""
╔══════════════════════════════════════════════════════════════╗
║  ❓ AJUDA DO LABORATÓRIO (MACOS)                             ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  1  📝 Abrir editor (sem banco)                              ║
║     Escolha entre Web, Python ou Java no VS Code.            ║
║                                                              ║
║  2  📝 Abrir editor + banco de dados                         ║
║     Liga o MariaDB (127.0.0.1:3307) e abre o VS Code.        ║
║                                                              ║
║  3  💻 Abrir terminal                                        ║
║     Terminal do Mac com PATH e variáveis de banco prontas.   ║
║                                                              ║
║  4  🔍 Verificar ferramentas                                 ║
║     Testa se PHP, Java, Python, MariaDB e JDBC estão ok.     ║
║                                                              ║
║  5  💾 Salvar cópia do banco (backup)                        ║
║     Gera um dump SQL do banco "aulas" em kit-mac/backups/.   ║
║                                                              ║
║  6  ⏹️  Parar banco de dados                                 ║
║     Desliga o processo MariaDB local com segurança.          ║
║                                                              ║
║  0  🚪 Sair                                                  ║
║     Encerra o banco de dados e sai do painel.                ║
║                                                              ║
║  💡 Credenciais do MariaDB:                                  ║
║     Host: 127.0.0.1 | Porta: 3307 | Banco: aulas             ║
║     Aluno: aluno / aluno | Admin: root / root                ║
╚══════════════════════════════════════════════════════════════╝""")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("acao", nargs="?", default="menu", choices=["menu", "abrir", "terminal", "iniciar", "parar", "diagnostico", "backup"])
    args = parser.parse_args()
    lab = MacLab()

    if args.acao == "iniciar":
        lab.start_db()
    elif args.acao == "parar":
        lab.stop_db()
    elif args.acao == "backup":
        lab.backup_db()
    elif args.acao == "diagnostico":
        lab.doctor()
    elif args.acao == "terminal":
        lab.open_terminal()
    elif args.acao == "abrir":
        lab.open_editor(with_db=True)
    else:
        while True:
            print("""
╔════════════════════════════════════════════════════╗
║  🍎 LABORATÓRIO DO PROFESSOR (MACOS)               ║
╠════════════════════════════════════════════════════╣
║                                                    ║
║  1  📝 Abrir editor de código                      ║
║  2  📝 Abrir editor + banco de dados               ║
║  3  💻 Abrir terminal                              ║
║  4  🔍 Verificar ferramentas                       ║
║  5  💾 Salvar cópia do banco (backup)              ║
║  6  ⏹️  Parar banco de dados                       ║
║  7  ❓ Ajuda                                       ║
║  0  🚪 Sair                                        ║
║                                                    ║
╚════════════════════════════════════════════════════╝""")
            choice = input("\n👉 Escolha uma opção: ").strip()
            if choice == "0":
                lab.stop_db()
                print("\n👋 Até logo!")
                return
            elif choice == "1":
                lab.open_editor(with_db=False)
            elif choice == "2":
                lab.open_editor(with_db=True)
            elif choice == "3":
                lab.open_terminal()
            elif choice == "4":
                lab.doctor()
            elif choice == "5":
                lab.backup_db()
            elif choice == "6":
                lab.stop_db()
            elif choice == "7":
                lab.ajuda()
            else:
                print("⚠️  Opção inválida. Tente novamente.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Painel de controle do laboratório no macOS (kit-mac) com suporte a SQLite."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


class MacLab:
    def __init__(self):
        self.state = ROOT / "estado"
        self.state.mkdir(exist_ok=True)

    def open_editor(self):
        print("""
Qual workspace deseja abrir no VS Code?
  [1] Web (PHP 8.5 & SQLite)
  [2] POO Python (CPython 3.13 & SQLite)
  [3] POO Java (Adoptium JDK 25 & SQLite)
  [4] Todos os projetos""")
        choice = input("👉 Escolha (1-4) [1]: ").strip()
        workspaces = {
            "1": ROOT / "web.code-workspace",
            "2": ROOT / "poo-python.code-workspace",
            "3": ROOT / "poo-java.code-workspace",
            "4": ROOT / "projetos"
        }
        target = workspaces.get(choice, ROOT / "web.code-workspace")
        print(f"🚀 Abrindo VS Code: {target.name}...")
        subprocess.Popen(["code", str(target)])

    def backup_projects(self):
        folder = ROOT / "backups"
        folder.mkdir(exist_ok=True)
        dest = folder / ("mac-projetos-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".zip")
        part = dest.with_suffix(".zip.part")
        try:
            with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as zf:
                for p in (ROOT / "projetos").rglob("*"):
                    if p.is_file():
                        arcname = p.relative_to(ROOT)
                        zf.write(p, str(arcname))
            part.replace(dest)
            print(f"💾 Cópia de segurança criada em: {dest}")
        except Exception as e:
            part.unlink(missing_ok=True)
            print(f"❌ Falha no backup: {e}")

    def doctor(self):
        print("\n🔍 Verificando ambiente macOS (kit-mac)...\n")
        checks = [
            ("Git", ["git", "--version"]),
            ("Python", ["python3", "--version"]),
            ("PHP", ["php", "-v"]),
            ("Composer", ["composer", "--version"]),
            ("Java JDK", ["javac", "--version"]),
            ("VS Code", ["code", "--version"]),
        ]
        failures = 0
        for name, cmd in checks:
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, check=True)
                ver = res.stdout.strip().splitlines()[0]
                print(f"  ✅ {name:<12}: {ver}")
            except Exception as e:
                print(f"  ❌ {name:<12}: {e}")
                failures += 1

        # Verificar SQLite nativo
        try:
            with sqlite3.connect(":memory:") as conn:
                conn.execute("CREATE TABLE t (id INT);")
            print("  ✅ SQLite      : Driver nativo operacional")
        except Exception as e:
            print(f"  ❌ SQLite      : {e}")
            failures += 1

        # Verificar banco.db nos projetos
        for p in (ROOT / "projetos").glob("*/banco.db"):
            try:
                with sqlite3.connect(p) as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT count(*) FROM sqlite_master WHERE type='table';")
                    qtd = cur.fetchone()[0]
                print(f"  ✅ Banco SQLite: {p.relative_to(ROOT)} ({qtd} tabelas)")
            except Exception as e:
                print(f"  ❌ Banco SQLite: {p} — {e}")
                failures += 1

        if failures == 0:
            print("\n🎉 Ambiente macOS 100% configurado e pronto para aulas com SQLite!")
        else:
            print(f"\n⚠️  {failures} ferramenta(s) precisam de atenção.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("acao", nargs="?", default="menu", choices=["menu", "editor", "backup", "doctor"])
    args = parser.parse_args()
    lab = MacLab()

    if args.acao == "editor":
        lab.open_editor()
    elif args.acao == "backup":
        lab.backup_projects()
    elif args.acao == "doctor":
        lab.doctor()
    else:
        while True:
            print("""
╔════════════════════════════════════════════════════╗
║  🍏 LABORATÓRIO MAC (PROFESSOR)                    ║
╠════════════════════════════════════════════════════╣
║                                                    ║
║  1  📝 Abrir VS Code (escolher disciplina)         ║
║  2  💾 Fazer backup dos projetos                   ║
║  3  🔍 Verificar ferramentas (Doctor)              ║
║  0  🚪 Sair                                        ║
║                                                    ║
╚════════════════════════════════════════════════════╝""")
            choice = input("\n👉 Escolha uma opção: ").strip()
            if choice == "1":
                lab.open_editor()
            elif choice == "2":
                lab.backup_projects()
            elif choice == "3":
                lab.doctor()
            elif choice == "0":
                print("\n👋 Até logo!")
                break
            else:
                print("⚠️  Opção inválida.")


if __name__ == "__main__":
    main()

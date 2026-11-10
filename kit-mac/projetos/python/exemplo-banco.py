# ==============================================================
# 🗄️ Demonstração de Banco de Dados SQLite em Python
# ==============================================================
# Como executar:
# - No VS Code: Pressione F5
# - No terminal: python exemplo-banco.py
# ==============================================================

from pathlib import Path
import sqlite3

def main():
    print("🚀 Laboratório Python (POO): CPython + SQLite")
    db_path = Path(__file__).resolve().parent / "banco.db"
    
    if not db_path.exists():
        print(f"⚠️ Banco de dados não encontrado em: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome, matricula, curso FROM alunos ORDER BY id ASC")
    alunos = cursor.fetchall()

    print("\n✓ Conexão com SQLite realizada com sucesso!")
    print("-" * 55)
    print(f"{'ID':<4} | {'Nome':<15} | {'Matrícula':<10} | {'Curso'}")
    print("-" * 55)
    for a in alunos:
        print(f"{a[0]:<4} | {a[1]:<15} | {a[2]:<10} | {a[3]}")
    print("-" * 55)
    conn.close()

if __name__ == "__main__":
    main()

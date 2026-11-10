📁 Projetos Python (POO)

Nesta pasta você cria seus scripts e classes Python (.py).

Exemplos incluídos:
  1. ola-mundo.py     - Primeiro programa simples em Python (Olá, mundo!)
  2. exemplo-banco.py - Demonstração de conexão e consulta com o banco SQLite

Como executar:
  Opção 1: No VS Code, abra o arquivo e pressione F5 (ou use o botão "Run" no canto superior).
  Opção 2: No terminal do kit, execute:
    python ola-mundo.py
    python exemplo-banco.py

Banco de Dados SQLite:
  Arquivo: banco.db (localizado nesta mesma pasta)
  No VS Code: Basta clicar no arquivo banco.db para abrir o SQLite Viewer integrado!
  Conexão em Python:
    import sqlite3
    conn = sqlite3.connect("banco.db")

📁 Projetos Web (PHP & HTML)

Nesta pasta você cria seus arquivos para a aula de desenvolvimento web (.php, .html, .css).

Exemplos incluídos:
  1. ola-mundo.php      - Primeiro programa simples em PHP (Olá, mundo!)
  2. exemplo-banco.php  - Demonstração de conexão e consulta com o banco SQLite
  3. index.php          - Página inicial padrão que carrega o ola-mundo.php

Como testar no navegador:
  Opção 1 (Mais fácil):
    No VS Code, use o menu Terminal -> Run Task (ou Ctrl+Shift+B)
    e escolha "🌐 Iniciar Servidor Web PHP".
    
  Opção 2 (Via Terminal do Kit):
    Abra o terminal e execute:
      php -S 127.0.0.1:8080 -t .
      
  Depois acesse no seu navegador:
    http://127.0.0.1:8080/ola-mundo.php
    http://127.0.0.1:8080/exemplo-banco.php

Banco de Dados SQLite:
  Arquivo: banco.db (localizado nesta mesma pasta)
  No VS Code: Basta clicar no arquivo banco.db para abrir o SQLite Viewer integrado!
  Conexão em PHP:
    $pdo = new PDO("sqlite:" . __DIR__ . "/banco.db");

📁 Projetos Web (PHP & HTML)

Nesta pasta você cria seus arquivos para a aula de desenvolvimento web (.php, .html, .css).

Como testar no navegador:
  Opção 1 (Mais fácil):
    No VS Code, use o menu Terminal -> Run Task (ou Ctrl+Shift+B)
    e escolha "🌐 Iniciar Servidor Web PHP".
    
  Opção 2 (Via Terminal do Kit):
    Abra o terminal e execute:
      php -S 127.0.0.1:8080 -t .
      
  Depois acesse no seu navegador: http://127.0.0.1:8080/ola-mundo.php

Banco de Dados SQLite:
  Arquivo: banco.db (localizado nesta mesma pasta)
  Conexão no VS Code: Já conectada automaticamente na barra lateral (ícone SQLTools)!
  Conexão em PHP:
    $pdo = new PDO("sqlite:" . __DIR__ . "/banco.db");

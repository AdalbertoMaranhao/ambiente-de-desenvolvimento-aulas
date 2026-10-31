<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>Laboratório Web — Olá Mundo</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 3rem; background: #f8fafc; color: #1e293b; }
    .card { background: white; padding: 2rem; border-radius: 8px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); max-width: 600px; margin: auto; }
    h1 { color: #0284c7; margin-top: 0; }
  </style>
</head>
<body>
  <div class="card">
    <h1>🚀 Olá, Mundo PHP!</h1>
    <p><?php echo "Seu ambiente de desenvolvimento web está funcionando perfeitamente!"; ?></p>
    <p><small>Horário do servidor: <?php echo date("d/m/Y H:i:s"); ?></small></p>
  </div>
</body>
</html>

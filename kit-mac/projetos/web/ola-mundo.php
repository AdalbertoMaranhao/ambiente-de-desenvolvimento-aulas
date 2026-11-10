<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>Olá, mundo! — Laboratório Web</title>
  <style>
    body { font-family: system-ui, -apple-system, sans-serif; margin: 3rem; background: #f8fafc; color: #1e293b; text-align: center; }
    .card { background: white; padding: 2.5rem; border-radius: 12px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); max-width: 520px; margin: auto; }
    h1 { color: #0284c7; margin-top: 0; }
    p { font-size: 1.1rem; line-height: 1.6; }
    .badge { display: inline-block; background: #dcfce7; color: #166534; padding: 0.35rem 0.75rem; border-radius: 9999px; font-size: 0.9rem; font-weight: 600; }
    .link-banco { display: inline-block; margin-top: 1.5rem; color: #0284c7; text-decoration: none; font-weight: 600; font-size: 1rem; }
    .link-banco:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <div class="card">
    <h1>👋 <?php echo "Olá, mundo!"; ?></h1>
    <p>Seu primeiro programa em PHP está rodando no laboratório portátil!</p>
    <p><span class="badge">✓ Servidor PHP ativo</span></p>
    <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 1.5rem 0;">
    <p style="margin-bottom: 0.5rem; color: #64748b;">Próximo passo:</p>
    <a class="link-banco" href="exemplo-banco.php">Ver demonstração com Banco SQLite →</a>
  </div>
</body>
</html>

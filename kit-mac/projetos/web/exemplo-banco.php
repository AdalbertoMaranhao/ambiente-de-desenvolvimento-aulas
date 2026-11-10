<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>Laboratório Web — Demonstração com SQLite</title>
  <style>
    body { font-family: system-ui, -apple-system, sans-serif; margin: 3rem; background: #f8fafc; color: #1e293b; }
    .card { background: white; padding: 2rem; border-radius: 12px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); max-width: 650px; margin: auto; }
    h1 { color: #0284c7; margin-top: 0; }
    table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
    th, td { text-align: left; padding: 0.75rem; border-bottom: 1px solid #e2e8f0; }
    th { background: #f1f5f9; color: #475569; font-weight: 600; }
    .badge { display: inline-block; background: #dcfce7; color: #166534; padding: 0.25rem 0.5rem; border-radius: 9999px; font-size: 0.85rem; font-weight: 600; }
    .footer { margin-top: 1.5rem; font-size: 0.85rem; color: #64748b; }
    .voltar { display: inline-block; margin-bottom: 1rem; color: #0284c7; text-decoration: none; font-weight: 500; }
    .voltar:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <div class="card">
    <a class="voltar" href="ola-mundo.php">← Voltar ao Olá Mundo</a>
    <h1>🚀 Laboratório Web: PHP + SQLite</h1>
    <p>Demonstração de consulta ao arquivo <code>banco.db</code> compartilhado:</p>

    <?php
    $dbPath = __DIR__ . '/banco.db';
    try {
        $pdo = new PDO("sqlite:" . $dbPath);
        $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
        
        $stmt = $pdo->query("SELECT id, nome, matricula, curso FROM alunos ORDER BY id ASC");
        $alunos = $stmt->fetchAll(PDO::FETCH_ASSOC);
        
        echo "<p><span class='badge'>✓ Conexão com SQLite estabelecida com sucesso</span></p>";
        echo "<table>";
        echo "<thead><tr><th>ID</th><th>Nome</th><th>Matrícula</th><th>Curso</th></tr></thead><tbody>";
        foreach ($alunos as $aluno) {
            echo "<tr>";
            echo "<td>" . htmlspecialchars($aluno['id']) . "</td>";
            echo "<td>" . htmlspecialchars($aluno['nome']) . "</td>";
            echo "<td>" . htmlspecialchars($aluno['matricula']) . "</td>";
            echo "<td>" . htmlspecialchars($aluno['curso']) . "</td>";
            echo "</tr>";
        }
        echo "</tbody></table>";
    } catch (Exception $e) {
        echo "<p style='color: #dc2626;'><strong>Erro ao acessar banco:</strong> " . htmlspecialchars($e->getMessage()) . "</p>";
    }
    ?>

    <div class="footer">
      <p>💡 <em>O arquivo <code>banco.db</code> é compartilhado entre Windows e Linux sem necessidade de exportar ou importar dados.</em></p>
      <p><small>Horário do servidor: <?php echo date("d/m/Y H:i:s"); ?></small></p>
    </div>
  </div>
</body>
</html>

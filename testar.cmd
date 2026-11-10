@echo off
setlocal
echo 🧪 Executando suite de testes unitarios...
python -m unittest discover -s tests -v
if errorlevel 1 (
    echo ❌ Falha nos testes unitarios.
    exit /b 1
)

if exist dist (
    echo.
    echo 🔍 Executando inspecao estatica dos pacotes em dist...
    python verificar_pacote.py
    if errorlevel 1 (
        echo ❌ Falha na inspecao de pacotes.
        exit /b 1
    )
)

echo.
echo ✅ Todos os testes e validacoes foram concluidos com sucesso!
endlocal

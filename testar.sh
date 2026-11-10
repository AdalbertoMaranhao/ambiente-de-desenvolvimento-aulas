#!/bin/sh
set -e
echo "🧪 Executando suíte de testes unitários..."
python3 -m unittest discover -s tests -v

if [ -d "dist" ]; then
    printf '\n🔍 Executando inspeção estática dos pacotes em dist/...\n'
    python3 verificar_pacote.py
fi

printf '\n✅ Todos os testes e validações foram concluídos com sucesso!\n'

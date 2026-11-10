#!/bin/sh
# Verifica a compatibilidade do sistema antes de usar o laboratório
# Execute este script antes de copiar o kit do pendrive

PASS=0
FAIL=0

check() {
    NAME="$1"
    RESULT="$2"
    if [ "$RESULT" = "0" ]; then
        echo "  ✅ $3"
        PASS=$((PASS + 1))
    else
        echo "  ❌ $3"
        FAIL=$((FAIL + 1))
    fi
}

echo "🔍 Verificando seu computador..."
echo ""

# Sistema
ARCH=$(uname -m 2>/dev/null)
if [ "$ARCH" = "x86_64" ]; then
    check "arch" "0" "Sistema: Linux x64 (compatível)"
else
    check "arch" "1" "Arquitetura: $ARCH (requer x86_64)"
fi

# Kernel
KERNEL=$(uname -r 2>/dev/null | cut -d. -f1)
if [ "$KERNEL" -ge 4 ] 2>/dev/null; then
    check "kernel" "0" "Kernel: $(uname -r) (mínimo: 4.x)"
else
    check "kernel" "1" "Kernel: $(uname -r) (mínimo: 4.x)"
fi

# Memória
MEM_TOTAL=$(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print int($2/1024)}')
if [ -n "$MEM_TOTAL" ] && [ "$MEM_TOTAL" -ge 4096 ] 2>/dev/null; then
    check "mem" "0" "Memória: $((MEM_TOTAL / 1024)) GB disponíveis (mínimo: 4 GB)"
else
    check "mem" "1" "Memória: ${MEM_TOTAL}MB (mínimo: 4 GB)"
fi

# Espaço em disco
DISK_FREE=$(df -BG . 2>/dev/null | tail -1 | awk '{gsub(/G/,"",$4); print $4}')
if [ -n "$DISK_FREE" ] && [ "$DISK_FREE" -ge 5 ] 2>/dev/null; then
    check "disk" "0" "Espaço em disco: ${DISK_FREE}GB livres (mínimo: 5 GB)"
else
    check "disk" "1" "Espaço em disco: ${DISK_FREE}GB livres (mínimo: 5 GB)"
fi

# Python 3 (opcional, o kit já inclui)
echo ""
echo "ℹ️  Observações:"
echo "  - O laboratório inclui Python 3 próprio, não depende do sistema"
echo "  - O kit funciona sem conexão com internet"
echo ""

if [ "$FAIL" -eq 0 ]; then
    echo "🎉 Seu computador é compatível com o laboratório!"
    echo ""
    echo "Para iniciar:"
    echo "  1. Extraia o kit no pendrive ou copie a pasta para o seu computador"
    echo "  2. Clique duas vezes em Iniciar <Disciplina>.desktop"
    echo "     ou abra um terminal e execute: sh iniciar-linux.sh"
else
    echo "⚠️  Foram encontrados $FAIL problema(s) de compatibilidade."
    echo "    Consulte o professor antes de usar o laboratório."
fi

echo ""
echo "Total: $PASS aprovado(s), $FAIL falha(s)"
exit "$FAIL"

#!/usr/bin/env sh
# gravar-pendrive.sh — Lançador rápido do gravador de pendrive para Linux e macOS

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Se python3 estiver disponível, executa o utilitário completo com interface rica
if command -v python3 >/dev/null 2>&1; then
    exec python3 "$SCRIPT_DIR/gravar_pendrive.py" "$@"
fi

# Fallback se python3 não estiver instalado no sistema
echo "================================================================="
echo "  🚀 Gravador de Pendrive do Laboratório Portátil"
echo "================================================================="
echo

if [ ! -d "$SCRIPT_DIR/dist" ]; then
    echo "❌ Pasta dist não encontrada. Baixe ou monte os kits antes de gravar."
    exit 1
fi

echo "Pacotes disponíveis em dist/:"
kits=$(ls "$SCRIPT_DIR/dist"/kit-*.zip 2>/dev/null)
if [ -z "$kits" ]; then
    echo "❌ Nenhum arquivo kit-*.zip encontrado em dist/."
    exit 1
fi

i=1
for k in $kits; do
    echo "  [$i] $(basename "$k")"
    eval "pkg_$i=\"$k\""
    i=$((i + 1))
done

printf "\nEscolha o kit [1-%d]: " $((i - 1))
read -r escolha

eval "SELECIONADO=\"\$pkg_$escolha\""
if [ -z "$SELECIONADO" ] || [ ! -f "$SELECIONADO" ]; then
    echo "❌ Opção inválida."
    exit 1
fi

echo
printf "Digite o caminho do pendrive montado (ex: /Volumes/MEUPENDRIVE ou /media/$USER/AULAS): "
read -r destino

if [ ! -d "$destino" ]; then
    echo "❌ Caminho não encontrado: $destino"
    exit 1
fi

echo
echo "================================================================="
echo "  Origem  : $(basename "$SELECIONADO")"
echo "  Destino : $destino"
echo "================================================================="
printf "Confirmar a gravação no pendrive? [S/n]: "
read -r confirma
if [ "$confirma" = "n" ] || [ "$confirma" = "N" ]; then
    echo "Operação cancelada."
    exit 0
fi

echo
echo "⚡ Extraindo em alta velocidade..."
if command -v tar >/dev/null 2>&1 && tar -tf "$SELECIONADO" >/dev/null 2>&1; then
    tar -xf "$SELECIONADO" --strip-components=1 -C "$destino"
else
    unzip -q -o "$SELECIONADO" -d "$destino"
fi

if [ -f "$destino/iniciar-linux.sh" ]; then
    chmod +x "$destino/iniciar-linux.sh" 2>/dev/null || true
fi

echo
echo "================================================================="
echo "  🎉 Pendrive gravado e pronto para a aula com sucesso!"
echo "================================================================="
echo

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
echo "  💡 Dica: O sistema de arquivos ideal é exFAT (cluster 128 KB)."
echo "  Ele grava até 3x mais rápido e funciona em Windows, Mac e Linux."
echo "================================================================="
printf "Deseja formatar a unidade (%s) em exFAT antes de gravar? [s/N]: " "$destino"
read -r opt_fmt
if [ "$opt_fmt" = "s" ] || [ "$opt_fmt" = "S" ]; then
    echo
    echo "🚨 ATENÇÃO: A FORMATAÇÃO APAGARÁ TODOS OS DADOS EM $destino!"
    printf "Para confirmar a formatação, digite exatamente FORMATAR: "
    read -r conf_fmt
    if [ "$conf_fmt" = "FORMATAR" ] || [ "$conf_fmt" = "formatar" ]; then
        if [ "$(uname)" = "Darwin" ]; then
            echo "⚡ Formatando no macOS via diskutil..."
            if diskutil eraseVolume ExFAT AULAS "$destino" >/dev/null 2>&1; then
                if [ -d "/Volumes/AULAS" ]; then
                    destino="/Volumes/AULAS"
                fi
                echo "✅ Volume formatado com sucesso em exFAT!"
            fi
        elif command -v udisksctl >/dev/null 2>&1; then
            dev=$(findmnt -n -o SOURCE "$destino" 2>/dev/null || df "$destino" 2>/dev/null | tail -1 | awk '{print $1}')
            if [ -n "$dev" ] && [ -b "$dev" ]; then
                echo "⚡ Formatando $dev via udisksctl..."
                udisksctl unmount -b "$dev" >/dev/null 2>&1 || true
                if udisksctl format -b "$dev" -t exfat --name AULAS --no-user-interaction >/dev/null 2>&1; then
                    res_mount=$(udisksctl mount -b "$dev" 2>/dev/null || true)
                    new_dest=$(echo "$res_mount" | awk '{print $NF}' | tr -d '.')
                    if [ -d "$new_dest" ]; then
                        destino="$new_dest"
                    fi
                    echo "✅ Unidade formatada com sucesso em exFAT!"
                fi
            fi
        fi
    else
        echo "ℹ️  Formatação cancelada. Prosseguindo com os dados existentes."
    fi
fi

# Determinar pasta do kit no pendrive
KIT_FOLDER=$(basename "$SELECIONADO" .zip)
DESTINO_FINAL="$destino/$KIT_FOLDER"
mkdir -p "$DESTINO_FINAL"

echo
echo "================================================================="
echo "  Origem       : $(basename "$SELECIONADO")"
echo "  Pendrive     : $destino"
echo "  Pasta do Kit : $DESTINO_FINAL"
echo "================================================================="
printf "Confirmar a gravação no pendrive? [S/n]: "
read -r confirma
if [ "$confirma" = "n" ] || [ "$confirma" = "N" ]; then
    echo "Operação cancelada."
    exit 0
fi

echo
echo "⚡ Extraindo em alta velocidade para $DESTINO_FINAL..."
if command -v tar >/dev/null 2>&1 && tar -tf "$SELECIONADO" >/dev/null 2>&1; then
    tar -xf "$SELECIONADO" --strip-components=1 -C "$DESTINO_FINAL"
else
    unzip -q -o "$SELECIONADO" -d "$DESTINO_FINAL"
fi

if [ -f "$DESTINO_FINAL/iniciar-linux.sh" ]; then
    chmod +x "$DESTINO_FINAL/iniciar-linux.sh" 2>/dev/null || true
fi
if [ -f "$DESTINO_FINAL/laboratorio.desktop" ]; then
    chmod +x "$DESTINO_FINAL/laboratorio.desktop" 2>/dev/null || true
fi

# Criar LEIA-ME na raiz do pendrive
if [ ! -f "$destino/LEIA-ME.txt" ]; then
    cat <<EOF > "$destino/LEIA-ME.txt"
=================================================================
  LABORATÓRIO PORTÁTIL UNIVERSAL - KITS DE AULA
=================================================================

Os kits de desenvolvimento estão em pastas dedicadas neste pendrive:
  • $KIT_FOLDER/

Como iniciar seus estudos:
  1. Abra a pasta do kit desejado (ex: $KIT_FOLDER).
  2. No Windows : dê duplo clique em 'iniciar-windows.cmd'.
  3. No Linux   : dê duplo clique em 'laboratorio.desktop'
                  ou abra o terminal na pasta e execute: ./iniciar-linux.sh
=================================================================
EOF
fi

echo
echo "================================================================="
echo "  🎉 Pendrive gravado e pronto para a aula com sucesso!"
echo "================================================================="
echo "Local do kit: $DESTINO_FINAL"
echo "Para iniciar: Acesse a pasta '$KIT_FOLDER' e execute ./iniciar-linux.sh ou iniciar-windows.cmd"
echo "================================================================="
echo

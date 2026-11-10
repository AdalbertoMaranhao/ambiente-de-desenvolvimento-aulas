#!/bin/sh
# Apenas leitura, sem rede e sem necessidade de root.
printf '%s\n' '=== Diagnostico preliminar do laboratorio ==='
if [ "$(uname -s)" != Linux ]; then
    printf '%s\n' 'Este diagnostico destina-se ao Linux.'
    exit 1
fi
printf '\n%s\n' 'Sistema e arquitetura:'
uname -srm
if [ -r /etc/os-release ]; then
    sed -n '/^PRETTY_NAME=/p; /^ID=/p; /^VERSION_ID=/p' /etc/os-release
fi
printf '\n%s\n' 'Biblioteca C:'
getconf GNU_LIBC_VERSION 2>/dev/null || printf '%s\n' 'glibc nao identificada via getconf (pode ser outro libc).'
printf '\n%s\n' 'Memoria:'
if [ -r /proc/meminfo ]; then
    sed -n '/^MemTotal:/p; /^MemAvailable:/p' /proc/meminfo
fi
printf '\n%s\n' 'Espaco no local atual:'
df -Pk .
printf '\n%s\n' 'Comandos encontrados no PATH (nao verifica se funcionam):'
for task_command in php java javac python3 git sqlite3 code tar; do
    if command -v "$task_command" >/dev/null 2>&1; then
        printf '%s: presente\n' "$task_command"
    else
        printf '%s: ausente\n' "$task_command"
    fi
done
printf '\n%s\n' 'Configuracoes de namespaces (indicios para sandbox; nao sao teste funcional):'
for task_setting in /proc/sys/kernel/unprivileged_userns_clone /proc/sys/user/max_user_namespaces /proc/sys/kernel/apparmor_restrict_unprivileged_userns; do
    if [ -r "$task_setting" ]; then
        printf '%s: ' "$task_setting"
        cat "$task_setting"
    fi
done
printf '\n%s\n' 'Validar depois: permissao de execucao, bibliotecas, editor e conexoes locais.'

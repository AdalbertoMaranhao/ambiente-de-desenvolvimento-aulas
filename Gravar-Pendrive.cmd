@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo =================================================================
echo   🚀 Gravador Rápido de Pendrive - Laboratório Portátil
echo =================================================================
echo.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: 1. Tentar executar o gravador completo em Python se disponível
where python >nul 2>&1
if %errorlevel% equ 0 (
    python "%SCRIPT_DIR%gravar_pendrive.py" %*
    goto :fim
)

where py >nul 2>&1
if %errorlevel% equ 0 (
    py "%SCRIPT_DIR%gravar_pendrive.py" %*
    goto :fim
)

:: 2. Fallback nativo do Windows (usando tar.exe nativo e PowerShell)
echo [Aviso] Python não detectado no sistema.
echo Utilizando motor nativo do Windows (tar.exe de alta velocidade)...
echo.

if not exist "%SCRIPT_DIR%dist" (
    echo [Erro] Pasta 'dist' não encontrada.
    echo Certifique-se de que o kit foi baixado ou montado antes de gravar.
    pause
    exit /b 1
)

:: Listar pacotes zip disponíveis
echo Pacotes disponíveis em dist:
set /a count=0
for %%f in ("%SCRIPT_DIR%dist\kit-*.zip") do (
    set /a count+=1
    set "pkg_!count!=%%~nxf"
    echo   [!count!] %%~nxf
)

if %count% equ 0 (
    echo [Erro] Nenhum pacote kit-*.zip encontrado na pasta dist.
    pause
    exit /b 1
)

echo.
set /p "escolha=Selecione o kit a ser gravado [1-%count%]: "
set "ZIP_NAME=!pkg_%escolha%!"
if not defined ZIP_NAME (
    echo [Erro] Opção inválida.
    pause
    exit /b 1
)

set "ZIP_PATH=%SCRIPT_DIR%dist\%ZIP_NAME%"
echo.
echo Kit selecionado: %ZIP_NAME%
echo.

:: Detectar unidades removíveis via PowerShell
echo Procurando pendrives conectados...
powershell -NoProfile -Command "Get-CimInstance Win32_LogicalDisk | Where-Object { $_.DriveType -eq 2 } | ForEach-Object { Write-Host ('  [' + $_.DeviceID + '] ' + $_.VolumeName + ' (' + [math]::Round($_.FreeSpace/1GB, 2) + ' GB livres de ' + [math]::Round($_.Size/1GB, 2) + ' GB)') }"

echo.
set /p "DRIVE_LETTER=Digite a letra do seu pendrive (ex: E): "
set "DRIVE_LETTER=%DRIVE_LETTER::=%"
set "DESTINO=%DRIVE_LETTER%:\"

if not exist "%DESTINO%" (
    echo [Erro] A unidade '%DESTINO%' não existe ou não está acessível.
    pause
    exit /b 1
)

:: Opção de formatação para exFAT de alta performance
echo.
echo =================================================================
echo   💡 Dica: O sistema de arquivos ideal é exFAT (cluster 128 KB).
echo   Ele grava até 3x mais rápido e funciona em Windows, Mac e Linux.
echo =================================================================
set /p "OPT_FORMATAR=Deseja formatar %DRIVE_LETTER%: em exFAT antes de gravar? [s/N]: "
if /i "%OPT_FORMATAR%"=="s" (
    echo.
    echo 🚨 ATENÇÃO: A FORMATAÇÃO APAGARÁ TODOS OS DADOS EM %DRIVE_LETTER%:!
    set /p "CONFIRMA_FMT=Para confirmar a formatação, digite exatamente FORMATAR: "
    if /i "!CONFIRMA_FMT!"=="FORMATAR" (
        echo ⚡ Formatando %DRIVE_LETTER%: em exFAT (cluster 128 KB, rótulo AULAS)...
        format %DRIVE_LETTER%: /FS:exFAT /Q /A:128K /V:AULAS /Y
        if !errorlevel! neq 0 (
            format %DRIVE_LETTER%: /FS:exFAT /Q /V:AULAS /Y
        )
        echo ✅ Unidade %DRIVE_LETTER%: formatada com sucesso!
    ) else (
        echo Formatação cancelada. Prosseguindo com os dados existentes.
    )
)

:: Determinar pasta do kit no pendrive
set "KIT_FOLDER=%ZIP_NAME:~0,-4%"
set "DESTINO_FINAL=%DESTINO%%KIT_FOLDER%"
if not exist "%DESTINO_FINAL%" mkdir "%DESTINO_FINAL%"

echo.
echo =================================================================
echo   Origem       : %ZIP_PATH%
echo   Pendrive     : %DESTINO%
echo   Pasta do Kit : %DESTINO_FINAL%
echo =================================================================
set /p "CONFIRMA=Confirmar gravação no pendrive? [S/n]: "
if /i "%CONFIRMA%"=="n" (
    echo Operação cancelada pelo usuário.
    exit /b 0
)

echo.
echo ⚡ Descompactando via tar.exe em alta velocidade para %DESTINO_FINAL%...
tar -xf "%ZIP_PATH%" --strip-components=1 -C "%DESTINO_FINAL%"

if %errorlevel% equ 0 (
    :: Criar LEIA-ME na raiz do pendrive
    if not exist "%DESTINO%LEIA-ME.txt" (
        (
            echo =================================================================
            echo   LABORATÓRIO PORTÁTIL UNIVERSAL - KITS DE AULA
            echo =================================================================
            echo.
            echo Os kits de desenvolvimento estão em pastas dedicadas neste pendrive:
            echo   • %KIT_FOLDER%\
            echo.
            echo Como iniciar seus estudos:
            echo   1. Abra a pasta do kit desejado ^(ex: %KIT_FOLDER%^).
            echo   2. No Windows : dê duplo clique em 'iniciar-windows.cmd'.
            echo   3. No Linux   : dê duplo clique em 'laboratorio.desktop' ou execute ./iniciar-linux.sh.
            echo =================================================================
        ) > "%DESTINO%LEIA-ME.txt"
    )
    echo.
    echo =================================================================
    echo   🎉 Pendrive gravado e pronto para a aula com sucesso!
    echo =================================================================
    echo Local do kit: %DESTINO_FINAL%
    echo Para iniciar: Abra a pasta '%KIT_FOLDER%' e execute 'iniciar-windows.cmd'.
    echo =================================================================
) else (
    echo.
    echo [Erro] Ocorreu uma falha durante a descompactação com tar.exe.
)

:fim
echo.
pause

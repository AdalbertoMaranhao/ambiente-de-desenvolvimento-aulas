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

echo.
echo =================================================================
echo   Origem  : %ZIP_PATH%
echo   Destino : %DESTINO%
echo =================================================================
set /p "CONFIRMA=Confirmar gravação direta no pendrive? [S/n]: "
if /i "%CONFIRMA%"=="n" (
    echo Operação cancelada pelo usuário.
    exit /b 0
)

echo.
echo ⚡ Descompactando via tar.exe em alta velocidade...
tar -xf "%ZIP_PATH%" --strip-components=1 -C "%DESTINO%"

if %errorlevel% equ 0 (
    echo.
    echo =================================================================
    echo   🎉 Pendrive gravado e pronto para a aula com sucesso!
    echo =================================================================
) else (
    echo.
    echo [Erro] Ocorreu uma falha durante a descompactação com tar.exe.
)

:fim
echo.
pause

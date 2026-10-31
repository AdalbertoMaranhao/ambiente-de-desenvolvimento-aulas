@echo off
setlocal
:: Verifica a compatibilidade do sistema antes de usar o laboratório
:: Execute este script antes de copiar o kit do pendrive

set PASS=0
set FAIL=0

echo 🔍 Verificando seu computador...
echo.

:: Versão do Windows
for /f "tokens=3*" %%a in ('reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion" /v CurrentBuild 2^>nul') do (
    set BUILD=%%a
)
if defined BUILD (
    if %BUILD% GEQ 22000 (
        echo   ✅ Windows: Build %BUILD% (Windows 11 compatível)
        set /a PASS+=1
    ) else (
        echo   ❌ Windows: Build %BUILD% (requer Windows 11)
        set /a FAIL+=1
    )
) else (
    echo   ❌ Não foi possível verificar a versão do Windows
    set /a FAIL+=1
)

:: Arquitetura
echo   ✅ Arquitetura: %PROCESSOR_ARCHITECTURE%
if /i "%PROCESSOR_ARCHITECTURE%"=="AMD64" (
    set /a PASS+=1
) else (
    echo   ❌ Arquitetura: %PROCESSOR_ARCHITECTURE% (requer AMD64)
    set /a FAIL+=1
)

:: Memória
for /f "tokens=2 delims=:" %%a in ('wmic OS get TotalVisibleMemorySize /format:list ^| find "TotalVisibleMemorySize"') do (
    set MEM=%%a
)
if defined MEM (
    set /a MEM_GB=MEM/1024
    if %MEM_GB% GEQ 4 (
        echo   ✅ Memória: %MEM_GB% GB (mínimo: 4 GB)
        set /a PASS+=1
    ) else (
        echo   ❌ Memória: %MEM_GB% GB (mínimo: 4 GB)
        set /a FAIL+=1
    )
)

:: Espaço em disco
for /f "tokens=3" %%a in ('wmic logicaldisk where "DeviceID='%SYSTEMDRIVE%' " get FreeSpace 2^>nul') do (
    set DISK=%%a
)
if defined DISK (
    set /a DISK_GB=DISK/1073741824
    if %DISK_GB% GEQ 10 (
        echo   ✅ Espaço em disco: %DISK_GB% GB livres (mínimo: 10 GB)
        set /a PASS+=1
    ) else (
        echo   ❌ Espaço em disco: %DISK_GB% GB livres (mínimo: 10 GB)
        set /a FAIL+=1
    )
)

echo.
echo ℹ️  Observações:
echo   - O laboratório inclui Python 3 próprio, não depende do sistema
echo   - O kit funciona sem conexão com internet
echo.

if %FAIL% EQU 0 (
    echo 🎉 Seu computador é compatível com o laboratório!
    echo.
    echo Para iniciar:
    echo   1. Copie a pasta do kit para o seu computador
    echo   2. Clique duas vezes em iniciar-windows.cmd
) else (
    echo ⚠️  Foram encontrados %FAIL% problema(s) de compatibilidade.
    echo     Consulte o professor antes de usar o laboratório.
)

echo.
echo Total: %PASS% aprovado(s), %FAIL% falha(s)
pause
exit /b %FAIL%

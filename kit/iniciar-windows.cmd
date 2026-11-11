@echo off
setlocal

:: 1. Localizar o kit (diretorio deste script)
set "KIT_DIR=%~dp0"

:: 2. Localizar Python de bootstrap (primeiro verifica no armazenamento local persistente, depois no pendrive)
set "LOCAL_BOOTSTRAP=%LOCALAPPDATA%\LaboratorioAulas\bootstrap\windows-x64\python\python.exe"
set "PY_EXE="
if exist "%LOCAL_BOOTSTRAP%" set "PY_EXE=%LOCAL_BOOTSTRAP%"
if not defined PY_EXE if exist "%KIT_DIR%ferramentas\windows-x64\python\python.exe" set "PY_EXE=%KIT_DIR%ferramentas\windows-x64\python\python.exe"
if not defined PY_EXE if exist "%KIT_DIR%tools\windows-x64\python\python.exe" set "PY_EXE=%KIT_DIR%tools\windows-x64\python\python.exe"

if not defined PY_EXE (
    where python >nul 2>&1 && set "PY_EXE=python"
)

if not defined PY_EXE (
    echo [Erro] Nao foi possivel localizar o Python de inicializacao do kit.
    pause
    exit /b 1
)

:: Boas-vindas na primeira execucao
if not exist "%KIT_DIR%configuracoes\windows-x64\iniciado.txt" (
    if not exist "%KIT_DIR%configuracoes\windows-x64" mkdir "%KIT_DIR%configuracoes\windows-x64" >nul 2>&1
    if exist "%KIT_DIR%BEM-VINDO.html" start "" "%KIT_DIR%BEM-VINDO.html"
    type nul > "%KIT_DIR%configuracoes\windows-x64\iniciado.txt" 2>nul
)

:: Inicializar o controle do laboratorio repassando todos os argumentos
"%PY_EXE%" -E "%KIT_DIR%lab.py" %*
set "TASK_RESULT=%ERRORLEVEL%"
if not "%TASK_RESULT%"=="0" pause
exit /b %TASK_RESULT%

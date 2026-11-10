@echo off
setlocal
set "PY_EXE=%~dp0ferramentas\windows-x64\python\python.exe"
if not exist "%PY_EXE%" set "PY_EXE=%~dp0tools\windows-x64\python\python.exe"

if not exist "%PY_EXE%" (
    echo Kit incompleto. As ferramentas para Windows nao foram encontradas.
    pause
    exit /b 1
)

if not exist "%~dp0configuracoes\windows-x64\iniciado.txt" (
    if not exist "%~dp0configuracoes\windows-x64" mkdir "%~dp0configuracoes\windows-x64"
    if exist "%~dp0configuracoes" attrib +h "%~dp0configuracoes" >nul 2>&1
    if exist "%~dp0tools" attrib +h "%~dp0tools" >nul 2>&1
    start "" "%~dp0BEM-VINDO.html"
    type nul > "%~dp0configuracoes\windows-x64\iniciado.txt" 2>nul
)

"%PY_EXE%" -E "%~dp0lab.py" %*
set "TASK_RESULT=%ERRORLEVEL%"
if not "%TASK_RESULT%"=="0" pause
exit /b %TASK_RESULT%

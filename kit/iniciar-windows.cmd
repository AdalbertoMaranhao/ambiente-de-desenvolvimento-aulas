@echo off
setlocal
if not exist "%~dp0tools\windows-x64\python\python.exe" (
    echo Kit incompleto. O professor precisa executar preparar.py montar antes de distribuir.
    pause
    exit /b 1
)
if not exist "%~dp0estado\windows-x64\credenciais.json" (
    start "" "%~dp0BEM-VINDO.html"
)
"%~dp0tools\windows-x64\python\python.exe" -E "%~dp0lab.py" %*
set "TASK_RESULT=%ERRORLEVEL%"
if not "%TASK_RESULT%"=="0" pause
exit /b %TASK_RESULT%

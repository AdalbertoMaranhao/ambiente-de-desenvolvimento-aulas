@echo off
setlocal
echo === Diagnostico preliminar do laboratorio ===
echo.
ver
echo Arquitetura do processo: %PROCESSOR_ARCHITECTURE%
if defined PROCESSOR_ARCHITEW6432 echo Arquitetura nativa: %PROCESSOR_ARCHITEW6432%
echo.
echo Comandos encontrados no PATH - nao verifica se funcionam:
for %%T in (php.exe java.exe javac.exe python.exe git.exe mariadbd.exe mariadb.exe Code.exe tar.exe) do (
    where /q %%T >nul 2>&1
    if errorlevel 1 (echo %%T: ausente) else (echo %%T: presente)
)
echo.
echo Detalhes do sistema, se o PowerShell e o CIM estiverem disponiveis:
powershell.exe -NoLogo -NoProfile -Command "$ErrorActionPreference='Stop'; try { Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber,OSArchitecture,TotalVisibleMemorySize | Format-List; Write-Output ('PowerShell LanguageMode: ' + $ExecutionContext.SessionState.LanguageMode) } catch { Write-Output 'Detalhes indisponiveis; informe a versao do Windows manualmente.'; exit 1 }"
echo.
echo Validar depois: runtime Visual C++, execucao na pasta do aluno e conexoes locais.
echo Este diagnostico nao instala nem altera configuracoes.
endlocal

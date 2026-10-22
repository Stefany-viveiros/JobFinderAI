@echo off
setlocal
set "ROOT=%~dp0.."
if not exist "%ROOT%\.venv\Scripts\python.exe" (
  echo Ambiente Python .venv nao encontrado.
  echo Abra o terminal na pasta do projeto e siga os comandos de instalacao do README.md.
  pause
  exit /b 1
)
where npm >nul 2>nul
if errorlevel 1 (
  echo npm nao encontrado. Instale o Node.js LTS e abra um novo terminal.
  pause
  exit /b 1
)
start "JobFinder AI - API Python" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location -LiteralPath '%ROOT%'; & '%ROOT%\.venv\Scripts\python.exe' -m uvicorn jobfinder.api:app --reload"
start "JobFinder AI - React" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location -LiteralPath '%ROOT%\frontend'; if (-not (Test-Path 'node_modules')) { npm install }; npm run dev"
echo Os terminais do backend e do frontend foram abertos.
echo Acesse http://localhost:5173 no navegador.
endlocal

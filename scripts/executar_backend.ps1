$ProjectPath = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectPath
if (-not (Test-Path "$ProjectPath\.venv\Scripts\python.exe")) {
    Write-Host "Ambiente .venv não encontrado. Rode os comandos de instalação do README.md primeiro." -ForegroundColor Yellow
    exit 1
}
& "$ProjectPath\.venv\Scripts\python.exe" -m uvicorn jobfinder.api:app --reload

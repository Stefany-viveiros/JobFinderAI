$ProjectPath = Resolve-Path (Join-Path $PSScriptRoot "..")
$Launcher = Join-Path $PSScriptRoot "executar_app.bat"
if (-not (Test-Path $Launcher)) {
    Write-Host "Arquivo de inicialização não encontrado: $Launcher" -ForegroundColor Red
    exit 1
}
Start-Process -FilePath $Launcher -WorkingDirectory $ProjectPath

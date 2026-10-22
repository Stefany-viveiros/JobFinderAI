$ProjectPath = Resolve-Path (Join-Path $PSScriptRoot "..")
$FrontendPath = Join-Path $ProjectPath "frontend"
Set-Location $FrontendPath
if (-not (Test-Path "$FrontendPath\node_modules")) {
    Write-Host "Instalando dependências do React..." -ForegroundColor Cyan
    npm install
}
npm run dev

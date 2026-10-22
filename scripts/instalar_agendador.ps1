param(
  [string]$ProjectPath = (Resolve-Path (Join-Path $PSScriptRoot "..")),
  [string]$TaskName = "JobFinderAI-Lembretes-Diarios",
  [string]$Time = "09:00"
)
$python = Join-Path $ProjectPath ".venv\Scripts\python.exe"
if (!(Test-Path $python)) { throw "Ambiente virtual não encontrado: $python. Execute primeiro o setup do README." }
$action = New-ScheduledTaskAction -Execute $python -Argument "-m jobfinder.reminder_runner" -WorkingDirectory $ProjectPath
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "Resumo diário de tarefas pendentes do JobFinder AI" -Force
Write-Host "Agendador registrado: $TaskName às $Time. Confira as credenciais SMTP no .env."

# setup_task.ps1 - Run as Administrator

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$TaskName    = "iPhoneManager"
$PS          = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
$Script      = Join-Path $ProjectRoot "launch.ps1"
$Args        = "-WindowStyle Hidden -NonInteractive -ExecutionPolicy Bypass -File `"$Script`""

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Stop-Process -Name "pythonw" -Force -ErrorAction SilentlyContinue
Stop-Process -Name "python"  -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

$action = New-ScheduledTaskAction -Execute $PS -Argument $Args
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
    -RestartCount 0 `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -RunLevel Highest `
    -LogonType Interactive

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "iPhone Manager local web UI" `
    -Force

Write-Host "Starting task..." -ForegroundColor Cyan
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 6

$listening = netstat -ano | Select-String ":5055"
if ($listening) {
    Write-Host "SUCCESS - listening on port 5055" -ForegroundColor Green
} else {
    Write-Host "Not listening yet - check logs in $ProjectRoot\logs" -ForegroundColor Yellow
}

# uninstall_service.ps1
# Run as Administrator

$ServiceName = "iPhoneManager"
$nssmPath = "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe"

$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $svc) {
    Write-Host "Service '$ServiceName' not found." -ForegroundColor Yellow
    exit 0
}

Write-Host "Stopping and removing $ServiceName service..." -ForegroundColor Cyan
& $nssmPath stop $ServiceName
Start-Sleep -Seconds 2
& $nssmPath remove $ServiceName confirm
Write-Host "Service removed." -ForegroundColor Green

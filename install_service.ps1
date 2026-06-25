# install_service.ps1
# Run as Administrator

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir  = Join-Path $ProjectRoot "backend"
$LogDir      = Join-Path $ProjectRoot "logs"
$EnvFile     = Join-Path $ProjectRoot "environment.ps1"

if (Test-Path $EnvFile) {
    . $EnvFile
}

$Python      = (Get-Command python -ErrorAction Stop).Source
$VenvPython  = Join-Path $BackendDir ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $Python = $VenvPython
}
$LibDirs     = Get-ChildItem -Path $ProjectRoot -Directory -Filter "libimobiledevice*" -ErrorAction SilentlyContinue
$LibMobile   = if ($LibDirs) { $LibDirs[0].FullName } else { "" }
$SitePkgs    = Join-Path $BackendDir ".venv\Lib\site-packages"
$ServiceName = "iPhoneManager"
$nssmPath    = "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe"

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

if (-not (Test-Path $nssmPath)) {
    Write-Host "NSSM not found at: $nssmPath" -ForegroundColor Red
    exit 1
}

function Invoke-NSSM { & $nssmPath @args }

$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Removing existing service..." -ForegroundColor Yellow
    Invoke-NSSM stop $ServiceName | Out-Null
    Start-Sleep -Seconds 2
    Invoke-NSSM remove $ServiceName confirm | Out-Null
    Start-Sleep -Seconds 2
}

Write-Host "Installing $ServiceName service..." -ForegroundColor Cyan
Invoke-NSSM install $ServiceName $Python
Invoke-NSSM set $ServiceName AppParameters "run_service.py"
Invoke-NSSM set $ServiceName AppDirectory $BackendDir

$pathExtra = if ($LibMobile) { "$LibMobile;$env:PATH" } else { $env:PATH }
$ConfigDir = if ($env:IPHONE_MANAGER_CONFIG_DIR) {
    $env:IPHONE_MANAGER_CONFIG_DIR
} else {
    Join-Path $env:APPDATA "iPhoneManager"
}
if (-not (Test-Path $ConfigDir)) { New-Item -ItemType Directory -Path $ConfigDir | Out-Null }

Invoke-NSSM set $ServiceName AppEnvironment "PYTHONPATH=$SitePkgs" "VIRTUAL_ENV=$BackendDir\.venv" "IPHONE_MANAGER_SERVICE=1" "IPHONE_MANAGER_CONFIG_DIR=$ConfigDir"
Invoke-NSSM set $ServiceName AppEnvironmentExtra "PATH=$pathExtra"

Invoke-NSSM set $ServiceName DisplayName "iPhone Manager"
Invoke-NSSM set $ServiceName Description "iPhone Backup Manager local web UI"
Invoke-NSSM set $ServiceName Start SERVICE_AUTO_START
Invoke-NSSM set $ServiceName AppStdout "$LogDir\service_out.log"
Invoke-NSSM set $ServiceName AppStderr "$LogDir\service_err.log"
Invoke-NSSM set $ServiceName AppRotateFiles 1
Invoke-NSSM set $ServiceName AppRotateBytes 5242880

Invoke-NSSM set $ServiceName ObjectName ".\$env:USERNAME" "$(Read-Host 'Enter Windows password for service account')"

Write-Host "Starting service..." -ForegroundColor Cyan
Invoke-NSSM start $ServiceName
Start-Sleep -Seconds 4

$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -eq "Running") {
    Write-Host "SUCCESS! iPhone Manager service is running." -ForegroundColor Green
    Write-Host "Default URL: http://127.0.0.1:5055" -ForegroundColor Green
} else {
    Write-Host "Service status: $($svc.Status)" -ForegroundColor Red
    Get-Content "$LogDir\service_err.log" -ErrorAction SilentlyContinue | Select-Object -Last 20
}

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir  = Join-Path $ProjectRoot "backend"
$EnvFile     = Join-Path $ProjectRoot "environment.ps1"

if (Test-Path $EnvFile) {
    . $EnvFile
}

$LibDirs = Get-ChildItem -Path $ProjectRoot -Directory -Filter "libimobiledevice*" -ErrorAction SilentlyContinue
if ($LibDirs) {
  $env:PATH = ($LibDirs[0].FullName + [IO.Path]::PathSeparator + $env:PATH)
}

Set-Location $BackendDir
$VenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
  & $VenvPython "run_service.py"
  exit $LASTEXITCODE
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
  throw "Python not found on PATH."
}
& $python.Source "run_service.py"

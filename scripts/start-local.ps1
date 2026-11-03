$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path '.venv/Scripts/python.exe')) { throw 'Create .venv and install requirements.txt first.' }
if (-not (Test-Path 'local.settings.json')) { throw 'Copy local.settings.example.json and replace APP_API_KEY first.' }
$env:VIRTUAL_ENV = Join-Path $projectRoot '.venv'
$env:Path = "$projectRoot\.venv\Scripts;$env:Path"
func start --port 7071

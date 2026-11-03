param(
    [Parameter(Mandatory)][string]$AppName,
    [Parameter(Mandatory)][string]$ResourceGroup
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
if (-not (Get-Command az -ErrorAction SilentlyContinue)) { throw 'Install Azure CLI and run az login first.' }
if (-not (Get-Command func -ErrorAction SilentlyContinue)) { throw 'Install Azure Functions Core Tools v4 first.' }

Push-Location -LiteralPath $projectRoot
try {
    func azure functionapp publish $AppName --python --build remote
    if ($LASTEXITCODE -ne 0) { throw 'Publish failed; inspect the build output.' }
    $siteId = az functionapp show --name $AppName --resource-group $ResourceGroup --query id -o tsv
    if ($LASTEXITCODE -ne 0 -or -not $siteId) { throw 'Could not read the Azure resource ID.' }
    $expected = @('league', 'leagues', 'reports')
    # A fresh host can serve routes before management has synchronized its triggers.
    for ($attempt = 1; $attempt -le 6; $attempt++) {
        az rest --method post --url "https://management.azure.com$siteId/syncfunctiontriggers?api-version=2024-11-01" --output none
        if ($LASTEXITCODE -ne 0) { throw 'Function trigger synchronization failed.' }
        $functionNames = az functionapp function list --name $AppName --resource-group $ResourceGroup --query '[].name' -o tsv
        if ($LASTEXITCODE -ne 0) { throw 'Could not read registered functions.' }
        $registered = @($functionNames | ForEach-Object { ($_ -split '/')[-1] })
        if (-not (Compare-Object $expected $registered)) { break }
        if ($attempt -lt 6) { Start-Sleep -Seconds 10 }
    }
    if (Compare-Object $expected $registered) { throw 'Expected exactly league, leagues and reports. Inspect function indexing before testing.' }
    $hostName = az functionapp show --name $AppName --resource-group $ResourceGroup --query defaultHostName -o tsv
    if ($LASTEXITCODE -ne 0 -or -not $hostName) { throw 'Could not read the Azure hostname.' }
    Write-Output "Published. Run python tests/smoke_test.py against https://$hostName/api with the Azure key; see docs/project.pdf for hosted verification examples."
} finally {
    Pop-Location
}

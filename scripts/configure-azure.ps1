param(
    [Parameter(Mandatory)][string]$AppName,
    [Parameter(Mandatory)][string]$ResourceGroup
)
$ErrorActionPreference = 'Stop'
if (-not (Get-Command az -ErrorAction SilentlyContinue)) { throw 'Install Azure CLI and run az login first.' }
if ([string]::IsNullOrWhiteSpace($env:APP_API_KEY) -or $env:APP_API_KEY.Trim() -eq 'REPLACE_WITH_A_RANDOM_LOCAL_KEY') {
    throw 'Set the intended private Azure APP_API_KEY in this process first.'
}

# Windows az.cmd needs quotes preserved around the pipe in the runtime stack.
$runtimeStack = if ($IsWindows) { '"Python|3.12"' } else { 'Python|3.12' }
az functionapp config set --name $AppName --resource-group $ResourceGroup --always-on true --linux-fx-version $runtimeStack --min-tls-version 1.2 --ftps-state Disabled --output none
if ($LASTEXITCODE -ne 0) { throw 'Runtime configuration failed.' }
az functionapp update --name $AppName --resource-group $ResourceGroup --set httpsOnly=true --output none
if ($LASTEXITCODE -ne 0) { throw 'HTTPS configuration failed.' }
az functionapp config appsettings set --name $AppName --resource-group $ResourceGroup --settings FUNCTIONS_WORKER_RUNTIME=python 'FUNCTIONS_EXTENSION_VERSION=~4' FUNCTIONS_WORKER_PROCESS_COUNT=1 "APP_API_KEY=$env:APP_API_KEY" --output none
if ($LASTEXITCODE -ne 0) { throw 'App settings configuration failed.' }

foreach ($policy in 'scm', 'ftp') {
    az resource update --resource-group $ResourceGroup --name $policy --namespace Microsoft.Web --resource-type basicPublishingCredentialsPolicies --parent "sites/$AppName" --set properties.allow=false --output none
    if ($LASTEXITCODE -ne 0) { throw "Could not disable $policy basic publishing authentication." }
}
Write-Output 'Azure settings configured. Publish and run the hosted checks next.'

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
& docker compose --env-file (Join-Path $projectRoot 'deploy/.env.local') -f (Join-Path $projectRoot 'deploy/compose.app.yml') down
if ($LASTEXITCODE -ne 0) { throw 'Compose shutdown failed.' }
Write-Output 'Services stopped. Database and uploaded photos remain in their volumes.'

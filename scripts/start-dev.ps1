param([switch]$NoBuild)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot 'deploy/.env.local'
if (-not (Test-Path -LiteralPath $envPath)) {
    $content = Get-Content -LiteralPath (Join-Path $projectRoot 'deploy/.env.example') -Raw
    function New-LocalSecret {
        $bytes = New-Object byte[] 32
        $random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        try { $random.GetBytes($bytes) } finally { $random.Dispose() }
        return ([BitConverter]::ToString($bytes)).Replace('-', '').ToLowerInvariant()
    }
    $content = $content.Replace('change-this-development-password', (New-LocalSecret))
    $content = $content.Replace('development-only-change-this-secret-before-deployment', (New-LocalSecret))
    $content = $content.Replace('development-only-separate-phone-encryption-key', (New-LocalSecret))
    # Windows PowerShell 5.1 writes a BOM with Set-Content -Encoding UTF8.
    [System.IO.File]::WriteAllText($envPath, $content, [System.Text.UTF8Encoding]::new($false))
    Write-Output 'Created deploy/.env.local with private development credentials.'
}
$composePath = Join-Path $projectRoot 'deploy/compose.app.yml'
& docker info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop Linux containers, then run this script again.' }
$composeArgs = @('compose', '--env-file', $envPath, '-f', $composePath, 'up', '-d')
if (-not $NoBuild) { $composeArgs += '--build' }
& docker @composeArgs
if ($LASTEXITCODE -ne 0) { throw 'Compose startup failed. Check the output above.' }
$ready = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/v1/health/ready' -TimeoutSec 2
        if ($health.status -eq 'ready') { $ready = $true; break }
    } catch { }
    Start-Sleep -Seconds 1
}
if (-not $ready) { throw 'API is not ready. Run docker compose --env-file deploy/.env.local -f deploy/compose.app.yml logs api worker.' }
$running = @(& docker compose --env-file $envPath -f $composePath ps --status running --services)
if ($LASTEXITCODE -ne 0 -or $running -notcontains 'worker') { throw 'Worker is not running. Check docker compose logs worker.' }
Write-Output 'API ready: http://127.0.0.1:8000/docs'
Write-Output 'Development mode uses a mock model and returns a login development_code.'

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'dev-shell.ps1')
$previousMock = $env:MOCK
$previousApiBase = $env:NEXT_PUBLIC_API_BASE
$previousTelemetry = $env:NEXT_TELEMETRY_DISABLED
Push-Location (Join-Path (Split-Path $PSScriptRoot -Parent) 'apps/dashboard')
try {
    $env:MOCK = '1'
    $env:NEXT_PUBLIC_API_BASE = ''
    $env:NEXT_TELEMETRY_DISABLED = '1'
    Write-Host 'MOCK DATA ONLY: http://127.0.0.1:3400 ; Ctrl+C stops the server.'
    & node node_modules/next/dist/bin/next dev -p 3400 -H 127.0.0.1
} finally {
    $env:MOCK = $previousMock
    $env:NEXT_PUBLIC_API_BASE = $previousApiBase
    $env:NEXT_TELEMETRY_DISABLED = $previousTelemetry
    Pop-Location
}

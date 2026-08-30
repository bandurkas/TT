$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$bundledRoot = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies'
$nodeDirectory = Join-Path $bundledRoot 'node/bin'
if (Test-Path (Join-Path $nodeDirectory 'node.exe')) {
    $env:PATH = "$nodeDirectory;$env:PATH"
}
$gitHelpers = Join-Path $bundledRoot 'native/git/mingw64/bin'
if (Test-Path (Join-Path $gitHelpers 'git-remote-https.exe')) {
    $env:GIT_EXEC_PATH = $gitHelpers
}
$venvScripts = Join-Path $projectRoot '.venv/Scripts'
if (Test-Path (Join-Path $venvScripts 'python.exe')) {
    $env:PATH = "$venvScripts;$env:PATH"
}
$localNpm = Join-Path $projectRoot '.tools/package/bin/npm-cli.js'
if (Test-Path $localNpm) {
    $global:TTLocalNpm = $localNpm
    function global:npm { & node $global:TTLocalNpm @args }
}
Write-Host 'TT tools ready for this PowerShell session. Backend requires Linux (fcntl).'

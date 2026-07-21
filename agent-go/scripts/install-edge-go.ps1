$ErrorActionPreference = "Stop"

$principal = [Security.Principal.WindowsPrincipal]::new(
    [Security.Principal.WindowsIdentity]::GetCurrent()
)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this installer from an elevated PowerShell session."
}

$installDir = Join-Path $env:ProgramFiles "KaydanEdge"
$configDir = Join-Path $env:ProgramData "KaydanEdge"
$logsDir = Join-Path $configDir "logs"
$binarySource = Join-Path $PSScriptRoot "bin\kshield-agent-windows-amd64.exe"
$binaryPath = Join-Path $installDir "kshield-agent.exe"
$configSource = Join-Path $PSScriptRoot "config\kshield-agent.toml"
$configPath = Join-Path $configDir "kshield-agent.toml"
$checksumFile = Join-Path $PSScriptRoot "bin\SHA256SUMS.txt"
$taskName = "KaydanEdgeGateway"

if (-not (Test-Path $binarySource)) { throw "Bundled gateway binary is missing." }
if (-not (Test-Path $configSource)) { throw "Bundled gateway configuration is missing." }

New-Item -ItemType Directory -Force -Path $installDir, $configDir, $logsDir | Out-Null
Copy-Item $binarySource $binaryPath -Force
Copy-Item $configSource $configPath -Force
if (Test-Path (Join-Path $PSScriptRoot "certs")) {
    Copy-Item (Join-Path $PSScriptRoot "certs") $configDir -Recurse -Force
}

if (Test-Path $checksumFile) {
    $expected = ((Get-Content $checksumFile -Raw) -split "\s+")[0].ToLowerInvariant()
    $actual = (Get-FileHash $binaryPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($expected -ne $actual) { throw "Bundled gateway binary checksum mismatch." }
}

$config = Get-Content $configPath -Raw
$serverUrl = [regex]::Match($config, 'server_url\s*=\s*"([^"]+)"').Groups[1].Value
$activationToken = [regex]::Match($config, 'activation_token\s*=\s*"([^"]*)"').Groups[1].Value
$apiToken = [regex]::Match($config, 'api_token\s*=\s*"([^"]*)"').Groups[1].Value
if (-not $serverUrl) { throw "server_url is missing from the configuration." }

if (-not $apiToken) {
    if (-not $activationToken) { throw "activation_token is missing from the configuration." }
    & $binaryPath activate --config $configPath --server-url $serverUrl --token $activationToken
    if ($LASTEXITCODE -ne 0) { throw "Gateway activation failed." }
}

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
$arguments = 'run --config "{0}"' -f $configPath
$action = New-ScheduledTaskAction -Execute $binaryPath -Argument $arguments -WorkingDirectory $configDir
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
$taskPrincipal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $taskPrincipal | Out-Null
Start-ScheduledTask -TaskName $taskName

Write-Host "Kaydan Edge Gateway installed and started." -ForegroundColor Green
Write-Host "Task:   $taskName"
Write-Host "Config: $configPath"

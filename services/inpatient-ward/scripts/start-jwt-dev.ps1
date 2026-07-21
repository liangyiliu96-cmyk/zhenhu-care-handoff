param(
  [int]$Port = 8001,
  [string]$JwtSecret = $env:AUTH_JWT_SECRET,
  [string]$DeepSeekApiKey = $env:DEEPSEEK_API_KEY
)

function Import-LocalEnvironment {
  param([string]$Path)

  if (-not (Test-Path -LiteralPath $Path)) { return }
  foreach ($line in Get-Content -LiteralPath $Path) {
    if ($line -match '^\s*#' -or $line -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') { continue }
    $name = $matches[1]
    $value = $matches[2].Trim().Trim('"').Trim("'")
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name, 'Process'))) {
      Set-Item -Path "Env:$name" -Value $value
    }
  }
}

Import-LocalEnvironment (Join-Path $PSScriptRoot '..\.env')
if ([string]::IsNullOrWhiteSpace($DeepSeekApiKey)) { $DeepSeekApiKey = $env:DEEPSEEK_API_KEY }

if ([string]::IsNullOrWhiteSpace($JwtSecret)) {
  $bytes = New-Object byte[] 48
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try {
    $rng.GetBytes($bytes)
  } finally {
    $rng.Dispose()
  }
  $JwtSecret = [Convert]::ToBase64String($bytes)
}
if ([string]::IsNullOrWhiteSpace($DeepSeekApiKey)) {
  throw 'DEEPSEEK_API_KEY is required to start the inpatient service.'
}

$env:APP_ENV = 'dev'
$env:AUTH_MODE = 'jwt'
$env:AUTH_JWT_SECRET = $JwtSecret
$env:AUTH_ISSUER = 'zhenhu-inpatient'
$env:AUTH_AUDIENCE = 'zhenhu-inpatient'
$env:ENABLE_DEV_SHORTCUT_LOGIN = 'true'
$env:DEEPSEEK_API_KEY = $DeepSeekApiKey
$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$contractsSource = Join-Path $workspaceRoot 'packages\clinical-contracts-py\src'
$env:PYTHONPATH = "$contractsSource$([IO.Path]::PathSeparator)$env:PYTHONPATH"

python -m uvicorn zhenhu.inpatient.main:app --app-dir src --host 127.0.0.1 --port $Port

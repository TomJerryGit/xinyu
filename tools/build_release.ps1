# Xinyu release: build -> Authenticode sign -> installer -> sign installer -> manifest -> Ed25519 sign.
# Certificate/private key are provided via environment variables; without them the manifest is dev-only.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "== 1. build exe =="
python build.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

$version = (python -c "from version import VERSION; print(VERSION)").Trim()
$exe = Join-Path $root "dist\Xinyu\Xinyu.exe"
if (-not (Test-Path $exe)) { throw "missing $exe" }

$signConfigured = $env:XINYU_SIGN_CERT_THUMBPRINT -or $env:XINYU_SIGN_PFX
if ($signConfigured) {
    Write-Host "== 2. Authenticode sign exe =="
    & (Join-Path $PSScriptRoot "sign_artifacts.ps1") -Files $exe
    if ($LASTEXITCODE -ne 0) { throw "exe signing failed" }
} else {
    Write-Host "No signing cert (XINYU_SIGN_CERT_THUMBPRINT / XINYU_SIGN_PFX); exe is unsigned."
}

Write-Host "== 3. compile installer =="
$isccPath = $null
$command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($command) {
    $isccPath = $command.Source
} else {
    foreach ($candidate in @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )) {
        if (Test-Path $candidate) {
            $isccPath = $candidate
            break
        }
    }
}
$installer = Join-Path $root "dist\installer\Xinyu-Setup-$version.exe"
if ($isccPath) {
    & $isccPath "/DMyAppVersion=$version" "installer\xinyu.iss"
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
    if (-not (Test-Path $installer)) { throw "installer not generated: $installer" }
    if ($signConfigured) {
        Write-Host "== 4. Authenticode sign installer =="
        & (Join-Path $PSScriptRoot "sign_artifacts.ps1") -Files $installer
        if ($LASTEXITCODE -ne 0) { throw "installer signing failed" }
    }
    $artifact = $installer
    $artifactRel = "installer/Xinyu-Setup-$version.exe"
} else {
    Write-Host "ISCC.exe not found; falling back to unsigned onedir exe."
    $artifact = $exe
    $artifactRel = "Xinyu/Xinyu.exe"
}

Write-Host "== 5. generate update.json =="
$hash = (Get-FileHash $artifact -Algorithm SHA256).Hash.ToLower()
$size = (Get-Item $artifact).Length
$updateUrl = $env:XINYU_UPDATE_URL
if (-not $updateUrl) {
    $updateUrl = "https://example.com/xinyu/$([System.IO.Path]::GetFileName($artifact))"
}
$rollout = 5
if ($env:XINYU_ROLLOUT) { $rollout = [int]$env:XINYU_ROLLOUT }
$manifest = [ordered]@{
    version     = $version
    url         = $updateUrl
    file        = $artifactRel
    sha256      = $hash
    size        = $size
    rollout     = $rollout
    released_at = (Get-Date).ToString("o")
}
$manifestJson = $manifest | ConvertTo-Json
[System.IO.File]::WriteAllText(
    (Join-Path $root "dist\update.json"),
    $manifestJson,
    (New-Object System.Text.UTF8Encoding($false))
)

Write-Host "== 6. Ed25519 sign manifest =="
$privateKey = $env:XINYU_UPDATE_PRIVATE_KEY
if ($privateKey -and (Test-Path $privateKey)) {
    python tools\sign_manifest.py sign --key $privateKey --manifest "dist\update.json"
    if ($LASTEXITCODE -ne 0) { throw "manifest signing failed" }
} else {
    Write-Host "No XINYU_UPDATE_PRIVATE_KEY; update.json is unsigned."
}

Write-Host "== result =="
Get-Content "dist\update.json"
Write-Host "artifact: $artifact"
Write-Host ("rollout: {0}% (later 25/100 via tools/set_rollout.py)" -f $rollout)

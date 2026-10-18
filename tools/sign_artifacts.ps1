param(
    [Parameter(Mandatory = $true)][string[]]$Files,
    [string]$Thumbprint = $env:XINYU_SIGN_CERT_THUMBPRINT,
    [string]$Pfx = $env:XINYU_SIGN_PFX,
    [string]$Password = $env:XINYU_SIGN_PASSWORD,
    [string]$Timestamp = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
if (-not $Thumbprint -and -not $Pfx) {
    throw "缺少代码签名证书：设置 XINYU_SIGN_CERT_THUMBPRINT 或 XINYU_SIGN_PFX"
}

if ($Thumbprint) {
    $cert = Get-ChildItem "Cert:\CurrentUser\My\$Thumbprint" -ErrorAction Stop
} elseif ($Pfx) {
    $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($Pfx, $Password)
}

foreach ($file in $Files) {
    if (-not (Test-Path $file)) { throw "文件不存在: $file" }
    Write-Host "签名: $file"
    $result = Set-AuthenticodeSignature -FilePath $file -Certificate $cert -TimestampServer $Timestamp
    if ($result.Status -ne "Valid") {
        throw "签名失败: $file -> $($result.Status)"
    }
    Get-AuthenticodeSignature -FilePath $file | Select-Object Path, Status, StatusMessage, SignerCertificate | Format-List
}

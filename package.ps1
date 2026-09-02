<#
    Sticky Notes - package the build as an MSIX for the Microsoft Store.

    Run build.ps1 first. This takes dist\StickyNote, drops the manifest and the
    Store tiles beside it, and produces dist\StickyNote.msix ready to upload.

    You need three values from Partner Center. Reserve your app name first,
    then read them off Product > Product identity:

        powershell -ExecutionPolicy Bypass -File package.ps1 `
            -IdentityName    "12345YourPublisher.StickyNotesPaper" `
            -Publisher       "CN=A1B2C3D4-0000-0000-0000-123456789ABC" `
            -PublisherDisplay "Your Publisher Name" `
            -DisplayName     "Sticky Notes Paper" `
            -Version         "1.0.0.0"

    Do NOT sign the package yourself for a Store submission - Microsoft signs
    it during certification, which is why Store distribution costs you nothing
    in certificates and produces no SmartScreen warning.

    To test the package on your own machine before uploading, add -SelfSign.
    That signs it with a throwaway local certificate so Windows will install
    it; a self-signed package can never be uploaded to the Store.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$IdentityName,
    [Parameter(Mandatory = $true)][string]$Publisher,
    [Parameter(Mandatory = $true)][string]$PublisherDisplay,
    [string]$DisplayName = "Sticky Notes",
    [string]$Version = "1.0.0.0",
    [switch]$SelfSign
)

$ErrorActionPreference = 'Continue'
$Root = $PSScriptRoot
$Build = Join-Path $Root 'dist\StickyNote'
$Stage = Join-Path $Root 'dist\msix'
$Msix = Join-Path $Root 'dist\StickyNote.msix'

if (-not (Test-Path (Join-Path $Build 'StickyNote.exe'))) {
    throw "No build found at $Build. Run build.ps1 first."
}
if ($Version -notmatch '^\d+\.\d+\.\d+\.\d+$') {
    throw "MSIX versions are four parts, e.g. 1.0.0.0 - got '$Version'"
}
if ($Version -match '\.\d+$' -and $Version.Split('.')[3] -ne '0') {
    Write-Host 'Note: the Store requires the fourth version part to be 0.' -ForegroundColor Yellow
}
if ($Publisher -notmatch '^CN=') {
    throw "Publisher must be the full subject from Partner Center, starting with 'CN='."
}

# ------------------------------------------------------- find the SDK tools

function Find-SdkTool([string]$name) {
    $roots = @(
        "${env:ProgramFiles(x86)}\Windows Kits\10\bin",
        "$env:ProgramFiles\Windows Kits\10\bin"
    ) | Where-Object { Test-Path $_ }
    foreach ($r in $roots) {
        $hit = Get-ChildItem $r -Directory -ErrorAction SilentlyContinue |
               Sort-Object Name -Descending |
               ForEach-Object { Join-Path $_.FullName "x64\$name" } |
               Where-Object { Test-Path $_ } |
               Select-Object -First 1
        if ($hit) { return $hit }
    }
    return $null
}

$makeappx = Find-SdkTool 'makeappx.exe'
if (-not $makeappx) {
    Write-Host ''
    Write-Host 'makeappx.exe not found - the Windows SDK is not installed.' -ForegroundColor Yellow
    Write-Host 'Install just the signing tools (a few hundred MB, not the whole SDK):'
    Write-Host ''
    Write-Host '  winget install --id Microsoft.WindowsSDK.10.0.22621'
    Write-Host ''
    Write-Host 'Or use the MSIX Packaging Tool from the Microsoft Store, which does'
    Write-Host 'the same job with a wizard.'
    throw 'Windows SDK required.'
}

# ------------------------------------------------------------------- stage

if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
New-Item -ItemType Directory -Path $Stage -Force | Out-Null

Copy-Item (Join-Path $Build '*') $Stage -Recurse -Force
Copy-Item (Join-Path $Root 'packaging\Images') $Stage -Recurse -Force

$manifest = Get-Content (Join-Path $Root 'packaging\AppxManifest.xml') -Raw
$manifest = $manifest.Replace('__IDENTITY_NAME__', $IdentityName)
$manifest = $manifest.Replace('__PUBLISHER__', $Publisher)
$manifest = $manifest.Replace('__PUBLISHER_DISPLAY__', $PublisherDisplay)
$manifest = $manifest.Replace('__DISPLAY_NAME__', $DisplayName)
$manifest = $manifest.Replace('__VERSION__', $Version)
$manifest | Out-File (Join-Path $Stage 'AppxManifest.xml') -Encoding utf8

# The app must not ship its own shortcut installer inside the package: an MSIX
# creates its Start Menu entry from the manifest, and writing shortcuts by hand
# is exactly the kind of thing Store certification rejects.
Remove-Item (Join-Path $Stage 'install.ps1') -Force -ErrorAction SilentlyContinue

# -------------------------------------------------------------------- pack

if (Test-Path $Msix) { Remove-Item $Msix -Force }
& $makeappx pack /d $Stage /p $Msix /o
if ($LASTEXITCODE -ne 0) { throw 'makeappx failed.' }

Write-Host ''
Write-Host ('Packed {0} ({1:N1} MB)' -f $Msix, ((Get-Item $Msix).Length / 1MB)) -ForegroundColor Green

# ------------------------------------------------- optional local test sign

if ($SelfSign) {
    $signtool = Find-SdkTool 'signtool.exe'
    if (-not $signtool) { throw 'signtool.exe not found in the Windows SDK.' }

    Write-Host 'Creating a throwaway local certificate...'
    $cert = New-SelfSignedCertificate -Type Custom -Subject $Publisher `
        -KeyUsage DigitalSignature -FriendlyName 'StickyNote local test' `
        -CertStoreLocation 'Cert:\CurrentUser\My' `
        -TextExtension @('2.5.29.37={text}1.3.6.1.5.5.7.3.3', '2.5.29.19={text}')
    $pfx = Join-Path $Root 'dist\localtest.pfx'
    $pw = ConvertTo-SecureString -String 'localtest' -Force -AsPlainText
    Export-PfxCertificate -Cert $cert -FilePath $pfx -Password $pw | Out-Null

    & $signtool sign /fd SHA256 /a /f $pfx /p 'localtest' $Msix
    if ($LASTEXITCODE -ne 0) { throw 'signtool failed.' }

    Write-Host ''
    Write-Host 'Signed for LOCAL TESTING ONLY. Do not upload this file.' -ForegroundColor Yellow
    Write-Host 'To install it you must first trust the test certificate:'
    Write-Host ('  Import-Certificate -FilePath (Export path) -CertStoreLocation Cert:\LocalMachine\TrustedPeople')
    Write-Host 'Then double-click the .msix. Re-run without -SelfSign to produce the upload build.'
} else {
    Write-Host ''
    Write-Host 'Unsigned, which is correct for a Store upload.' -ForegroundColor Cyan
    Write-Host 'Microsoft signs it during certification. Upload this file in'
    Write-Host 'Partner Center under Submission > Packages.'
}

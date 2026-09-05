# Build the MSIX for the Microsoft Store.
#
#   .\packaging\package.ps1                     # unsigned .msix, ready for Partner Center
#   .\packaging\package.ps1 -Sign               # plus a self-signed one for a local install test
#
# For a Store upload, pass the three identity values Partner Center shows
# under Product > Product identity after you reserve the app name:
#
#   .\packaging\package.ps1 -IdentityName 12345Publisher.Sticky `
#       -Publisher "CN=A1B2C3D4-..." -PublisherDisplay "Your Name"
#
# The Store re-signs the package itself, so the upload build needs no signing.
# The defaults below only exist so the script runs end to end for local tests.

param(
    [string]$IdentityName     = "Local.Sticky",
    [string]$Publisher        = "CN=Sticky Dev",
    [string]$PublisherDisplay = "Sticky Dev",
    [string]$DisplayName      = "Sticky",
    [string]$Version          = "1.0.0.0",
    [switch]$Sign
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$out = Join-Path $root "out"
$stage = Join-Path $out "msix"

# Newest Windows SDK wins; makeappx and signtool live side by side.
$kits = "C:\Program Files (x86)\Windows Kits\10\bin"
$sdk = Get-ChildItem $kits -Directory -Filter "10.*" |
    Sort-Object Name -Descending |
    Where-Object { Test-Path (Join-Path $_.FullName "x64\makeappx.exe") } |
    Select-Object -First 1
if ($null -eq $sdk) { throw "no Windows SDK with makeappx.exe under $kits" }
$makeappx = Join-Path $sdk.FullName "x64\makeappx.exe"
$signtool = Join-Path $sdk.FullName "x64\signtool.exe"

Write-Host "== PyInstaller build =="
Push-Location $root
python -m PyInstaller Sticky.spec --noconfirm
Pop-Location
if ($LASTEXITCODE -ne 0) { throw "pyinstaller failed" }

Write-Host "== Staging =="
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force $stage | Out-Null
Copy-Item (Join-Path $root "dist\Sticky\*") $stage -Recurse
Copy-Item (Join-Path $PSScriptRoot "Images") $stage -Recurse

$manifest = Get-Content (Join-Path $PSScriptRoot "AppxManifest.xml") -Raw
$manifest = $manifest -replace "__IDENTITY_NAME__", $IdentityName `
                      -replace "__PUBLISHER__", [System.Security.SecurityElement]::Escape($Publisher) `
                      -replace "__PUBLISHER_DISPLAY__", [System.Security.SecurityElement]::Escape($PublisherDisplay) `
                      -replace "__DISPLAY_NAME__", [System.Security.SecurityElement]::Escape($DisplayName) `
                      -replace "__VERSION__", $Version
Set-Content (Join-Path $stage "AppxManifest.xml") $manifest -Encoding utf8

Write-Host "== makeappx pack =="
$msix = Join-Path $out "Sticky_$Version.msix"
& $makeappx pack /d $stage /p $msix /o
if ($LASTEXITCODE -ne 0) { throw "makeappx failed" }
Write-Host "wrote $msix"

Write-Host "== itch.io zip =="
# Flat zip for itch.io: no MSIX identity, no Store signing, just the exe folder.
$itch = Join-Path $out "itch\Sticky"
if (Test-Path $itch) { Remove-Item $itch -Recurse -Force }
New-Item -ItemType Directory -Force $itch | Out-Null
Copy-Item (Join-Path $root "dist\Sticky\*") $itch -Recurse

$readme = @"
Sticky $Version for Windows
=========================

Sticky notes on your desktop, with a crew of little box-men who live on
your taskbar, read what you write, and act on it.

RUN
  1. Unzip anywhere. Keep the folder together: Sticky.exe needs _internal.
  2. Double-click Sticky.exe.
  3. Windows SmartScreen may warn the first time, because this build is
     not code-signed. Click "More info", then "Run anyway".

TRY
  - Type "pizza" on a note. Somebody goes to fetch one.
  - Type "birthday". Hats.
  - Type "zzz". He naps.
  - Type "grr". He gets grumpy and turns the fun down.
  - Right-click a note > Scenes to ask for a race, a party, the ice
    cream van, a pizza run or a sing-along.
  - Ctrl+Alt+N drops a new note where your pointer is.
  - The board (Sticky in your taskbar) lists every note and, at the
    bottom, "What do they react to?"

YOUR NOTES
  Saved in %APPDATA%\StickyNote\notes.json and nowhere else. No account,
  no network, nothing phones home.

UNINSTALL
  Delete the folder. Delete %APPDATA%\StickyNote too if you want the
  notes gone.

Source: https://github.com/kryshn7777/Sticky-Audit-
"@
Set-Content (Join-Path $itch "README.txt") $readme -Encoding utf8

$zip = Join-Path $out "Sticky-$Version-win64.zip"
Compress-Archive -Path $itch -DestinationPath $zip -Force
Write-Host "wrote $zip"

if ($Sign) {
    # Self-signed cert for a local install test only. The subject must equal
    # the manifest Publisher exactly or Windows refuses the package.
    Write-Host "== signing (local test) =="
    $cert = Get-ChildItem Cert:\CurrentUser\My |
        Where-Object { $_.Subject -eq $Publisher } | Select-Object -First 1
    if ($null -eq $cert) {
        $cert = New-SelfSignedCertificate -Type Custom -Subject $Publisher `
            -KeyUsage DigitalSignature -FriendlyName "Sticky local test" `
            -CertStoreLocation Cert:\CurrentUser\My `
            -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3", "2.5.29.19={text}")
    }
    & $signtool sign /fd SHA256 /sha1 $cert.Thumbprint $msix
    if ($LASTEXITCODE -ne 0) { throw "signtool failed" }
    Write-Host @"
signed with a self-signed certificate. Before this package will install,
Windows must trust that certificate (one-time, admin PowerShell):

  Export-Certificate -Cert (Get-Item Cert:\CurrentUser\My\$($cert.Thumbprint)) -FilePath "$out\sticky-test.cer"
  Import-Certificate -FilePath "$out\sticky-test.cer" -CertStoreLocation Cert:\LocalMachine\Root

then double-click the .msix, or:  Add-AppxPackage "$msix"
"@
}

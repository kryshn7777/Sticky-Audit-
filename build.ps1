<#
    Sticky - build a standalone Windows application.

    Produces dist\Sticky\Sticky.exe, which runs on a machine with no
    Python installed, plus a zip ready to hand to someone.

    Usage:
        powershell -ExecutionPolicy Bypass -File build.ps1
        powershell -ExecutionPolicy Bypass -File build.ps1 -Version 1.1.0 -Publisher "Your Name"
        powershell -ExecutionPolicy Bypass -File build.ps1 -OneFile

    One folder, not one file, by default. A one-file build unpacks itself into
    a temp directory on every single launch, which costs a second of startup
    and a few megabytes of disk writes each time - the opposite of what this
    app is for. Use -OneFile only if a single loose .exe matters more.
#>

[CmdletBinding()]
param(
    [string]$Version = "1.0.0",
    [string]$Publisher = "Sticky",
    [switch]$OneFile,
    [switch]$SkipZip,
    [string]$PythonPath
)

# Windows PowerShell turns any stderr output from a native exe into a
# terminating error when ErrorActionPreference is Stop. PyInstaller and Python
# both write progress and warnings to stderr, so exit codes are checked
# explicitly instead.
$ErrorActionPreference = 'Continue'
$Root = $PSScriptRoot
Set-Location $Root

# ------------------------------------------------------------------- checks

# There is usually more than one Python on a Windows box - a Store build, a
# miniconda, a python.org install - and they do not have the same packages.
# Pick one that can actually do the job rather than whatever PATH answers with.
function Find-BuildPython {
    $candidates = @()
    $candidates += (Get-Command python.exe -All -ErrorAction SilentlyContinue | ForEach-Object { $_.Source })
    $candidates += (Get-Command py.exe -ErrorAction SilentlyContinue | ForEach-Object {
        (& $_.Source -3 -c "import sys; print(sys.executable)" 2>$null) })
    $candidates += "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
    $candidates += "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
    $candidates = $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique

    # find_spec rather than import, so a missing module is an exit code and
    # not a traceback splattered across the build log
    $probe = "import importlib.util as u,sys; sys.exit(0 if u.find_spec('{0}') else 1)"

    $withTk = @()
    foreach ($c in $candidates) {
        & $c -c ($probe -f 'tkinter')
        if ($LASTEXITCODE -eq 0) { $withTk += $c }
    }
    if (-not $withTk) { throw 'No Python with tkinter found. Install python.org Python 3.8+.' }

    foreach ($c in $withTk) {                 # prefer one that already has PyInstaller
        & $c -c ($probe -f 'PyInstaller')
        if ($LASTEXITCODE -eq 0) { return $c }
    }
    return $withTk[0]
}

if ($PythonPath) {
    if (-not (Test-Path $PythonPath)) { throw "No Python at $PythonPath" }
    $python = $PythonPath
} else {
    $python = Find-BuildPython
}
Write-Host "Python  $python" -ForegroundColor DarkGray

& $python -c "import importlib.util as u,sys; sys.exit(0 if u.find_spec('PyInstaller') else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Host 'PyInstaller not found for this interpreter. Installing...' -ForegroundColor Yellow
    & $python -m pip install --quiet pyinstaller
    if ($LASTEXITCODE -ne 0) { throw 'Could not install PyInstaller.' }
}

if (-not (Test-Path (Join-Path $Root 'assets\sticky.ico'))) {
    Write-Host 'Building assets...'
    & $python (Join-Path $Root 'make_icon.py')
}

# Never ship a build that fails its own checks.
Write-Host 'Running checks...' -ForegroundColor Cyan
& $python (Join-Path $Root 'test_store.py')
if ($LASTEXITCODE -ne 0) { throw 'test_store.py failed - not building.' }
& $python (Join-Path $Root 'test_app.py')
if ($LASTEXITCODE -ne 0) { throw 'test_app.py failed - not building.' }

# --------------------------------------------------- Windows version resource

if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw "Version must look like 1.2.3, got '$Version'" }
$v = $Version.Split('.')
$quad = "$($v[0]), $($v[1]), $($v[2]), 0"

$versionFile = Join-Path $Root 'version_info.txt'
@"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($quad), prodvers=($quad),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', '$Publisher'),
      StringStruct('FileDescription', 'Sticky for Windows'),
      StringStruct('FileVersion', '$Version.0'),
      StringStruct('InternalName', 'Sticky'),
      StringStruct('LegalCopyright', '$Publisher'),
      StringStruct('OriginalFilename', 'Sticky.exe'),
      StringStruct('ProductName', 'Sticky'),
      StringStruct('ProductVersion', '$Version.0')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ])
"@ | Out-File -FilePath $versionFile -Encoding utf8

# ------------------------------------------------------------------- build

Write-Host "Building Sticky $Version..." -ForegroundColor Cyan

$pyArgs = @(
    '-m', 'PyInstaller',
    '--noconfirm', '--clean',
    '--windowed',                      # GUI app: never flash a console window
    '--name', 'Sticky',
    '--icon', (Join-Path $Root 'assets\sticky.ico'),
    '--add-data', 'assets;assets',
    '--version-file', $versionFile,
    # Pillow builds the icon and the paper grain; the app never imports it.
    '--exclude-module', 'PIL',
    '--exclude-module', 'numpy',
    '--exclude-module', 'pytest',
    '--exclude-module', 'unittest',
    '--exclude-module', 'pydoc',
    '--exclude-module', 'email',
    '--exclude-module', 'http',
    '--exclude-module', 'xml',
    '--exclude-module', 'lib2to3'
)
if ($OneFile) { $pyArgs += '--onefile' }
$pyArgs += (Join-Path $Root 'sticky.pyw')

& $python @pyArgs
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }

Remove-Item $versionFile -Force -ErrorAction SilentlyContinue

# -------------------------------------------------------------------- report

if ($OneFile) {
    $exe = Join-Path $Root 'dist\Sticky.exe'
    $payload = $exe
} else {
    $exe = Join-Path $Root 'dist\Sticky\Sticky.exe'
    $payload = Join-Path $Root 'dist\Sticky'
}
if (-not (Test-Path $exe)) { throw "Expected $exe but it was not produced." }

# Ship the shortcut installer and the readme inside the folder so the zip is
# self-contained. install.ps1 detects Sticky.exe and skips Python entirely.
if (-not $OneFile) {
    Copy-Item (Join-Path $Root 'install.ps1') $payload -Force
    Copy-Item (Join-Path $Root 'README.md') $payload -Force -ErrorAction SilentlyContinue
}

$size = (Get-ChildItem $payload -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Host ''
Write-Host ('Built {0}' -f $exe) -ForegroundColor Green
Write-Host ('Payload {0:N1} MB' -f ($size / 1MB))

if (-not $SkipZip) {
    $zip = Join-Path $Root ("dist\Sticky-{0}-win64.zip" -f $Version)
    if (Test-Path $zip) { Remove-Item $zip -Force }
    Compress-Archive -Path $payload -DestinationPath $zip
    Write-Host ('Zipped  {0} ({1:N1} MB)' -f $zip, ((Get-Item $zip).Length / 1MB))
}

Write-Host ''
Write-Host 'This build is not code signed.' -ForegroundColor Yellow
Write-Host 'SmartScreen will warn on first run for most users until you sign it'
Write-Host 'with an authenticode certificate and build download reputation.'

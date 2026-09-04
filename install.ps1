<#
    Sticky - shortcut installer.

    Creates a Start Menu shortcut (and optionally a Desktop one) that launches
    the app with pythonw.exe, carries the note icon, and declares the same
    AppUserModelID the app sets on itself. Matching IDs are what makes Windows
    treat the running windows and the pinned icon as one application.

    Usage:
        powershell -ExecutionPolicy Bypass -File install.ps1
        powershell -ExecutionPolicy Bypass -File install.ps1 -Desktop
        powershell -ExecutionPolicy Bypass -File install.ps1 -Uninstall

    Nothing is installed system-wide and no admin rights are needed: this only
    writes shortcut files under your own user profile.
#>

[CmdletBinding()]
param(
    [switch]$Desktop,
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'

$AppName   = 'Sticky'
$AppId     = 'Claude.Sticky'
$Root      = $PSScriptRoot
$Launcher  = Join-Path $Root 'sticky.pyw'
$IconPath  = Join-Path $Root 'assets\sticky.ico'
$StartMenu = Join-Path ([Environment]::GetFolderPath('Programs')) "$AppName.lnk"
$DesktopLnk = Join-Path ([Environment]::GetFolderPath('Desktop')) "$AppName.lnk"

# --------------------------------------------------------------- uninstall

if ($Uninstall) {
    foreach ($lnk in @($StartMenu, $DesktopLnk)) {
        if (Test-Path $lnk) {
            Remove-Item $lnk -Force
            Write-Host "removed $lnk"
        }
    }
    $runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
    if ((Get-ItemProperty -Path $runKey -Name 'Sticky' -ErrorAction SilentlyContinue)) {
        Remove-ItemProperty -Path $runKey -Name 'Sticky'
        Write-Host 'removed the start-with-Windows entry'
    }
    Write-Host ''
    Write-Host 'Shortcuts removed. Your notes are untouched, in:'
    Write-Host "  $env:APPDATA\Sticky\notes.json"
    Write-Host 'If the app was pinned, right-click the taskbar icon and unpin it.'
    return
}

# ------------------------------------------------------------------ checks

if (-not (Test-Path $Launcher) -and -not (Test-Path (Join-Path $Root 'Sticky.exe'))) {
    throw "Neither Sticky.exe nor sticky.pyw found in $Root"
}

# A packaged build is its own executable. Only fall back to hunting for a
# Python interpreter when running from source.
$FrozenExe = Join-Path $Root 'Sticky.exe'
if (Test-Path $FrozenExe) {
    $Target = $FrozenExe
    $Arguments = ''
    Write-Host "Using the built application: $Target" -ForegroundColor DarkGray
} else {
    $pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
    if (-not $pythonw) {
        $python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
        if (-not $python) { throw 'Python was not found on PATH. Install Python 3.8 or newer, or use the built release.' }
        $pythonw = Join-Path (Split-Path $python) 'pythonw.exe'
    }
    if (-not (Test-Path $pythonw)) { throw "pythonw.exe not found (looked at $pythonw)" }
    $Target = $pythonw
    $Arguments = '"{0}"' -f $Launcher

    if (-not (Test-Path $IconPath)) {
        Write-Host 'Icon missing, generating it...'
        & (Join-Path (Split-Path $pythonw) 'python.exe') (Join-Path $Root 'make_icon.py')
    }
}

# ---------------------------------------------- AppUserModelID on shortcuts

# A .lnk with no explicit AppUserModelID inherits one derived from its target.
# That target is pythonw.exe, which every other Python GUI app shares, so the
# pinned icon would group with them. Stamping our own ID fixes the grouping.
if (-not ('ShortcutAppId' -as [type])) {
    Add-Type -Language CSharp @'
using System;
using System.Runtime.InteropServices;

public static class ShortcutAppId
{
    [StructLayout(LayoutKind.Sequential, Pack = 4)]
    public struct PropertyKey { public Guid fmtid; public uint pid; }

    [ComImport, Guid("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IPropertyStore
    {
        void GetCount(out uint cProps);
        void GetAt(uint iProp, out PropertyKey pkey);
        void GetValue(ref PropertyKey key, IntPtr pv);
        void SetValue(ref PropertyKey key, IntPtr pv);
        void Commit();
    }

    [ComImport, Guid("0000010b-0000-0000-C000-000000000046"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IPersistFile
    {
        void GetClassID(out Guid pClassID);
        [PreserveSig] int IsDirty();
        void Load([MarshalAs(UnmanagedType.LPWStr)] string file, uint mode);
        void Save([MarshalAs(UnmanagedType.LPWStr)] string file,
                  [MarshalAs(UnmanagedType.Bool)] bool remember);
        void SaveCompleted([MarshalAs(UnmanagedType.LPWStr)] string file);
        void GetCurFile([MarshalAs(UnmanagedType.LPWStr)] out string file);
    }

    [ComImport, Guid("00021401-0000-0000-C000-000000000046")]
    private class ShellLink { }

    [DllImport("ole32.dll")]
    private static extern int PropVariantClear(IntPtr pvar);

    private const ushort VT_LPWSTR = 31;

    // A PROPVARIANT is a 2-byte type tag, six bytes of padding, then the value
    // union at offset 8 on both 32- and 64-bit Windows. For VT_LPWSTR the union
    // holds a CoTaskMem pointer, which PropVariantClear frees for us.
    private static void WriteStringPropVariant(IntPtr pv, string value)
    {
        for (int i = 0; i < 32; i++) Marshal.WriteByte(pv, i, 0);
        Marshal.WriteInt16(pv, 0, unchecked((short)VT_LPWSTR));
        Marshal.WriteIntPtr(pv, 8, Marshal.StringToCoTaskMemUni(value));
    }

    public static void Apply(string linkPath, string appId)
    {
        object link = new ShellLink();
        ((IPersistFile)link).Load(linkPath, 2 /* STGM_READWRITE */);

        // PKEY_AppUserModel_ID
        PropertyKey key = new PropertyKey();
        key.fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3");
        key.pid = 5;

        IntPtr pv = Marshal.AllocCoTaskMem(32);
        try
        {
            WriteStringPropVariant(pv, appId);
            IPropertyStore store = (IPropertyStore)link;
            store.SetValue(ref key, pv);
            store.Commit();
            ((IPersistFile)link).Save(linkPath, true);
        }
        finally
        {
            PropVariantClear(pv);
            Marshal.FreeCoTaskMem(pv);
            Marshal.ReleaseComObject(link);
        }
    }
}
'@
}

# ------------------------------------------------------------------ create

function New-StickyShortcut([string]$Path) {
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut($Path)
    $lnk.TargetPath = $Target
    $lnk.Arguments = $Arguments
    $lnk.WorkingDirectory = $Root
    if (Test-Path $IconPath) { $lnk.IconLocation = "$IconPath,0" } else { $lnk.IconLocation = "$Target,0" }
    $lnk.Description = 'Your notes, stuck to your desktop.'
    $lnk.Save()
    [Runtime.InteropServices.Marshal]::ReleaseComObject($shell) | Out-Null
    [ShortcutAppId]::Apply($Path, $AppId)
    Write-Host "created $Path"
}

New-StickyShortcut $StartMenu
if ($Desktop) { New-StickyShortcut $DesktopLnk }

Write-Host ''
Write-Host 'Installed.' -ForegroundColor Green
Write-Host ''
Write-Host 'To pin it to the taskbar (Windows has not allowed apps to pin themselves'
Write-Host 'since Windows 10 1607, so this last step is yours):'
Write-Host ''
Write-Host '  1. Press Start and type: Sticky'
Write-Host '  2. Right-click the result and choose Pin to taskbar.'
Write-Host ''
Write-Host 'Or launch it first, then right-click its taskbar button and pin that.'
Write-Host 'Clicking the pinned icon afterwards reopens the overview window; it'
Write-Host 'never starts a second copy.'
Write-Host ''
Write-Host "Notes are stored in $env:APPDATA\Sticky\notes.json"

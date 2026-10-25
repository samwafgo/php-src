[CmdletBinding()]
param([string]$ToolsRoot = 'C:\php56-vc11')

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'VC11 setup must run on Windows; use the supplied GitHub windows-2022 workflow' }
$principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'The Windows toolchain installer requires an elevated administrator process'
}
$ToolsRoot = [IO.Path]::GetFullPath($ToolsRoot)
$downloads = Join-Path $ToolsRoot 'downloads'
$logs = Join-Path $ToolsRoot 'logs'
New-Item -ItemType Directory -Force $ToolsRoot,$downloads,$logs | Out-Null
$lock = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'downloads.json') -Raw | ConvertFrom-Json
$files = @{}
foreach ($asset in $lock.assets) {
    $uri = [Uri]$asset.url
    if ($uri.Scheme -ne 'https' -or $uri.Host -notin @('download.microsoft.com','downloads.php.net')) { throw 'Unexpected download host' }
    if ([IO.Path]::GetFileName($asset.filename) -ne $asset.filename) { throw 'Invalid download filename' }
    $path = Join-Path $downloads $asset.filename
    if (-not (Test-Path -LiteralPath $path)) {
        Write-Host "Downloading official asset: $($asset.filename)"
        $part = $path + '.part'
        & curl.exe --fail --location --retry 3 --connect-timeout 30 --max-time 1800 --output $part $asset.url
        if ($LASTEXITCODE -ne 0) { throw "Download failed: $($asset.filename)" }
        $null = Assert-FileHash $part $asset.sha256
        Move-Item -LiteralPath $part -Destination $path -Force
    }
    $null = Assert-FileHash $path $asset.sha256
    $files[$asset.id] = $path
}

$sdk = Join-Path $ToolsRoot 'php-sdk'
Expand-WithSevenZip $files['php_sdk'] $sdk (Join-Path $logs 'extract-sdk.log')
$sdkBin = Join-Path $sdk 'bin'
if (-not (Test-Path -LiteralPath (Join-Path $sdkBin 'bison.exe'))) { throw 'Official SDK did not contain bin/bison.exe' }
$deps = @{}
foreach ($arch in @('x86','x64')) {
    $destination = Join-Path $ToolsRoot ('deps-' + $arch)
    Expand-WithSevenZip $files[('deps_' + $arch)] $destination (Join-Path $logs ('extract-deps-' + $arch + '.log'))
    $depRoot = Join-Path $destination 'deps'
    if (-not (Test-Path -LiteralPath (Join-Path $depRoot 'include'))) { throw "Missing include directory in $arch deps" }
    if (-not (Test-Path -LiteralPath (Join-Path $depRoot 'lib'))) { throw "Missing lib directory in $arch deps" }
    $deps[$arch] = $depRoot
}

$vcvars = Get-Vc11Vars
$installExit = $null
$signatureStatus = 'existing compiler installation'
if (-not $vcvars) {
    $media = Join-Path $ToolsRoot 'vs2012-media'
    Expand-WithSevenZip $files['vc11_iso'] $media (Join-Path $logs 'extract-vc11-media.log')
    $installer = Join-Path $media 'wdexpress_full.exe'
    $null = Assert-FileHash $installer '7f1603afef35d3014cbdfa307d5575b8b5da6f85ddddca8ae512a765df639319'
    $signature = Get-AuthenticodeSignature -LiteralPath $installer
    $signatureStatus = [string]$signature.Status
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Microsoft Corporation') {
        throw "Microsoft installer Authenticode validation failed: $signatureStatus"
    }
    Write-Host 'Installing Visual Studio Express 2012 for Windows Desktop (VC11)'
    $setupLog = Join-Path $logs 'vs2012-setup.log'
    # VS2012 uses slash switches, unlike the modern VS --quiet syntax.
    # Full offline media provides the compiler, CRT and Windows SDK payloads.
    $installExit = Invoke-LoggedProcess -FilePath $installer `
        -Arguments @('/quiet','/norestart','/log',('"'+$setupLog+'"')) `
        -Log (Join-Path $logs 'vs2012-console.log') -WorkingDirectory $media `
        -TimeoutSeconds 2700 -AllowedExitCodes @(0,3010)
    $vcvars = Get-Vc11Vars
    if (-not $vcvars) { throw "Installer returned $installExit but VC11 vcvarsall.bat is missing; inspect setup logs" }
}

$smoke = Join-Path $ToolsRoot 'compiler-smoke'
$studioRoot = Split-Path -Parent (Split-Path -Parent $vcvars)
$commonTools = (Join-Path $studioRoot 'Common7\Tools') + '\'
New-Item -ItemType Directory -Force $smoke | Out-Null
$source = Join-Path $smoke 'compiler.c'
@'
#include <stdio.h>
#if _MSC_VER != 1700
#error This build requires the VC11 compiler
#endif
#if EXPECT_X64
#ifndef _M_X64
#error Expected x64 compiler target
#endif
#else
#ifndef _M_IX86
#error Expected x86 compiler target
#endif
#endif
int main(void) { printf("VC11-%u\n", (unsigned)(sizeof(void *)*8)); return 0; }
'@ | Set-Content -LiteralPath $source -Encoding ASCII
foreach ($arch in @('x86','x64')) {
    $vcTarget = if ($arch -eq 'x64') { 'x86_amd64' } else { 'x86' }
    $expect = if ($arch -eq 'x64') { '1' } else { '0' }
    $exe = Join-Path $smoke ('compiler-' + $arch + '.exe')
    $batch = Join-Path $smoke ('compiler-' + $arch + '.cmd')
    Write-CmdBatch $batch @(
        '@echo off',
        ('set "VS110COMNTOOLS='+$commonTools+'"'),
        'set "VisualStudioVersion=11.0"',
        ('call "'+$vcvars+'" '+$vcTarget+' || exit /b 1'),
        ('set "PATH='+$sdkBin+';%PATH%"'),
        ('set "BISON_SIMPLE='+$sdkBin+'\bison.simple"'),
        'where cl || exit /b 1', 'where nmake || exit /b 1',
        'bison --version || exit /b 1',
        ('cl /nologo /MD /DEXPECT_X64='+$expect+' "'+$source+'" /Fe:"'+$exe+'" || exit /b 1'),
        ('"'+$exe+'" || exit /b 1'), 'exit /b 0'
    )
    $null = Invoke-CmdBatch $batch (Join-Path $logs ('compiler-' + $arch + '.log')) $smoke 120
    if ((Get-PeArchitecture $exe) -ne $arch) { throw "Compiler emitted wrong architecture: $arch" }
}
$info = [ordered]@{
    schema=1; tools_root=$ToolsRoot; vcvarsall=$vcvars; sdk_bin=$sdkBin; vs110_common_tools=$commonTools;
    deps_x86=$deps['x86']; deps_x64=$deps['x64'];
    installer_exit_code=$installExit; installer_signature=$signatureStatus;
    compiler_smoke_x86='PASS'; compiler_smoke_x64='PASS';
    downloads=$lock.assets; windows_version=[Environment]::OSVersion.VersionString;
    limitations='VC11 RTM from official Express Desktop media; actual PHP verification occurs in subsequent build steps'
}
$info | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $ToolsRoot 'toolchain.json') -Encoding UTF8
Write-Host 'VC11, x86/x64 compiler targets, CRT execution, PHP SDK and matching dependencies are ready'

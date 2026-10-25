[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidateSet('x86','x64')][string]$Arch,
    [Parameter(Mandatory=$true)][ValidateSet('ts','nts')][string]$Threading,
    [string]$ToolsRoot='C:\php56-vc11', [string]$WorkRoot='C:\php56-work'
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'Windows build requires Windows' }
$repo=(Get-Location).Path
$key=$Arch+'-'+$Threading
$out=Join-Path $repo ('artifacts\windows\'+$key)
$evidence=Join-Path $out 'evidence'
$binaryOut=Join-Path $out 'binaries'
New-Item -ItemType Directory -Force $evidence | Out-Null
$status=[ordered]@{ configuration=$key; status='STARTED'; cve_security_validation='not performed' }
try {
    $tools=Get-Content -LiteralPath (Join-Path $ToolsRoot 'toolchain.json') -Raw | ConvertFrom-Json
    if ($tools.compiler_smoke_x86 -ne 'PASS' -or $tools.compiler_smoke_x64 -ne 'PASS') { throw 'Compiler probes did not pass' }
    $work=Join-Path $WorkRoot $key
    $source=Join-Path $work 'source'
    if (Test-Path -LiteralPath $work) { throw "Build work directory already exists: $work" }
    New-Item -ItemType Directory -Force $source | Out-Null
    $archive=Join-Path $work 'source.zip'
    & git archive --format=zip --output=$archive HEAD
    if ($LASTEXITCODE -ne 0) { throw 'git archive failed' }
    Expand-Archive -LiteralPath $archive -DestinationPath $source
    $deps=if ($Arch -eq 'x64') { $tools.deps_x64 } else { $tools.deps_x86 }
    $vcTarget=if ($Arch -eq 'x64') { 'x86_amd64' } else { 'x86' }
    $zts=if ($Threading -eq 'ts') { '--enable-zts' } else { '--disable-zts' }
    $batch=Join-Path $work 'build.cmd'
    Write-CmdBatch $batch @(
        '@echo off', ('cd /d "'+$source+'" || exit /b 1'),
        ('set "VS110COMNTOOLS='+$tools.vs110_common_tools+'"'),
        'set "VisualStudioVersion=11.0"',
        ('call "'+$tools.vcvarsall+'" '+$vcTarget+' || exit /b 1'),
        ('set "PATH='+$tools.sdk_bin+';%PATH%"'),
        ('set "BISON_SIMPLE='+$tools.sdk_bin+'\bison.simple"'),
        'where cl || exit /b 1', 'where nmake || exit /b 1',
        'bison --version || exit /b 1',
        'call buildconf.bat || exit /b 1',
        'if not exist configure.js exit /b 1',
        ('cscript //nologo configure.js --disable-all --enable-cli --enable-cgi --enable-session '+$zts+' --with-php-build="'+$deps+'" || exit /b 1'),
        'nmake || exit /b 1', 'exit /b 0'
    )
    $null=Invoke-CmdBatch $batch (Join-Path $evidence 'build.log') $source 1800
    $suffix=if ($Threading -eq 'ts') { 'Release_TS' } else { 'Release' }
    $release=if ($Arch -eq 'x64') { Join-Path $source ('x64\'+$suffix) } else { Join-Path $source $suffix }
    $stage=Join-Path $work 'package'
    New-Item -ItemType Directory -Force $stage | Out-Null
    foreach ($file in @('php.exe','php-cgi.exe')) {
        Copy-Item -LiteralPath (Join-Path $release $file) -Destination $stage
    }
    Get-ChildItem -LiteralPath $release -File -Filter '*.dll' | Copy-Item -Destination $stage
    Copy-Item -LiteralPath (Join-Path $source 'LICENSE') -Destination $stage
    Copy-Item -LiteralPath (Join-Path $source 'php.ini-production') -Destination (Join-Path $stage 'php.ini.example')
    $verification=Join-Path $evidence 'verification.json'
    & python (Join-Path $PSScriptRoot 'verify_windows.py') --package $stage --arch $Arch --threading $Threading --output $verification
    if ($LASTEXITCODE -ne 0) { throw 'Staged Windows binary verification failed' }
    $commit=(& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Cannot determine source commit' }
    $files=[ordered]@{}
    Get-ChildItem -LiteralPath $stage -File | ForEach-Object {
        $files[$_.Name]=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $manifest=[ordered]@{
        version='5.6.40-sec1'; upstream_base='5.6.40'; source_commit=$commit;
        platform='Windows'; arch=$Arch; threading=$Threading; compiler='VC11'; profile='core'; status='candidate';
        toolchain=$tools; verification=(Get-Content -LiteralPath $verification -Raw | ConvertFrom-Json);
        cve_security_validation='not performed'; runtime_requirement='Visual C++ 2012 Runtime matching package architecture';
        omissions=@('openssl','curl','gd','zip','third-party loaders','Apache module');
        limitations=@('Limited core CLI/CGI build','No full PHPT, IIS, Apache or exploit regression','Session upload progress disabled in C');
        files=$files
    }
    $manifest | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $stage 'MANIFEST.json') -Encoding UTF8
    Copy-Item -LiteralPath $verification -Destination $stage
    @'
Unofficial PHP 5.6.40-sec1 Windows core candidate.
Contains CLI, CGI, matching PHP DLL, LICENSE and a configuration example.
Install the matching x86/x64 Microsoft Visual C++ 2012 runtime before deployment.
Core-only: OpenSSL, cURL, GD, ZIP, third-party loaders and Apache module are absent.
This package passed the checks recorded in verification.json, not a complete CVE or production acceptance.
'@ | Set-Content -LiteralPath (Join-Path $stage 'README.txt') -Encoding UTF8
    New-Item -ItemType Directory -Force $binaryOut | Out-Null
    $name='php-5.6.40-sec1-windows-vc11-'+$Arch+'-'+$Threading+'-core-candidate.zip'
    $zip=Join-Path $binaryOut $name
    Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zip
    $hash=(Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
    ($hash+'  '+$name) | Set-Content -LiteralPath (Join-Path $binaryOut 'SHA256SUMS') -Encoding ASCII
    Copy-Item -LiteralPath (Join-Path $stage 'MANIFEST.json') -Destination $binaryOut
    $status['status']='PASS'
    $status['binary']=$name
    $status['sha256']=$hash
} catch {
    $status['status']='FAIL'
    $status['error']=$_.Exception.Message
    throw
} finally {
    $status | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $evidence 'status.json') -Encoding UTF8
}

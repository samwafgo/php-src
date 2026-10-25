$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
$errorsFound=@()
Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.ps1' -File | ForEach-Object {
    $tokens=$null; $parseErrors=$null
    [Management.Automation.Language.Parser]::ParseFile($_.FullName,[ref]$tokens,[ref]$parseErrors) | Out-Null
    if ($parseErrors) { $errorsFound += $parseErrors }
}
if ($errorsFound) { throw ($errorsFound | Out-String) }
$temp=Join-Path ([IO.Path]::GetTempPath()) ('php56-script-tests-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $temp | Out-Null
try {
    $file=Join-Path $temp 'sample.bin'
    [IO.File]::WriteAllBytes($file,[Text.Encoding]::ASCII.GetBytes('sample'))
    $hash=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash
    $null=Assert-FileHash $file $hash
    $rejected=$false
    try { $null=Assert-FileHash $file ('0'*64) } catch { $rejected=$true }
    if (-not $rejected) { throw 'Hash mismatch was accepted' }
    foreach ($arch in @('x86','x64')) {
        $bytes=New-Object byte[] 256
        $bytes[0]=0x4d; $bytes[1]=0x5a
        [BitConverter]::GetBytes([int]128).CopyTo($bytes,0x3c)
        $bytes[128]=0x50; $bytes[129]=0x45
        $machine=if ($arch -eq 'x64') { [uint16]0x8664 } else { [uint16]0x14c }
        [BitConverter]::GetBytes($machine).CopyTo($bytes,132)
        [IO.File]::WriteAllBytes($file,$bytes)
        if ((Get-PeArchitecture $file) -ne $arch) { throw 'PE architecture parsing failed' }
    }
    [IO.File]::WriteAllBytes($file,[Text.Encoding]::ASCII.GetBytes('not a PE'))
    $rejected=$false
    try { $null=Get-PeArchitecture $file } catch { $rejected=$true }
    if (-not $rejected) { throw 'Non-PE file was accepted' }
    if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
        $exe=$env:ComSpec; $good=@('/d','/c','echo','process-ok'); $bad=@('/d','/c','exit','7')
    } else {
        $exe='/bin/sh'; $good=@('-c','true'); $bad=@('-c','false')
    }
    $null=Invoke-LoggedProcess -FilePath $exe -Arguments $good -Log (Join-Path $temp 'success.log') -WorkingDirectory $temp
    $rejected=$false
    try { $null=Invoke-LoggedProcess -FilePath $exe -Arguments $bad -Log (Join-Path $temp 'failure.log') -WorkingDirectory $temp } catch { $rejected=$true }
    if (-not $rejected) { throw 'Nonzero process exit was accepted' }
    Write-Host 'PowerShell AST, download hash, PE architecture and process failure checks PASS'
} finally { [IO.Directory]::Delete($temp,$true) }

Set-StrictMode -Version Latest

function Assert-FileHash {
    param([string]$Path, [string]$Expected)
    if ($Expected -notmatch '^[a-fA-F0-9]{64}$') { throw 'Invalid SHA256 in download lock' }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing file: $Path" }
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $Expected.ToLowerInvariant()) { throw "SHA256 mismatch: $Path" }
    return $actual
}

function Get-PeArchitecture {
    param([string]$Path)
    $stream = [IO.File]::OpenRead($Path)
    $reader = [IO.BinaryReader]::new($stream)
    try {
        if ($stream.Length -lt 64 -or $reader.ReadUInt16() -ne 0x5a4d) { throw "Not a PE file: $Path" }
        $stream.Position = 0x3c
        $offset = $reader.ReadInt32()
        if ($offset -lt 64 -or ($offset + 6) -gt $stream.Length) { throw "Bad PE offset: $Path" }
        $stream.Position = $offset
        if ($reader.ReadUInt32() -ne 0x4550) { throw "Missing PE signature: $Path" }
        switch ($reader.ReadUInt16()) {
            0x14c { return 'x86' }
            0x8664 { return 'x64' }
            default { throw "Unsupported PE architecture: $Path" }
        }
    } finally { $reader.Dispose(); $stream.Dispose() }
}

function Invoke-LoggedProcess {
    param(
        [string]$FilePath, [string[]]$Arguments, [string]$Log,
        [string]$WorkingDirectory, [int]$TimeoutSeconds = 1800,
        [int[]]$AllowedExitCodes = @(0)
    )
    New-Item -ItemType Directory -Force (Split-Path -Parent $Log) | Out-Null
    $params = @{
        FilePath=$FilePath; ArgumentList=$Arguments; PassThru=$true;
        RedirectStandardOutput=$Log; RedirectStandardError=($Log + '.stderr');
        WorkingDirectory=$WorkingDirectory
    }
    $process = Start-Process @params
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
            & taskkill.exe /PID $process.Id /T /F | Out-Null
        } else { $process.Kill() }
        throw "Process timed out; see $Log"
    }
    $process.WaitForExit()
    $code = $process.ExitCode
    if ($code -notin $AllowedExitCodes) {
        foreach ($file in @($Log, ($Log + '.stderr'))) {
            if (Test-Path -LiteralPath $file) { Get-Content -LiteralPath $file -Tail 60 | Write-Host }
        }
        throw "Process failed ($code): $FilePath; see $Log"
    }
    return $code
}

function Invoke-CmdBatch {
    param([string]$Batch, [string]$Log, [string]$WorkingDirectory, [int]$TimeoutSeconds=1800)
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'CMD requires Windows' }
    return Invoke-LoggedProcess -FilePath $env:ComSpec -Arguments @('/d','/c','call',('"'+$Batch+'"')) `
        -Log $Log -WorkingDirectory $WorkingDirectory -TimeoutSeconds $TimeoutSeconds
}

function Get-SevenZip {
    $command = Get-Command 7z.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $path = Join-Path $env:ProgramFiles '7-Zip\7z.exe'
    if (Test-Path -LiteralPath $path) { return $path }
    throw '7-Zip is missing; this automatic workflow targets the windows-2022 hosted image'
}

function Expand-WithSevenZip {
    param([string]$Archive, [string]$Destination, [string]$Log)
    New-Item -ItemType Directory -Force $Destination | Out-Null
    $zip = Get-SevenZip
    $null = Invoke-LoggedProcess -FilePath $zip -Arguments @('x',('"'+$Archive+'"'),('-o"'+$Destination+'"'),'-y','-bsp0') `
        -Log $Log -WorkingDirectory $Destination -TimeoutSeconds 900
}

function Get-Vc11Vars {
    $roots = @(
        [Environment]::GetEnvironmentVariable('ProgramFiles(x86)'),
        [Environment]::GetEnvironmentVariable('ProgramFiles')
    ) | Where-Object { $_ }
    foreach ($root in $roots) {
        $file = Join-Path $root 'Microsoft Visual Studio 11.0\VC\vcvarsall.bat'
        if (Test-Path -LiteralPath $file) { return $file }
    }
    return $null
}

function Write-CmdBatch {
    param([string]$Path, [string[]]$Lines)
    # cmd.exe has no UTF-8 requirement; generated batches contain ASCII paths.
    [IO.File]::WriteAllText($Path, (($Lines -join "`r`n") + "`r`n"), [Text.Encoding]::ASCII)
}

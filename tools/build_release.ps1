<#
.SYNOPSIS
    Build the full Inventaur Inc. Rhino3D-to-Solid-Edge bootstrap distribution.
.DESCRIPTION
    Packages first-party workflow sources, self-contained Solid Edge MCP runtime binaries,
    the bundled Rhino MCP Yak package, third-party notices, tests and operator documentation.
.AUTHOR Krishna Parmar
.COMPANY Inventaur Inc.
#>
[CmdletBinding()]
param([string]$Version = '', [switch]$SkipTests)
$ErrorActionPreference = 'Stop'
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $Version) { $Version = (Get-Content -Raw (Join-Path $RepositoryRoot 'VERSION')).Trim() }
if ($Version -notmatch '^[0-9A-Za-z.+-]+$') { throw "Invalid version: $Version" }
$Python = Get-Command python.exe -ErrorAction SilentlyContinue
if (-not $Python) { throw 'Python 3.11+ x64 is required to run release tests.' }
$pyver = & $Python.Source -c "import sys,struct;print('%d.%d|%d'%(sys.version_info.major,sys.version_info.minor,struct.calcsize('P')*8))"
if ($LASTEXITCODE -ne 0 -or $pyver -notmatch '^(\d+)\.(\d+)\|64$' -or ([int]$Matches[1] -lt 3 -or ([int]$Matches[1] -eq 3 -and [int]$Matches[2] -lt 11))) {
    throw "Python 3.11+ x64 is required. Found $pyver"
}
if (-not $SkipTests) {
    Write-Host 'Running Inventaur regression suite...'
    & $Python.Source -m pytest -q (Join-Path $RepositoryRoot 'tests')
    if ($LASTEXITCODE -ne 0) { throw 'Python regression tests failed.' }
    & $Python.Source -m compileall -q (Join-Path $RepositoryRoot 'Scripts') (Join-Path $RepositoryRoot 'tests')
    if ($LASTEXITCODE -ne 0) { throw 'Python compileall failed.' }
}

$PackageName = 'Inventaur_Inc_Rhino3D_to_SolidEdge_Workflow'
$DistRoot = Join-Path $RepositoryRoot 'dist'
$StageParent = Join-Path $DistRoot '_staging'
$StageRoot = Join-Path $StageParent $PackageName
$ZipPath = Join-Path $DistRoot ("{0}_{1}.zip" -f $PackageName,$Version)
$Runtime = Join-Path $RepositoryRoot 'Scripts\SOLIDEDGE-MCP\runtime\win-x64'
$YakPackage = Join-Path $RepositoryRoot 'ThirdParty\RhinoAI\rhino-mcp-platform-0.4.0-rh8_19-win.yak'
$PythonRoot = Join-Path $RepositoryRoot 'Runtime\Python'
$Wheelhouse = Join-Path $RepositoryRoot 'Runtime\Wheels'
foreach ($path in @((Join-Path $Runtime 'control\solidedge-mcp.exe'),(Join-Path $Runtime 'events\solidedge-event-mcp.exe'),(Join-Path $Runtime 'control\coreclr.dll'),(Join-Path $Runtime 'events\coreclr.dll'),(Join-Path $PythonRoot 'python.exe'),(Join-Path $PythonRoot 'python313.dll'),(Join-Path $PythonRoot 'Lib\venv\__init__.py'),(Join-Path $PythonRoot 'Lib\ensurepip\__init__.py'),(Join-Path $Wheelhouse 'psutil-7.2.2-cp37-abi3-win_amd64.whl'),(Join-Path $Wheelhouse 'pywin32-312-cp313-cp313-win_amd64.whl'),$YakPackage)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Full bootstrap payload missing: $path" }
}
if (Test-Path $StageRoot) { Remove-Item $StageRoot -Recurse -Force }
New-Item -ItemType Directory -Path $StageRoot -Force | Out-Null

$RootFiles = @('README.md','PROJECT_IDENTITY.md','README_RELEASE_NOTES.md','AGENTS.md','CHANGELOG.md','DEPENDENCY_MAP.json','THIRD_PARTY_NOTICES.md','LICENSE_PENDING.txt','VERSION','Inventaur_Install.ps1','INSTALL.bat','requirements.txt','requirements-dev.txt','pyproject.toml','inventaur_rhino3d_to_solidedge.py','.gitignore','.gitattributes','.editorconfig')
foreach ($name in $RootFiles) {
    $source = Join-Path $RepositoryRoot $name
    if (Test-Path -LiteralPath $source -PathType Leaf) { Copy-Item -LiteralPath $source -Destination $StageRoot -Force }
}
foreach ($directory in @('Docs','Scripts','tests','.github','ThirdParty','Runtime')) {
    $source = Join-Path $RepositoryRoot $directory
    if (-not (Test-Path -LiteralPath $source -PathType Container)) { continue }
    if ($directory -eq 'Scripts') {
        $destination = Join-Path $StageRoot 'Scripts'
        New-Item -ItemType Directory -Path $destination -Force | Out-Null
        Get-ChildItem -LiteralPath $source -Force | Where-Object { $_.Name -notin @('__pycache__','.pytest_cache','.git','bin','obj') } | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $destination -Recurse -Force
        }
    } elseif ($directory -eq 'Runtime') {
        # Copy the portable interpreter as a runtime payload, not a Python developer/test installation.
        # The stdlib test suite and any local site-packages are not needed by the conversion workflow.
        $destination = Join-Path $StageRoot 'Runtime'
        $excluded = @(
            (Join-Path $source 'Python\Lib\test'),
            (Join-Path $source 'Python\Lib\site-packages')
        )
        $copyArgs = @($source,$destination,'/E','/R:1','/W:1','/NFL','/NDL','/NJH','/NJS','/NC','/NS','/NP','/XD') + $excluded + @('/XF','*.pyc','*.pyo')
        & robocopy.exe @copyArgs
        $copyCode = $LASTEXITCODE
        if ($copyCode -ge 8) { throw "Bundled Python/wheelhouse copy failed (robocopy exit code $copyCode)." }
        Write-Host "Copied portable Python runtime and offline wheels (robocopy $copyCode)."
    } else {
        Copy-Item -LiteralPath $source -Destination $StageRoot -Recurse -Force
    }
}

# Remove caches/build by-products only. Self-contained executable/runtime DLLs and the Yak plugin stay bundled.
foreach ($name in @('__pycache__','.pytest_cache','.git','.venv','bin','obj')) {
    Get-ChildItem -LiteralPath $StageRoot -Directory -Recurse -Force | Where-Object Name -eq $name | Sort-Object { $_.FullName.Length } -Descending | ForEach-Object {
        if (Test-Path -LiteralPath $_.FullName) { Remove-Item -LiteralPath $_.FullName -Recurse -Force }
    }
}
Get-ChildItem -LiteralPath $StageRoot -File -Recurse -Force | Where-Object {
    $_.Extension.ToLowerInvariant() -in @('.pyc','.pyo','.pdb','.log','.sqlite','.3dm','.3dmbak','.par','.asm','.dft','.step','.stp','.iges','.igs','.stl','.zip')
} | Remove-Item -Force

$RuntimePrefix = ($StageRoot + '\Scripts\SOLIDEDGE-MCP\runtime\').ToLowerInvariant()
$PythonPrefix = ($StageRoot + '\Runtime\Python\').ToLowerInvariant()
$YakPrefix = ($StageRoot + '\ThirdParty\RhinoAI\').ToLowerInvariant()
foreach ($file in (Get-ChildItem -LiteralPath $StageRoot -File -Recurse -Force)) {
    $full = $file.FullName.ToLowerInvariant()
    if ($file.Extension -in @('.exe','.dll') -and -not ($full.StartsWith($RuntimePrefix) -or $full.StartsWith($PythonPrefix))) { throw "Executable/DLL is outside the bundled MCP/Python runtimes: $($file.FullName)" }
    if ($file.Extension -eq '.yak' -and -not $full.StartsWith($YakPrefix)) { throw "Unexpected Yak package outside the third-party Rhino folder: $($file.FullName)" }
}
$forbiddenCad = Get-ChildItem -LiteralPath $StageRoot -File -Recurse -Force | Where-Object { $_.Extension.ToLowerInvariant() -in @('.3dm','.3dmbak','.par','.asm','.dft','.step','.stp','.iges','.igs','.stl') }
if ($forbiddenCad) { throw "Package contains CAD/model data: $($forbiddenCad.FullName -join '; ')" }

# Reject workstation paths and obvious credentials from text assets.
$TextExtensions = @('.py','.md','.json','.yml','.yaml','.toml','.txt','.csv','.xml','.config','.nuspec','.bat','.cmd','.ps1','.cs','.csproj','.sln','.props','.targets')
$privacyPattern = 'F:\\ai\\BOT|C:\\Users\\krish|GLASSCASE'
$secretPattern = 'ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{24,}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----'
foreach ($file in (Get-ChildItem -LiteralPath $StageRoot -File -Recurse -Force)) {
    if ($file.Extension.ToLowerInvariant() -notin $TextExtensions) { continue }
    $content = [IO.File]::ReadAllText($file.FullName)
    if ($content -match $privacyPattern) { throw "Private/local workstation path found in package: $($file.FullName)" }
    if ($content -match $secretPattern) { throw "Possible secret found in package: $($file.FullName)" }
}

$manifest = Join-Path $StageRoot 'PACKAGE_MANIFEST.sha256'
$manifestLines = foreach ($file in (Get-ChildItem -LiteralPath $StageRoot -File -Recurse -Force | Sort-Object FullName)) {
    $relative = $file.FullName.Substring($StageRoot.Length + 1).Replace('\','/')
    $digest = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$digest  $relative"
}
[IO.File]::WriteAllLines($manifest,$manifestLines,(New-Object Text.UTF8Encoding($false)))
New-Item -ItemType Directory -Path $DistRoot -Force | Out-Null
if (Test-Path -LiteralPath $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force }
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::CreateFromDirectory($StageRoot,$ZipPath,[IO.Compression.CompressionLevel]::Optimal,$true)
$hash = (Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText(($ZipPath + '.sha256'),"$hash  $([IO.Path]::GetFileName($ZipPath))" + [Environment]::NewLine,(New-Object Text.UTF8Encoding($false)))
$zip = [IO.Compression.ZipFile]::OpenRead($ZipPath)
try {
    $names = @($zip.Entries | ForEach-Object { $_.FullName.Replace('\','/') })
    $required = @(
        "$PackageName/INSTALL.bat",
        "$PackageName/Runtime/Python/python.exe",
        "$PackageName/Runtime/Python/python313.dll",
        "$PackageName/Runtime/Wheels/psutil-7.2.2-cp37-abi3-win_amd64.whl",
        "$PackageName/Runtime/Wheels/pywin32-312-cp313-cp313-win_amd64.whl",
        "$PackageName/Inventaur_Install.ps1",
        "$PackageName/Scripts/Rhino3D_to_SolidEdge.bat",
        "$PackageName/Scripts/Inventaur_Rhino3D_to_SolidEdge.bat",
        "$PackageName/Scripts/SOLIDEDGE-MCP/runtime/win-x64/control/solidedge-mcp.exe",
        "$PackageName/Scripts/SOLIDEDGE-MCP/runtime/win-x64/events/solidedge-event-mcp.exe",
        "$PackageName/Scripts/SOLIDEDGE-MCP/runtime/win-x64/control/coreclr.dll",
        "$PackageName/Scripts/SOLIDEDGE-MCP/runtime/win-x64/events/coreclr.dll",
        "$PackageName/ThirdParty/RhinoAI/rhino-mcp-platform-0.4.0-rh8_19-win.yak",
        "$PackageName/ThirdParty/SolidEdge-MCP/LICENSE",
        "$PackageName/ThirdParty/SolidEdge-MCP/UPSTREAM.md",
        "$PackageName/ThirdParty/DotNet/SolidEdge-MCP-Server-LICENSE.txt",
        "$PackageName/Docs/BOOTSTRAP_AND_DEPLOYMENT.md"
    )
    foreach ($item in $required) { if ($item -notin $names) { throw "Required bootstrap archive entry missing: $item" } }
    foreach ($line in $manifestLines) {
        $relative = ($line -split '  ',2)[1]
        if ("$PackageName/$relative" -notin $names) { throw "Manifest entry missing from archive: $relative" }
    }
    if ($names | Where-Object { $_ -match '(^|/)(\.git|__pycache__|\.pytest_cache|\.venv|_local)/|\.(pyc|pdb|3dm|par|asm|step|stp)$' }) { throw 'A cache, debug symbol, or CAD model remains in the release archive.' }
} finally { $zip.Dispose() }
$size = (Get-Item -LiteralPath $ZipPath).Length
Write-Host "FULL BOOTSTRAP PACKAGE CREATED: $ZipPath" -ForegroundColor Green
Write-Host "SHA-256: $hash"
Write-Host "Files: $($manifestLines.Count)"
Write-Host ("ZIP size: {0:N2} MiB" -f ($size / 1MB))
Write-Host 'Included: first-party sources, self-contained .NET MCP control/event runtimes, local Rhino MCP Yak package, Python bootstrap and third-party notices.'

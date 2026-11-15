<#
.SYNOPSIS
    Full Inventaur Inc. bootstrap for Rhino3D-to-Solid-Edge automation.
.DESCRIPTION
    Installs the package-local Python environment, verifies bundled self-contained Solid Edge MCP servers,
    and installs the bundled Rhino MCP Yak package. No Git or .NET SDK/runtime is required.
.AUTHOR Krishna Parmar
.COMPANY Inventaur Inc.
#>
[CmdletBinding()]
param([switch]$NoPause)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path $PSScriptRoot).Path
$Scripts = Join-Path $Root 'Scripts'
$McpRoot = Join-Path $Scripts 'SOLIDEDGE-MCP'
$RuntimeRoot = Join-Path $McpRoot 'runtime\win-x64'
$ControlDir = Join-Path $RuntimeRoot 'control'
$EventDir = Join-Path $RuntimeRoot 'events'
$Venv = Join-Path $Root '.venv'
$PythonRuntime = Join-Path $Root 'Runtime\Python'
$Wheelhouse = Join-Path $Root 'Runtime\Wheels'
$Requirements = Join-Path $Root 'requirements.txt'
$YakPackage = Join-Path $Root 'ThirdParty\RhinoAI\rhino-mcp-platform-0.4.0-rh8_19-win.yak'

function Write-Section([string]$Text) {
    Write-Host ''
    Write-Host ('=== ' + $Text + ' ===') -ForegroundColor Cyan
}
function Invoke-Checked([string]$Exe, [string[]]$Arguments, [string]$Failure) {
    & $Exe @Arguments
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw "$Failure (exit code $code)." }
}
function Get-PythonCandidate {
    $candidate = Join-Path $PythonRuntime 'python.exe'
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        throw "Bundled CPython runtime is missing: $candidate. Re-extract the complete bootstrap package."
    }
    $identity = & $candidate -I -c 'import sys,struct; print(sys.version_info[0],sys.version_info[1],struct.calcsize(chr(80))*8,sep=chr(124))' 2>$null
    if ($LASTEXITCODE -ne 0 -or $identity -notmatch '^3\|13\|64$') {
        throw "Bundled Python must be CPython 3.13 x64. Runtime reported: $identity"
    }
    return $candidate
}
function Assert-SelfContainedRuntime([string]$Directory, [string]$ExeName) {
    foreach ($name in @($ExeName,'coreclr.dll','hostfxr.dll','hostpolicy.dll','System.Private.CoreLib.dll')) {
        $path = Join-Path $Directory $name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Bundled MCP runtime is incomplete. Missing: $path" }
    }
    $exe = Join-Path $Directory $ExeName
    $versionOutput = & $exe --version 2>&1
    $code = $LASTEXITCODE
    if ($code -ne 0 -or -not ($versionOutput -match 'v\d+\.\d+')) {
        throw "Bundled MCP executable failed its startup/version check: $exe`n$versionOutput"
    }
    Write-Host ("Verified: " + $versionOutput)
}

if (-not [Environment]::Is64BitOperatingSystem) { throw 'This package requires 64-bit Windows 10/11.' }
foreach ($required in @((Join-Path $PythonRuntime 'python.exe'),(Join-Path $Wheelhouse 'psutil-7.2.2-cp37-abi3-win_amd64.whl'),(Join-Path $Wheelhouse 'pywin32-312-cp313-cp313-win_amd64.whl'),$Requirements,(Join-Path $Scripts 'inventaur_rhino3d_to_solidedge.py'),(Join-Path $Scripts 'inventaur_run_rhino3d_to_solidedge.py'),(Join-Path $McpRoot 'inventaur_bridge_client.py'),(Join-Path $McpRoot 'inventaur_bridge_daemon.py'),$YakPackage)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Required package file missing: $required" }
}
Write-Host 'Inventaur Inc. - Rhino3D to Solid Edge | Full Bootstrap | by Krishna Parmar'

Write-Section 'Bundled Solid Edge MCP runtime'
Assert-SelfContainedRuntime $ControlDir 'solidedge-mcp.exe'
Assert-SelfContainedRuntime $EventDir 'solidedge-event-mcp.exe'
Write-Host 'Both MCP servers include their own .NET runtime. No .NET SDK, global .NET runtime, Git clone or source build is required.'

Write-Section 'Bundled Python environment (offline)'
$BasePython = Get-PythonCandidate
Write-Host ("Bundled Python: " + $BasePython)
$env:PYTHONNOUSERSITE = '1'
$VenvPython = Join-Path $Venv 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $VenvPython)) { Invoke-Checked $BasePython @('-m','venv',$Venv) 'Could not create the package-local Python environment' }
if (-not (Test-Path -LiteralPath $VenvPython)) { throw "Python virtual environment creation did not produce $VenvPython" }
Invoke-Checked $VenvPython @('-m','pip','install','--disable-pip-version-check','--no-index','--find-links',$Wheelhouse,'-r',$Requirements) 'Offline workflow dependency installation failed'
Invoke-Checked $VenvPython @('-I','-c','import sys,struct,psutil,pythoncom,pywintypes,win32gui,win32con,win32com.client; assert sys.version_info >= (3,13); assert struct.calcsize(chr(80)) == 8; print(sys.version)') 'Python dependency verification failed'

Write-Section 'Rhino MCP plugin (bundled local Yak package)'
$programRoots = @($env:ProgramFiles,[Environment]::GetEnvironmentVariable('ProgramFiles(x86)')) | Where-Object { $_ } | Select-Object -Unique
$rhinoSystems = @()
foreach ($base in $programRoots) {
    foreach ($major in @(8,9)) {
        $system = Join-Path $base ("Rhino {0}\System" -f $major)
        if (Test-Path (Join-Path $system 'Rhino.exe')) { $rhinoSystems += $system }
    }
}
if (-not $rhinoSystems) { throw 'Rhino 8.19+ or Rhino 9 was not detected. Install Rhino before running this bootstrap.' }
$installedYak = 0
foreach ($system in ($rhinoSystems | Select-Object -Unique)) {
    $yak = Join-Path $system 'Yak.exe'
    if (-not (Test-Path -LiteralPath $yak)) { Write-Warning "Yak.exe not found for Rhino at $system; plugin install skipped for this installation."; continue }
    $versionText = (& $yak version 2>&1 | Out-String).Trim()
    if ($versionText -match 'Rhino 8\.') {
        $rhinoVersion = [regex]::Match($versionText,'Rhino\s+(\d+\.\d+)').Groups[1].Value
        if ($rhinoVersion -and [version]$rhinoVersion -lt [version]'8.19') { Write-Warning "Bundled Rhino MCP package requires Rhino 8.19+; skipping $versionText"; continue }
    }
    $listText = (& $yak list 2>&1 | Out-String)
    if ($listText -match '(?im)^\s*Rhino-MCP-Platform\s*\(0\.4\.0\)\s*$') {
        Write-Host "Rhino-MCP-Platform 0.4.0 already installed for $system"
        $installedYak++
        continue
    }
    Write-Host "Installing bundled Rhino-MCP-Platform 0.4.0 into $system"
    & $yak install $YakPackage
    $yakExit = $LASTEXITCODE
    if ($yakExit -ne 0) { throw "Yak package installation failed for $system (exit code $yakExit)." }
    $verifyText = (& $yak list 2>&1 | Out-String)
    if ($verifyText -notmatch '(?im)^\s*Rhino-MCP-Platform\s*\(0\.4\.0\)\s*$') { throw "Yak did not report Rhino-MCP-Platform 0.4.0 installed for $system." }
    $installedYak++
}
if ($installedYak -lt 1) { throw 'The Rhino MCP plugin could not be verified in any supported Rhino installation.' }
Write-Host "Rhino MCP plugin verified in $installedYak compatible Rhino installation(s). Restart Rhino after bootstrap so the plugin is loaded."

Write-Section 'Siemens Solid Edge prerequisites'
$com = Test-Path 'Registry::HKEY_CLASSES_ROOT\SolidEdge.Application\CLSID'
if (-not $com) { $com = Test-Path 'Registry::HKEY_CLASSES_ROOT\SolidEdge.Application.1\CLSID' }
if ($com) { Write-Host 'SolidEdge.Application COM registration: found' }
else { Write-Warning 'Solid Edge COM registration not found. Install/repair Siemens Solid Edge before conversion.' }
$templateCandidates = @()
foreach ($base in $programRoots) {
    $siemens = Join-Path $base 'Siemens'
    if (Test-Path $siemens) {
        $templateCandidates += Get-ChildItem $siemens -Directory -Filter 'Solid Edge *' -ErrorAction SilentlyContinue | ForEach-Object { Join-Path $_.FullName 'Template\ISO Metric\iso metric part.par' } | Where-Object { Test-Path $_ }
    }
}
if ($templateCandidates) { Write-Host ("ISO Metric Part template: " + $templateCandidates[0]) }
else { Write-Warning 'ISO Metric Part template not detected. Configure CAD_SOLID_EDGE_PART_TEMPLATE when required.' }

Write-Section 'Bootstrap verification'
Write-Host ("Workflow root: " + $Root)
Write-Host ("Python environment: " + $Venv)
Write-Host ("Bundled MCP runtime: " + $RuntimeRoot)
Write-Host ("Rhino MCP plugin installs verified: " + $installedYak)
Write-Host 'BOOTSTRAP COMPLETED. Restart Rhino, open the target .3dm, run MCPStart and MCPConnect, verify run_python, then launch Scripts\Rhino3D_to_SolidEdge.bat.' -ForegroundColor Green
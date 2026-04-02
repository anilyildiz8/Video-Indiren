param(
    [switch]$Debug,
    [switch]$Clean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-Python {
    $candidates = @(
        (Get-Command python -ErrorAction SilentlyContinue),
        (Get-Command py -ErrorAction SilentlyContinue)
    ) | Where-Object { $_ }

    foreach ($candidate in $candidates) {
        return $candidate.Source
    }

    $localPython = Join-Path $env:LOCALAPPDATA "Python\pythoncore-3.14-64\python.exe"
    if (Test-Path $localPython) {
        return $localPython
    }

    throw "Python was not found. Add Python to PATH or install it under $env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe."
}

$python = Resolve-Python
$specFile = if ($Debug) { "VideoIndiren_Debug.spec" } else { "VideoIndiren.spec" }

if (-not (Test-Path $specFile)) {
    throw "Spec file not found: $specFile"
}

if ($Clean) {
    if (Test-Path "build") {
        Remove-Item -Recurse -Force "build"
    }
    if (Test-Path "dist") {
        Remove-Item -Recurse -Force "dist"
    }
}

Write-Host "Using Python: $python"
Write-Host "Using spec: $specFile"

& $python -m pip install -r requirements.txt pyinstaller
if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed."
}

& $python -m PyInstaller --clean $specFile
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

Write-Host "Build complete. Output is in dist."

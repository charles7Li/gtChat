param(
    [switch]$Clean,
    [string]$DistPath = "dist/windows",
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot ".."))
Set-Location $repo

& $Python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is not installed for $Python. Run: $Python -m pip install pyinstaller"
}

if ($Clean) {
    foreach ($path in @("build", $DistPath)) {
        $resolved = Join-Path $repo $path
        if (Test-Path -LiteralPath $resolved) {
            Remove-Item -LiteralPath $resolved -Recurse -Force
        }
    }
}

New-Item -ItemType Directory -Force -Path (Join-Path $repo $DistPath) | Out-Null
& $Python -m PyInstaller packaging/mochi-scout.spec --noconfirm --clean --distpath $DistPath --workpath build/windows
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

$exe = Join-Path $repo "$DistPath/mochi-scout/mochi-scout.exe"
if (-not (Test-Path -LiteralPath $exe)) { throw "Expected executable was not produced: $exe" }
Write-Output "Created $exe"

<#
.SYNOPSIS
    Environment setup for "Build Your First AI Agent" (Windows / PowerShell).

.DESCRIPTION
    Creates a local .venv, installs requirements, registers a Jupyter kernel,
    and copies .env.example to .env if you don't have one yet.

.EXAMPLE
    .\setup.ps1
    # then:
    .\.venv\Scripts\Activate.ps1
    jupyter lab

.NOTES
    If script execution is blocked, run PowerShell as:
        powershell -ExecutionPolicy Bypass -File .\setup.ps1
#>

$ErrorActionPreference = "Stop"

# Resolve repo root (directory of this script) so it works from anywhere.
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$VenvDir     = ".venv"
$KernelName  = "ai-agent"
$KernelLabel = "Python (Build Your First AI Agent)"

# Pick a Python interpreter.
$Py = $null
foreach ($cand in @("python", "py")) {
    if (Get-Command $cand -ErrorAction SilentlyContinue) { $Py = $cand; break }
}
if (-not $Py) {
    Write-Error "No 'python' or 'py' found on PATH. Install Python 3.8+ first."
}

Write-Host "==> Using $(& $Py --version)"

# 1. Create the virtual environment if it doesn't exist.
if (-not (Test-Path $VenvDir)) {
    Write-Host "==> Creating virtual environment in $VenvDir"
    & $Py -m venv $VenvDir
} else {
    Write-Host "==> Reusing existing virtual environment in $VenvDir"
}

# 2. Use the venv's Python directly (no need to activate for installs).
$VenvPy = Join-Path $VenvDir "Scripts\python.exe"

# 3. Install dependencies.
Write-Host "==> Upgrading pip and installing requirements"
& $VenvPy -m pip install --upgrade pip | Out-Null
& $VenvPy -m pip install -r requirements.txt

# 4. Register a Jupyter kernel that points at this venv.
Write-Host "==> Registering Jupyter kernel '$KernelName'"
& $VenvPy -m ipykernel install --user --name $KernelName --display-name $KernelLabel

# 5. Seed a .env from the template if the user doesn't have one.
if (-not (Test-Path ".env")) {
    Write-Host "==> No .env found - copying .env.example to .env (edit it with your provider + key)"
    Copy-Item ".env.example" ".env"
} else {
    Write-Host "==> .env already exists - leaving it untouched"
}

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Edit .env with your OPENAI_BASE_URL / OPENAI_API_KEY / MODEL."
Write-Host "  2. Activate the venv:   .\.venv\Scripts\Activate.ps1"
Write-Host "  3. Start Jupyter:       jupyter lab"
Write-Host "  4. In each notebook, pick the kernel: `"$KernelLabel`"."

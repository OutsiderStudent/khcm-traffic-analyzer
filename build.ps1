$ErrorActionPreference = "Stop"

if ($env:KHCM_PYTHON) {
    & $env:KHCM_PYTHON -m PyInstaller --noconfirm --clean "khcm_arterial_analyzer.spec"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python -m PyInstaller --noconfirm --clean "khcm_arterial_analyzer.spec"
} else {
    & py -3 -m PyInstaller --noconfirm --clean "khcm_arterial_analyzer.spec"
}

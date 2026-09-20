$ErrorActionPreference = "Stop"

if ($env:KHCM_PYTHON) {
    & $env:KHCM_PYTHON -m PyInstaller --noconfirm --clean "khcm_arterial_analyzer.spec"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 -m PyInstaller --noconfirm --clean "khcm_arterial_analyzer.spec"
} else {
    & python -m PyInstaller --noconfirm --clean "khcm_arterial_analyzer.spec"
}

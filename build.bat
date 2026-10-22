@echo off
REM WindowsHarness Build Script
REM Run this on Windows to create the standalone .exe

echo ==========================================
echo WindowsHarness - Build Script
echo ==========================================

REM Check Python version
python --version
if errorlevel 1 (
    echo ERROR: Python not found in PATH
    pause
    exit /b 1
)

echo.
echo Installing/updating dependencies...
pip install --upgrade pip
pip install -r requirements.txt
pip install PyQt6-WebEngine PyQt6-Qscintilla pyinstaller

echo.
echo Converting icon (requires ImageMagick or similar)...
REM If you have ImageMagick: magick assets/icon.svg assets/icon.ico
REM Otherwise, use online converter or create icon.ico manually
if not exist assets/icon.ico (
    echo WARNING: assets/icon.ico not found. Build will use default icon.
    echo You can convert assets/icon.svg to .ico using:
    echo   - ImageMagick: magick assets/icon.svg assets/icon.ico
    echo   - Online: https://convertio.co/svg-ico/
    echo.
)

echo.
echo Building with PyInstaller...
pyinstaller windows-harness.spec --clean

echo.
echo ==========================================
if exist dist\WindowsHarness.exe (
    echo SUCCESS! Executable created at:
    echo   dist\WindowsHarness.exe
    echo.
    echo File size:
    dir dist\WindowsHarness.exe
) else (
    echo BUILD FAILED - check output above for errors
)
echo ==========================================

echo.
echo To test the executable:
echo   dist\WindowsHarness.exe
echo.
pause

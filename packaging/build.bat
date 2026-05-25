@echo off
REM Build script for Windows
REM Generates dist\FlexionCalculator.exe (portable single executable)
REM Run from anywhere - it will cd into the project root.

setlocal

REM Cambia al directorio raíz del proyecto (un nivel arriba de packaging\)
cd /d "%~dp0\.."

echo ============================================
echo  Building Flexion Calculator for Windows
echo ============================================
echo  Project root: %CD%
echo.

REM 1. Verify Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    echo Download Python from https://www.python.org/downloads/
    exit /b 1
)

REM 2. Install/upgrade dependencies
echo [1/4] Installing dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

REM 3. Clean previous build
echo.
echo [2/4] Cleaning previous build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM 4. Build
echo.
echo [3/4] Building executable...
python -m PyInstaller packaging\flexion_calculator.spec --clean --noconfirm

REM 5. Verify result
echo.
echo [4/4] Verifying result...
if exist "dist\FlexionCalculator.exe" (
    echo.
    echo ============================================
    echo  BUILD SUCCESSFUL
    echo ============================================
    echo  Output: dist\FlexionCalculator.exe
    for %%A in ("dist\FlexionCalculator.exe") do echo  Size:   %%~zA bytes
    echo.
    echo You can now copy FlexionCalculator.exe anywhere
    echo and run it directly. No installation required.
    echo ============================================
) else (
    echo [ERROR] Build failed - exe not found
    exit /b 1
)

endlocal

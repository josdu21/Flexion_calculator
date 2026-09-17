@echo off
REM Build script for Windows (Nuitka)
REM Generates dist\BeamCalculator\BeamCalculator.exe (standalone folder)
REM Run from anywhere - it will cd into the project root.

setlocal enabledelayedexpansion

REM Cambia al directorio raiz del proyecto (un nivel arriba de packaging\)
cd /d "%~dp0\.."

echo ============================================
echo  Building Beam Calculator with Nuitka
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

REM 2. Read version
set VERSION=0.0.0
if exist "packaging\version.txt" (
    set /p VERSION=<packaging\version.txt
)
echo  Version: %VERSION%
echo.

REM 3. Install/upgrade dependencies
echo [1/5] Installing dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python -m nuitka --version

REM 4. Clean previous build
echo.
echo [2/5] Cleaning previous build...
if exist build_nuitka rmdir /s /q build_nuitka
if exist "distro\BeamCalculator" rmdir /s /q "distro\BeamCalculator"

REM 5. Detect optional icon
REM El .ico se incrusta en el exe y ademas se copia al lado, porque Qt lo lee
REM en runtime para el icono de la ventana y la barra de tareas.
set ICON_FLAG=
if exist "assets\icon.ico" (
    echo  Icon found: assets\icon.ico
    set ICON_FLAG=--windows-icon-from-ico=assets\icon.ico --include-data-files=assets\icon.ico=assets\icon.ico
) else (
    echo  No icon at assets\icon.ico - building without one.
)

REM 6. Build
echo.
echo [3/5] Building standalone executable...
python -m nuitka main.py ^
    --standalone ^
    --enable-plugin=pyqt6 ^
    --windows-console-mode=disable ^
    --output-dir=build_nuitka ^
    --output-filename=BeamCalculator.exe ^
    --company-name="Jose Manuel Duarte" ^
    --product-name="Beam Calculator" ^
    --file-version=%VERSION%.0 ^
    --product-version=%VERSION%.0 ^
    --file-description="Beam Calculator - Diseno de refuerzo ACI 318-19" ^
    --zig ^
    --assume-yes-for-downloads ^
    --remove-output ^
    %ICON_FLAG%

if errorlevel 1 (
    echo.
    echo [ERROR] Nuitka build failed
    exit /b 1
)

REM 7. Move standalone folder to a stable path
echo.
echo [4/5] Placing output...
if not exist distro mkdir distro
move /y "build_nuitka\main.dist" "distro\BeamCalculator" >nul
rmdir /s /q build_nuitka

REM 8. Verify result
echo.
echo [5/5] Verifying result...
if exist "distro\BeamCalculator\BeamCalculator.exe" (
    echo.
    echo ============================================
    echo  BUILD SUCCESSFUL
    echo ============================================
    echo  Output: distro\BeamCalculator\BeamCalculator.exe
    for %%A in ("distro\BeamCalculator\BeamCalculator.exe") do echo  Size:   %%~zA bytes
    echo.
    echo  Next step: compile the installer with
    echo    iscc packaging\installer.iss
    echo ============================================
) else (
    echo [ERROR] Build failed - exe not found
    exit /b 1
)

endlocal

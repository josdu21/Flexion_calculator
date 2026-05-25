# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Calculadora de Acero por Flexión.

Usage:
    pyinstaller flexion_calculator.spec

Output:
    Linux:   dist/FlexionCalculator           (single executable, ~70 MB)
    Windows: dist/FlexionCalculator.exe       (single executable, ~80 MB)
"""
import sys
import os
from pathlib import Path

block_cipher = None

# Raíz del proyecto (un nivel arriba de packaging/)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(SPEC), '..'))

# Detectar plataforma para nombrar el binario
IS_WINDOWS = sys.platform.startswith("win")
EXE_NAME = "FlexionCalculator"
_icon_path = os.path.join(PROJECT_ROOT, "assets", "icon.ico")
ICON_FILE = _icon_path if (IS_WINDOWS and os.path.exists(_icon_path)) else None

a = Analysis(
    [os.path.join(PROJECT_ROOT, 'main.py')],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[
        # No hay archivos de datos externos: el tema se lee en runtime
        # desde ~/.config/omarchy/ (Linux) y los stylesheets son strings.
    ],
    hiddenimports=[
        # PyQt6 submodules used by the app
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Reducir tamaño: módulos PyQt6 que no usamos
        'PyQt6.QtNetwork',
        'PyQt6.QtQml',
        'PyQt6.QtQuick',
        'PyQt6.QtWebEngineCore',
        'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtMultimedia',
        'PyQt6.QtSvg',
        'PyQt6.QtSql',
        'PyQt6.QtPrintSupport',
        'PyQt6.QtBluetooth',
        'PyQt6.QtPositioning',
        'PyQt6.QtSensors',
        'PyQt6.QtSerialPort',
        'PyQt6.QtTest',
        # Otros pesos comunes
        'tkinter',
        'unittest',
        'pydoc',
        'doctest',
        'difflib',
        'distutils',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=EXE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                 # comprime con UPX si está disponible (opcional)
    upx_exclude=[
        # Qt DLLs pueden romperse con UPX
        'Qt6Core*',
        'Qt6Gui*',
        'Qt6Widgets*',
    ],
    runtime_tmpdir=None,
    console=False,            # GUI app: sin ventana de consola
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_FILE,
)

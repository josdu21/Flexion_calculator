#!/usr/bin/env python3
"""
Calculadora de Acero por Flexión - Interfaz GUI (PyQt6)
Uso: python main.py
"""

import sys
import os

# Verificar que PyQt6 esté disponible
try:
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from PyQt6.QtCore import Qt
except ImportError:
    print("Error: PyQt6 no está instalado")
    print()
    print("Opciones:")
    print("1. Instalar PyQt6:")
    print("   - Arch/CachyOS: sudo pacman -S python-pyqt6")
    print("   - Debian/Ubuntu: sudo apt install python3-pyqt6")
    print("   - Otros: pip install PyQt6")
    print()
    print("2. Usar la versión CLI (sin dependencias):")
    print("   python main_cli.py")
    print()
    sys.exit(1)

# Importar el módulo de la interfaz
try:
    from ui.main_window import MainWindow
except ImportError as e:
    print(f"Error al importar módulos: {e}")
    sys.exit(1)

def main():
    """Función principal"""
    app = QApplication(sys.argv)

    # Configurar el estilo de la aplicación
    app.setStyle('Fusion')

    # Crear y mostrar la ventana principal
    window = MainWindow()
    window.show()

    # Iniciar el event loop
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

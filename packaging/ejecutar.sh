#!/bin/bash
# Calculadora de Acero por Flexión - Script de ejecución robusto

# Obtener el directorio del script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# Detectar si se ejecuta desde GUI o terminal
if [ -z "$TERM" ] || [ "$TERM" = "dumb" ]; then
    IS_GUI_LAUNCH=true
else
    IS_GUI_LAUNCH=false
fi

# Función para ejecutar con manejo de errores
run_with_check() {
    # Intentar cargar PyQt6
    python3 -c "import PyQt6" 2>/dev/null
    if [ $? -eq 0 ]; then
        # PyQt6 está disponible, ejecutar GUI
        exec python3 main.py
    else
        # PyQt6 no disponible
        if [ "$IS_GUI_LAUNCH" = true ]; then
            # Desde GUI: intentar instalar y luego ejecutar
            if command -v pacman &> /dev/null; then
                pkexec pacman -S --noconfirm python-pyqt6 2>/dev/null
            elif command -v sudo &> /dev/null; then
                sudo pacman -S --noconfirm python-pyqt6 2>/dev/null || \
                sudo apt install -y python3-pyqt6 2>/dev/null || \
                sudo yum install -y python3-pyqt6 2>/dev/null
            fi
            # Intentar nuevamente
            python3 -c "import PyQt6" 2>/dev/null && exec python3 main.py
            # Si aún falla, ejecutar CLI
            exec python3 main_cli.py
        else
            # Desde terminal: mostrar opciones
            echo "=================================================="
            echo "Calculadora de Acero por Flexión"
            echo "=================================================="
            echo ""
            echo "PyQt6 no está instalado."
            echo ""
            echo "Opciones:"
            echo "1. Instalar PyQt6:"
            if command -v pacman &> /dev/null; then
                echo "   sudo pacman -S python-pyqt6"
            elif command -v apt &> /dev/null; then
                echo "   sudo apt install python3-pyqt6"
            else
                echo "   pip install PyQt6"
            fi
            echo ""
            echo "2. Ejecutar CLI (sin dependencias):"
            echo "   python3 main_cli.py"
            echo ""
            read -p "¿Ejecutar CLI ahora? (s/n) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Ss]$ ]]; then
                exec python3 main_cli.py
            fi
        fi
    fi
}

# Ejecutar
run_with_check

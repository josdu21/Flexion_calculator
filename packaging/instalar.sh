#!/bin/bash
# Script de instalación de la Calculadora de Acero por Flexión

echo "=========================================="
echo "Calculadora de Acero por Flexión"
echo "Instalador"
echo "=========================================="
echo ""

# Detectar el sistema operativo
if command -v pacman &> /dev/null; then
    echo "Sistema detectado: Arch/CachyOS"
    echo "Instalando PyQt6..."
    sudo pacman -S --noconfirm python-pyqt6
elif command -v apt &> /dev/null; then
    echo "Sistema detectado: Debian/Ubuntu"
    echo "Instalando PyQt6..."
    sudo apt install -y python3-pyqt6
elif command -v yum &> /dev/null; then
    echo "Sistema detectado: RedHat/CentOS"
    echo "Instalando PyQt6..."
    sudo yum install -y python3-pyqt6
else
    echo "Sistema de paquetes no identificado"
    echo "Instala PyQt6 manualmente: pip install PyQt6"
    exit 1
fi

echo ""
echo "✓ Instalación completada"
echo ""
echo "Para ejecutar la aplicación:"
echo "  ./ejecutar.sh          (desde el directorio)"
echo "  python main_cli.py     (versión CLI sin dependencias)"
echo ""
echo "O busca 'Calculadora de Acero' en tu menú de aplicaciones"
echo ""

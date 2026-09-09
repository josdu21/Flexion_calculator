# 🏗️ Calculadora de Acero (ACI 318-19)

Aplicación de escritorio para diseñar acero de refuerzo por **flexión, cortante y torsión** según ACI 318-19. Compatible con Windows y Linux.

## ✨ Características

- ✅ Diseño de vigas y losas por flexión
- ✅ Diseño por cortante: estribos en viga y revisión de losa (ACI §22.5)
- ✅ Diseño por torsión combinado con cortante en viga (ACI §22.7)
- ✅ 3 sistemas de unidades: MKS (tonf, m), SI (kN, m), Inglés (kip, ft)
- ✅ Cálculo de As requerido, As_min, As_max
- ✅ Sugerencias automáticas de varillas ASTM
- ✅ Memoria de cálculo HTML imprimible con fórmulas y referencias al ACI
- ✅ Interfaz CLI (sin dependencias)
- ✅ Interfaz GUI con PyQt6 (opcional)
- ✅ Compatible con Linux y Windows

## 🚀 Uso rápido

### Desde el escritorio (Recomendado)
- Busca **"Calculadora de Acero"** en tu menú de aplicaciones
- Haz clic para ejecutar

### Desde terminal (CLI - Sin instalar nada)
```bash
cd ~/Projects/Flexion_calculator
python main_cli.py
```

### Desde terminal (GUI con PyQt6)
```bash
cd ~/Projects/Flexion_calculator
chmod +x ejecutar.sh
./ejecutar.sh
```

## 📥 Instalación

### Linux (Arch/CachyOS)
```bash
sudo pacman -S python-pyqt6
cd ~/Projects/Flexion_calculator
python main.py
```

### Linux (Debian/Ubuntu)
```bash
sudo apt install python3-pyqt6
python3 ~/Projects/Flexion_calculator/main.py
```

### Windows
```bash
pip install PyQt6
python main.py
```

## 📊 Ejemplo de cálculo

**Entrada (Sistema SI):**
- Viga: Mu = 150 kN·m
- Dimensiones: b = 300 mm, h = 500 mm, cover = 40 mm
- Resistencias: f'c = 28 MPa, fy = 420 MPa

**Salida:**
```
d efectivo:        452.00 mm
As requerido:      9.35 cm²
As mínimo:         4.52 cm²
As máximo:         27.99 cm²
Estado:            ✓ OK
Sugerencias:       5 × #5 (9.90 cm²)
```

## 📂 Estructura

```
flexion_calculator/
├── main.py               # GUI PyQt6
├── main_cli.py           # CLI (sin dependencias)
├── ejecutar.sh           # Script de ejecución
│
├── core/
│   ├── flexion.py       # Motor de flexión ACI 318-19
│   ├── shear.py         # Motor de cortante (viga y losa)
│   ├── torsion.py       # Motor de torsión + combinación V/T
│   ├── report.py        # Memoria de cálculo HTML
│   ├── units.py         # Conversión de unidades
│   └── bar_tables.py    # Varillas ASTM
│
├── ui/
│   ├── main_window.py         # Ventana principal
│   ├── input_panel.py         # Entradas de flexión
│   ├── results_panel.py       # Resultados de flexión
│   ├── shear_input_panel.py   # Entradas de cortante y torsión
│   └── shear_results_panel.py # Resultados de cortante y torsión
│
├── requirements.txt     # Dependencias
└── README.md           # Este archivo
```

## 🧮 Fórmulas ACI 318-19

1. **d efectivo:** d = h - cover - db/2
2. **β₁:** 0.85 si f'c ≤ 28 MPa; decrece 0.05 por cada 7 MPa
3. **Rn:** Mu / (φ·b·d²), donde φ = 0.9
4. **ρ requerida:** (1/m)·[1 - √(1 - 2m·Rn/fy)], m = fy/(0.85·f'c)
5. **As requerido:** ρ·b·d
6. **As mínimo:** max(0.25√f'c/fy, 1.4/fy)·b·d
7. **As máximo:** (0.85·β₁·f'c/fy)·(0.003/(0.003+0.004))·b·d

### Cortante (§22.5, §9.6.3, §9.7.6.2)

8. **Vc:** 0.17·λ·√f'c·bw·d — con φ = 0.75
9. **Vs requerido:** (Vu − φVc)/φ ≤ 0.66·√f'c·bw·d
10. **s por resistencia:** Av·fyt·d / Vs
11. **(Av/s)min:** max(0.062√f'c/fyt, 0.35/fyt)·bw
12. **s máx:** min(d/2, 600 mm) o min(d/4, 300 mm) si Vs > 0.33√f'c·bw·d

### Torsión (§22.7, §9.6.4, §9.7.5, §9.7.6.3)

13. **Torsión umbral:** Tth = 0.083·λ·√f'c·(Acp²/pcp) — si Tu ≤ φTth se desprecia
14. **Torsión de agrietamiento:** Tcr = 0.33·λ·√f'c·(Acp²/pcp) — en torsión por
    compatibilidad, Tu puede reducirse a φTcr
15. **Límite de la sección:** √[(Vu/bw·d)² + (Tu·ph/1.7Aoh²)²] ≤ φ(Vc/bw·d + 0.66√f'c)
16. **At/s:** (Tu/φ) / (2·Ao·fyt·cotθ), con Ao = 0.85·Aoh y θ = 45°
17. **Combinado:** (Av + 2At)/s ≥ max(0.062√f'c/fyt, 0.35/fyt)·bw
18. **Al:** (At/s)·ph·(fyt/fy)·cot²θ, no menor que Al,min de §9.6.4.3
19. **s máx torsión:** min(ph/8, 300 mm)

## 🔧 Solución de problemas

**"ModuleNotFoundError: PyQt6"**
- Instala: `pip install PyQt6` o `sudo pacman -S python-pyqt6`

**La GUI no abre**
- Usa CLI: `python main_cli.py`
- O instala PyQt6 manualmente

**Permisos denegados (Linux)**
- Ejecuta: `chmod +x ejecutar.sh`

## 📋 Varillas ASTM soportadas

#2, #3, #4, #5, #6, #8, #10, #12

## 🎯 Próximos pasos (opcional)

1. **Crear ejecutable Windows:**
   ```bash
   pip install pyinstaller
   pyinstaller --onefile --windowed main.py
   ```

2. **Mejoras futuras:**
   - Diseño a compresión
   - Torsión en secciones T y L (alas efectivas)
   - Exportar a PDF
   - Gráficos de momento

## 📝 Requisitos del sistema

- Python 3.7+
- PyQt6 6.4.0+ (solo para GUI)
- 50 MB de espacio en disco

## 📄 Licencia

Proyecto educativo. Libre para usar y modificar.

## 📧 Contacto

josdu2121@gmail.com

---

**¡Listo para usar! Ejecuta `./ejecutar.sh` desde el directorio del proyecto o busca la aplicación en tu menú.**

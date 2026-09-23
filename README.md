# 🏗️ Beam Calculator

Aplicación de escritorio para diseñar acero de refuerzo por **flexión, cortante y torsión**, con **dos normativas seleccionables**: **ACI 318-19** y **AASHTO LRFD Bridge Design Specifications 2020**. Compatible con Windows y Linux.

## ✨ Características

- ✅ **Dos normativas** en la misma sección: se eligen desde la cabecera y la memoria registra con cuál se calculó
- ✅ Diseño de vigas y losas por flexión
- ✅ **Secciones rectangulares, T y L** en viga, con el ala comprimida
- ✅ Diseño por cortante: estribos en viga y revisión de losa
- ✅ Diseño por torsión combinado con cortante en viga
- ✅ 3 sistemas de unidades: MKS (tonf, m), SI (kN, m), Inglés (kip, ft)
- ✅ Cálculo de As requerido, As_min y límites de armado
- ✅ Sugerencias automáticas de varillas ASTM
- ✅ Memoria de cálculo HTML imprimible, una por elemento, con las fórmulas y referencias de la norma usada
- ✅ Guardar y reabrir el estudio completo en un archivo `.json`
- ✅ Interfaz CLI (sin dependencias)
- ✅ Interfaz GUI con PyQt6 (opcional)
- ✅ Compatible con Linux y Windows

> La interfaz CLI (`main_cli.py`) calcula sólo flexión según ACI 318-19. Para
> AASHTO y para cortante y torsión, usar la GUI.

## 📐 Normativas

| | ACI 318-19 | AASHTO LRFD 2020 |
|---|---|---|
| φ flexión | 0.90 fijo | **Variable con ε_t** (§5.5.4.2): 0.75 → 0.90 |
| φ cortante / torsión | 0.75 | **0.90** |
| Refuerzo mínimo a flexión | Área (§9.6.1.2) | **Momento**: `M_r ≥ min(1.33·M_u, M_cr)` (§5.6.3.3) |
| Peralte para cortante | `d` | **`d_v`** = max(d_e − ȳ, 0.9·d_e, 0.72·h) (§5.7.2.8) |
| Ancho efectivo del ala | Tabla 6.3.2.1: voladizo ≤ min(8h_f, s_w/2, l_n/8) | §4.6.2.6.1: **ancho tributario** |
| V_c | Tabla 22.5.5.1 | `0.083·β·λ·√f'c·b_v·d_v`, β = 2.0 (§5.7.3.4.1) |
| Umbral de torsión | `T_u > φ·T_th` | `T_u > 0.25·φ·T_cr` (§5.7.2.1) |
| Revisiones extra | — | Refuerzo longitudinal (§5.7.3.5) y control de fisuración (§5.6.7) |

**Alcance de AASHTO:** concreto reforzado, con el
**procedimiento simplificado de cortante** (§5.7.3.4.1). No están implementados
el procedimiento general de §5.7.3.4.2 (MCFT), el preesfuerzo, ni los métodos
específicos de tablero (§4.6.2.1, §9.7.2). El procedimiento simplificado sólo
cubre elementos sin estribos si `h < 400 mm`; por encima, la aplicación avisa
que el resultado no sirve como verificación normativa.

## 🧱 Formas de sección

La viga se calcula como **rectangular**, **T** (ala a ambos lados) o **L** (ala
a un lado, viga de borde). El tipo se elige en la geometría de la pestaña
«Viga · Flexión» y de ahí lo toman el cortante y la torsión.

- Se modela el **ala comprimida**, es decir momento positivo. En una zona de
  momento negativo el ala queda traccionada y la sección responde como
  rectangular de ancho `b_w`: para eso se elige esa forma.
- `b_w` es el ancho del alma y es el que rige el cortante (`b_v`), la torsión y
  el `A_s,mín` de §9.6.1.2. El ala entra por el bloque de compresión, por el
  módulo de sección del `M_cr` de AASHTO y por el `A_cp` de torsión.
- El **ancho efectivo del ala `b_f` se ingresa**. La aplicación verifica el
  único límite que puede verificar sin más datos —el voladizo en múltiplos de
  `h_f`, ACI 318-19 Tabla 6.3.2.1— y avisa si se excede. Los otros dos límites
  de esa tabla (`s_w/2` y `l_n/8`, o `l_n/12` en la L) dependen de la luz y de
  la separación entre almas, que la aplicación no pide.
- La losa es siempre una franja rectangular de 1 m: no tiene selector de forma.

## 🚀 Uso rápido

### Windows (Recomendado)
Instala con `BeamCalculator-Setup-<version>.exe` (ver [Releases](https://github.com/josdu21/Flexion_calculator/releases))
y busca **"Beam Calculator"** en el menú Inicio.

### Desde terminal (CLI - Sin instalar nada)
```bash
python main_cli.py
```

### Desde terminal (GUI con PyQt6)
```bash
python main.py
```

En Linux, `packaging/ejecutar.sh` instala PyQt6 si falta y luego abre la GUI:
```bash
chmod +x packaging/ejecutar.sh
./packaging/ejecutar.sh
```

## Interfaz de diseño

- Una fila de navegación: flexión y cortante/torsión de viga; flexión y cortante de losa.
- Formularios continuos con desplazamiento. Los resultados se actualizan al confirmar
  una entrada (Enter o salir del campo), sin botón de recálculo.
- Ancho, altura, recubrimiento y f'c se sincronizan entre los dos análisis del mismo
  elemento. Las cargas y las hipótesis de refuerzo de cada análisis son independientes.
  La losa comienza con una franja de 1 m, espesor de 15 cm y recubrimiento de 2 cm.
- Estado, advertencias y refuerzo de diseño aparecen primero. Las comprobaciones
  intermedias se despliegan bajo demanda; la casilla **Incluir torsión · Tu** está
  debajo de Vu en **Viga · Cortante / torsión**, visible sin desplazarse.
- **Datos del proyecto** (`Ctrl+I`) define lo que va en el cajetín de la memoria:
  proyecto, diseñador, revisor, revisión, notas y el nombre de cada elemento.
  La fecha, el tipo de elemento y la norma se generan solos.
- **Guardar** (`Ctrl+S`) y **Abrir** (`Ctrl+O`) trabajan sobre un `.json` que
  contiene el estudio completo: los cuatro análisis, los datos del cajetín y el
  sistema de unidades. Las magnitudes se guardan en SI, así que un estudio
  hecho en unidades inglesas se abre sin problema en MKS o SI.
- **Exportar memoria** (`Ctrl+E`) guarda una sola memoria por elemento: la de viga
  cubre flexión, cortante y torsión; la de losa, flexión y cortante. Da igual
  desde qué pestaña del elemento se exporte. Cancelar cierra el diálogo.
- El resumen se apila automáticamente al reducir la ventana (mínimo 960 × 640).

Pruebas de los flujos de interfaz (requieren PyQt6):

```bash
python -m unittest discover -s tests -v
```

## 📥 Instalación

### Linux (Arch/CachyOS)
```bash
sudo pacman -S python-pyqt6
python main.py
```

### Linux (Debian/Ubuntu)
```bash
sudo apt install python3-pyqt6
python3 main.py
```

### Windows
Con el instalador (no requiere Python):
descarga `BeamCalculator-Setup-<version>.exe` desde Releases y ejecútalo.

Desde el código fuente:
```cmd
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
Beam_calculator/
├── main.py               # GUI PyQt6
├── main_cli.py           # CLI (sin dependencias)
│
├── core/
│   ├── design_code.py   # Registro de normas y despacho al motor que toca
│   ├── section_geometry.py  # Forma de la sección y armado (común)
│   ├── flexion.py       # Motor de flexión ACI 318-19
│   ├── shear.py         # Motor de cortante ACI (viga y losa)
│   ├── torsion.py       # Motor de torsión ACI + combinación V/T
│   ├── aashto/
│   │   ├── flexion.py   # Motor de flexión AASHTO LRFD
│   │   ├── shear.py     # Motor de cortante AASHTO (simplificado)
│   │   └── torsion.py   # Motor de torsión AASHTO + combinación V/T
│   ├── report.py        # Memoria de cálculo HTML (ambas normas)
│   ├── project.py       # Estudio guardable (.json) y datos del cajetín
│   ├── units.py         # Conversión de unidades
│   ├── bar_tables.py    # Varillas ASTM
│
├── ui/
│   ├── main_window.py         # Ventana principal
│   ├── input_panel.py         # Entradas de flexión
│   ├── results_panel.py       # Resultados de flexión
│   ├── shear_input_panel.py   # Entradas de cortante y torsión
│   ├── shear_results_panel.py # Resultados de cortante y torsión
│   ├── stress_diagram.py      # Diagrama de esfuerzos
│   ├── project_dialog.py      # Datos del cajetín
│   ├── form_helpers.py        # Widgets compartidos de formulario
│   └── theme.py               # Paleta y estilos
│
│   └── version.py       # Nombre y versión de la app
│
├── assets/icon.ico       # Ícono (regenerable con packaging/make_icon.py)
├── tests/                # Pruebas de los flujos de interfaz
├── packaging/            # Build, instalador y lanzadores Linux
│
├── requirements.txt      # Dependencias de la app
├── requirements-dev.txt  # Dependencias de build (Nuitka, Pillow)
├── CHANGELOG.md          # Registro de cambios por versión
└── README.md             # Este archivo
```

El build genera `distro/`: la carpeta `BeamCalculator/` con la app y el
instalador `BeamCalculator-Setup-<version>.exe`.

## 🧮 Fórmulas ACI 318-19

1. **d efectivo:** d = h - cover - db/2
2. **β₁:** 0.85 si f'c ≤ 28 MPa; decrece 0.05 por cada 7 MPa
3. **Rn:** Mu / (φ·b·d²), donde φ = 0.9
4. **ρ requerida:** (1/m)·[1 - √(1 - 2m·Rn/fy)], m = fy/(0.85·f'c)
5. **As requerido:** ρ·b·d
6. **As mínimo:** max(0.25√f'c/fy, 1.4/fy)·b·d
7. **As máximo:** (0.85·β₁·f'c/fy)·(0.003/(0.003+0.004))·b·d

### Secciones con ala (T y L, §6.3.2.1, §22.2)

Con el ala comprimida, `b` deja de ser constante en la altura del bloque, así
que la cuantía cerrada de arriba no aplica:

8. **Área comprimida en equilibrio:** A_c = A_s·f_y / (0.85·f'c)
9. **Profundidad del bloque:** a = A_c/b_f si A_c ≤ b_f·h_f;
   si no, a = h_f + (A_c − b_f·h_f)/b_w
10. **Brazo de palanca:** jd = d − ȳ, con ȳ el centroide del área comprimida
    (en sección rectangular, ȳ = a/2)
11. **As requerido, si el bloque no cabe en el ala:**
    A_sf = 0.85·f'c·(b_f − b_w)·h_f/f_y, con M_nf = A_sf·f_y·(d − h_f/2);
    el alma toma M_n − M_nf y A_s = A_sf + A_sw
12. **As máximo:** 0.85·f'c·A_c(a_max)/f_y, con a_max = β₁·d·(0.003/0.007)
13. **A_cp y p_cp de torsión (§22.7.4.1):** suman el voladizo del ala,
    limitado al menor entre el voladizo real, la proyección del alma bajo el
    ala y 4·h_f

### Cortante (§22.5, §9.6.3, §9.7.6.2)

14. **Vc:** 0.17·λ·√f'c·bw·d — con φ = 0.75
15. **Vs requerido:** (Vu − φVc)/φ ≤ 0.66·√f'c·bw·d
16. **s por resistencia:** Av·fyt·d / Vs
17. **(Av/s)min:** max(0.062√f'c/fyt, 0.35/fyt)·bw
18. **s máx:** min(d/2, 600 mm) o min(d/4, 300 mm) si Vs > 0.33√f'c·bw·d

### Torsión (§22.7, §9.6.4, §9.7.5, §9.7.6.3)

19. **Torsión umbral:** Tth = 0.083·λ·√f'c·(Acp²/pcp) — si Tu ≤ φTth se desprecia
20. **Torsión de agrietamiento:** Tcr = 0.33·λ·√f'c·(Acp²/pcp) — en torsión por
    compatibilidad, Tu puede reducirse a φTcr
21. **Límite de la sección:** √[(Vu/bw·d)² + (Tu·ph/1.7Aoh²)²] ≤ φ(Vc/bw·d + 0.66√f'c)
22. **At/s:** (Tu/φ) / (2·Ao·fyt·cotθ), con Ao = 0.85·Aoh y θ = 45°
23. **Combinado:** (Av + 2At)/s ≥ max(0.062√f'c/fyt, 0.35/fyt)·bw
24. **Al:** (At/s)·ph·(fyt/fy)·cot²θ, no menor que Al,min de §9.6.4.3
25. **s máx torsión:** min(ph/8, 300 mm)

## 🧮 Fórmulas AASHTO LRFD 2020

### Flexión (§5.5.4.2, §5.6.2, §5.6.3, §5.6.7)

1. **α₁, β₁:** β₁ igual que ACI; α₁ = 0.85 hasta 70 MPa, luego −0.02 por cada 7 MPa (piso 0.75)
2. **ε_t:** ε_cu·(d_t − c)/c, con ε_cu = 0.003
3. **φ:** 0.75 si ε_t ≤ ε_cl; 0.90 si ε_t ≥ ε_tl; interpolado en medio
4. **f_r:** 0.62·λ·√f'c  ·  **M_cr:** γ₃·γ₁·f_r·S_c, con γ₁ = 1.6 y γ₃ = 0.67 (A615) o 0.75 (A706)
5. **Refuerzo mínimo:** M_r ≥ min(1.33·M_u, M_cr) — criterio de momento, no de área
6. **Control de fisuración:** s ≤ 123000·γ_e/(β_s·f_ss) − 2·d_c, con β_s = 1 + d_c/(0.7(h−d_c))

### Cortante (§5.7.2, §5.7.3 — procedimiento simplificado de §5.7.3.4.1)

7. **d_v:** max(d_e − ȳ, 0.9·d_e, 0.72·h), con ȳ el centroide del bloque
   comprimido (a/2 en sección rectangular)
8. **V_c:** 0.083·β·λ·√f'c·b_v·d_v, con β = 2.0 y φ = 0.90
9. **V_s requerido:** V_u/φ − V_c  ·  **s:** A_v·f_y·d_v·cotθ / V_s, con θ = 45°
10. **Tope de la sección:** V_n ≤ 0.25·f'c·b_v·d_v
11. **(A_v/s)min:** 0.083·√f'c·b_v/f_y
12. **s máx:** min(0.8·d_v, 600 mm) si v_u < 0.125·f'c; si no, min(0.4·d_v, 300 mm)
13. **Refuerzo longitudinal:** A_s·f_y ≥ |M_u|/(φ_f·d_v) + (V_u/φ_v − 0.5·V_s)·cotθ

### Torsión (§5.7.2.1, §5.7.3.6)

14. **T_cr:** 0.125·λ·√f'c·(A_cp²/p_c) — se desprecia la torsión si T_u ≤ 0.25·φ·T_cr
15. **Cortante equivalente:** V_u,eq = √[V_u² + (0.9·p_h·T_u/(2·A_o))²]
16. **A_t/s:** (T_u/φ) / (2·A_o·f_y·cotθ), con A_o = 0.85·A_oh
17. **Longitudinal combinado:** A_s·f_y ≥ |M_u|/(φ_f·d_v) + cotθ·√[(V_u/φ_v − 0.5·V_s)² + (0.45·p_h·T_u/(2·A_o·φ))²]

## 🔧 Solución de problemas

**"ModuleNotFoundError: PyQt6"**
- Instala: `pip install PyQt6` o `sudo pacman -S python-pyqt6`

**La GUI no abre**
- Usa CLI: `python main_cli.py`
- O instala PyQt6 manualmente

**Permisos denegados (Linux)**
- Ejecuta: `chmod +x packaging/ejecutar.sh`

## 📋 Varillas ASTM soportadas

#2, #3, #4, #5, #6, #8, #10, #12

## 🎯 Próximos pasos (opcional)

1. **Crear instalador Windows:**
   ```cmd
   packaging\build_nuitka.bat
   iscc packaging\installer.iss
   ```
   Ver `packaging/README.md` para más detalle (requiere Inno Setup instalado aparte).

2. **Mejoras futuras:**
   - Diseño a compresión
   - Torsión en secciones T y L (alas efectivas)
   - Exportar a PDF
   - Gráficos de momento

## 📝 Requisitos del sistema

- Python 3.7+ (no hace falta si usas el instalador de Windows)
- PyQt6 6.4.0+ (solo para GUI)
- ~75 MB de espacio en disco

## 📄 Licencia

MIT — ver [LICENSE](LICENSE).

## 📧 Contacto

josdu2121@gmail.com

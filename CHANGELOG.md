# Registro de cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)
y [versionado semántico](https://semver.org/lang/es/).

Para publicar una versión: `python packaging/bump_version.py <x.y.z>`, completar
la entrada de abajo, commitear y etiquetar con `git tag v<x.y.z>`.

## [2.0.0]

### ⚠ Cambios que afectan resultados

- **Vc de losa según ACI 318-19.** Antes se usaba `0.17·λ·√f'c·b·d`, que la
  norma sólo permite en elementos con `Av ≥ Av,min`. Como la losa no lleva
  estribos, ahora se aplica la Tabla 22.5.5.1 para elementos sin refuerzo
  transversal: `0.66·λs·λ·(ρw)^⅓·√f'c·b·d`, con el factor de tamaño `λs`
  (§22.5.5.1.3). El Vc resultante baja entre 1.5 y 1.8 veces, así que **losas
  que antes daban OK pueden fallar ahora**. Re-revisar lo calculado con 1.0.0.
- **Peralte efectivo unificado en viga.** Cortante y torsión usan el `d` real de
  los lechos definidos en flexión, en vez de estimarlo con un diámetro asumido
  fijo de 19.05 mm. Cambia levemente Vc, Vs y la separación de estribos.
- **`(Av + 2At)/s` provisto.** Se contabilizaba sólo `n·Ab/s`, ignorando el
  término `2At`; el valor reportado era la mitad del real.

### Agregado

- Memoria de cálculo **única por elemento**: la de viga cubre flexión, cortante
  y torsión; la de losa, flexión y cortante. Antes había una memoria por
  análisis.
- **Datos del proyecto** (`Ctrl+I`): proyecto, diseñador, revisor, revisión,
  notas y nombre de cada elemento, que alimentan el cajetín de la memoria.
- **Guardar** (`Ctrl+S`) y **Abrir** (`Ctrl+O`) el estudio completo en un
  `.json`: los cuatro análisis, el cajetín y el sistema de unidades. Las
  magnitudes se guardan en SI, así que el archivo es independiente de las
  unidades en que se creó.
- Ícono de la aplicación.
- La versión se muestra en la interfaz y queda registrada al pie de cada
  memoria exportada.

### Cambiado

- La aplicación pasa a llamarse **Beam Calculator** (antes «Calculadora de
  Acero»). El ejecutable es `BeamCalculator.exe` y el instalador
  `BeamCalculator-Setup-<versión>.exe`.
- El empaquetado usa **Nuitka** en vez de PyInstaller, y el instalador se arma
  con **Inno Setup**. El instalador ahora actualiza en sitio una instalación
  previa y avisa si se intenta instalar sobre una versión más nueva.
- Los ratios sin solicitación (`Vu = 0`) se muestran como `∞` en vez de `0.00`,
  que se leía como falla total.

### Corregido

- `ZeroDivisionError` al calcular con `b = 0`, `f'c = 0` o `fy = 0`.
- `packaging/ejecutar.sh` (Linux) buscaba `main.py` dentro de `packaging/`, así
  que no arrancaba desde que el script se movió a esa carpeta.
- Un booleano de Python (`True`) se filtraba al HTML de la memoria en la
  verificación de equilibrio; ahora es una etiqueta CUMPLE / NO CUMPLE.

## [1.0.0]

- Diseño por flexión, cortante y torsión según ACI 318-19.
- Tres sistemas de unidades (MKS, SI, Inglés).
- Interfaz PyQt6 y memoria de cálculo HTML por análisis.

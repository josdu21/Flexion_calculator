# Registro de cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)
y [versionado semántico](https://semver.org/lang/es/).

Para publicar una versión: `python packaging/bump_version.py <x.y.z>`, completar
la entrada de abajo, commitear y etiquetar con `git tag v<x.y.z>`.

## [2.1.0]

### Agregado

- **Segunda normativa: AASHTO LRFD Bridge Design Specifications 2020.** Un
  selector en la cabecera elige la norma y recalcula los cuatro análisis con
  ella. **Los resultados de ACI 318-19 no cambian**: cada norma tiene su propio
  motor y la memoria deja registrado con cuál se calculó.
  - Flexión (§5.6): bloque rectangular con α₁ y β₁ de §5.6.2.2, **φ variable con
    ε_t** (§5.5.4.2, entre 0.75 y 0.90), refuerzo mínimo como criterio de
    momento `M_r ≥ min(1.33·M_u, M_cr)` (§5.6.3.3) y control de fisuración
    (§5.6.7).
  - Cortante (§5.7.3): **procedimiento simplificado de §5.7.3.4.1** (β = 2.0,
    θ = 45°, φ = 0.90), evaluado sobre el peralte efectivo de cortante `d_v`
    (§5.7.2.8), con el tope `V_n ≤ 0.25·f'c·b_v·d_v` y la revisión del refuerzo
    longitudinal de §5.7.3.5.
  - Torsión (§5.7.3.6): umbral `T_u > 0.25·φ·T_cr`, cortante equivalente
    `V_u,eq` para el tope de la sección, y refuerzo longitudinal combinado
    M + V + T de §5.7.3.6.3.
  - Alcance: concreto reforzado, secciones rectangulares. **No** se implementan
    el procedimiento general de §5.7.3.4.2 (MCFT), el preesfuerzo ni los métodos
    específicos de tablero (§4.6.2.1, §9.7.2).
- Bajo AASHTO se piden tres datos nuevos, sólo visibles con esa norma: tipo de
  barra (γ₃), clase de exposición (γ_e) y **momento de servicio M_s**, opcional;
  en cero, el control de fisuración se omite y la memoria lo dice.
- El cortante AASHTO toma de la pestaña de flexión el bloque de compresión (para
  `d_v`) y el M_u con el acero longitudinal (para §5.7.3.5), así que esas
  revisiones no piden ningún dato extra.

### Cambiado

- El archivo del estudio pasa a **v2** y guarda la norma. Los `.json` de la
  2.0.0 se abren igual y se interpretan como ACI 318-19.
- En la memoria, las referencias a artículos de ACI quedaron uniformes
  («ACI 318-19 §9.6.3.4» en vez de «ACI 9.6.3.4», que aparecía en tres lugares),
  y el pie ahora cita el nombre completo de la norma.
- La geometría del armado (lechos, centroide, separaciones) se extrajo a
  `core/section_geometry.py` para compartirla entre ambas normas. No cambia
  ningún resultado; está verificado contra la versión anterior.
- El diagrama de esfuerzos ya no rotula «ACI 318» ni «0.85·f'c» fijos: muestra
  la norma activa y el α₁ que corresponde.

### Corregido

- Bajo AASHTO, un refuerzo longitudinal insuficiente (§5.7.3.5 o §5.7.3.6.3)
  ahora marca el estado como «armado insuficiente» en vez de dejarlo en «diseño
  correcto» con la falla sólo en las advertencias.

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

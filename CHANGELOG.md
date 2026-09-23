# Registro de cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)
y [versionado semántico](https://semver.org/lang/es/).

Para publicar una versión: `python packaging/bump_version.py <x.y.z>`, completar
la entrada de abajo, commitear y etiquetar con `git tag v<x.y.z>`.

## [2.3.0]

### Agregado

- **Momento negativo en viga.** Un selector «Signo» en Solicitación elige
  entre momento positivo (acero inferior) y negativo (acero superior). En
  negativo el armado definido pasa a la cara superior y la compresión queda
  abajo, en el alma. `M_u` se sigue ingresando como magnitud.
  - En sección T o L el ala queda traccionada: la flexión se calcula como una
    rectangular de ancho `b_w` y la geometría real se conserva para el dibujo
    y la torsión.
  - ACI 318-19 §9.6.1.2: una casilla «Elemento isostático (voladizo)», visible
    sólo con ala traccionada, hace que `A_s,mín` use el menor entre `b_f` y
    `2·b_w`.
  - AASHTO: el `M_cr` de §5.6.3.3 usa el módulo de sección de la fibra
    superior (`I_g/y_sup`), y el `d_v` se mide con `a/2`.
  - El diagrama dibuja las barras arriba y el bloque comprimido abajo; la
    memoria rotula `M_u⁻` y recuerda la distribución del acero en el ala que
    pide §24.3.4, que no se verifica.
- Los resultados con momento positivo no cambian (verificado contra la 2.2.0).
- La losa sigue calculándose sólo en momento positivo.

### Cambiado

- **Nueva pantalla de inicio** (diseño 1c de `UI_Design/`). A la izquierda,
  un panel con los datos del proyecto (antes en un diálogo aparte), las
  unidades, la normativa como selector segmentado y abrir/guardar. A la
  derecha, las tarjetas **Viga** y **Losa en una dirección**, cada una con el
  nombre del elemento, y la lista de **estudios recientes**: los últimos
  abiertos o guardados, que se abren con doble clic o Enter. La lista vive en
  la configuración del usuario, no en el estudio, y descarta los archivos que
  ya no existen.
- **Pestaña «Geometría y sección» rediseñada.** La forma se elige con tres
  mosaicos (Rectangular, T, L); dimensiones y materiales usan campos con
  botones −/+ y la unidad adentro; «Continuar a Flexión» pasa a la pestaña
  siguiente. A la derecha, la sección acotada con dos capas que se prenden y
  apagan (recubrimiento y centroide) y una franja con las propiedades de la
  sección bruta: A_g, ȳ, I_g, E_c (según la norma activa) y β₁.
- La cabecera del elemento muestra la forma como etiqueta y las pestañas van
  numeradas en el orden de trabajo.
- **Tema Nocturne** en toda la aplicación: fondo gris azulado, un solo acento
  violeta, botones con contorno, tarjetas con filo de 1 px y colores de estado
  desaturados. Usa la fuente Inter si está instalada y, si no, Segoe UI.
- Cada elemento tiene su propio espacio de trabajo con pestañas
  **Geometría · Flexión · Cortante**. La geometría (forma, dimensiones y
  materiales) se define una sola vez, con un esquema acotado de la sección, y
  la leen los análisis: los formularios de flexión y cortante ya no la repiten
  y no hace falta desplazarse para llegar a los datos propios de cada uno.

### Corregido

- El grupo «Sección con ala» de resultados mostraba `b_f`, `h_f` y el límite
  de `b_f` diez veces más chicos (convertía la unidad dos veces).

## [2.2.0]

### Agregado

- **Secciones de viga con ala: T y L.** Un selector en la geometría de
  «Viga · Flexión» elige la forma, y con ella aparecen el ancho efectivo del
  ala `b_f` y su espesor `h_f`. **Los resultados de la sección rectangular no
  cambian**: está verificado contra la versión anterior, caso por caso y token
  a token en la memoria.
  - Flexión: el bloque de compresión se resuelve sobre el área realmente
    comprimida. Si cabe dentro del ala, la sección responde como rectangular de
    ancho `b_f`; si el eje neutro baja al alma, se separa el aporte de los
    voladizos del ala (`A_sf`) del aporte del alma. El brazo de palanca pasa a
    ser `d − ȳ`, con `ȳ` el centroide real de la compresión, que ya no es
    `a/2`.
  - `A_s,mín` se sigue midiendo sobre el alma (ACI 318-19 §9.6.1.2 con el ala
    comprimida) y `A_s,máx` pasa a calcularse sobre el área comprimida a
    `ε_t = 0.004`, porque `ρ_max·b·d` sólo vale en sección rectangular.
  - En AASHTO, el `M_cr` de §5.6.3.3 usa el módulo de sección de la T
    (`I_g/y_inf`) en vez de `b·h²/6`, y el `d_v` de §5.7.2.8 se mide contra el
    brazo real `d_e − ȳ`.
  - Torsión: `A_cp` y `p_cp` incluyen el voladizo del ala que admite
    §22.7.4.1, limitado al menor entre el voladizo real, la proyección del alma
    bajo el ala y `4·h_f`. `A_oh` y `p_h` siguen siendo los del estribo cerrado
    del alma, que es el lado seguro. La memoria deja dicho que esto vale sólo
    si el ala es monolítica con el alma.
  - El cortante no cambia: `b_v` es y sigue siendo el ancho del alma.
- El diagrama de esfuerzos dibuja la sección real —T o L, con el alma centrada
  o al borde— y sombrea el bloque de compresión sobre el ancho que
  efectivamente comprime.
- La memoria desarrolla el cálculo por partes (ala + alma) con sus fórmulas, y
  el cajetín dice la forma de la sección.
- Se verifica el límite de `b_f` por espesor de ala (ACI 318-19 Tabla 6.3.2.1:
  `8h_f` por lado en T, `6h_f` en L) y se advierte si se excede. Los otros dos
  límites de esa tabla dependen de la luz y de la separación entre almas, que
  la aplicación no pide: la memoria lo dice explícitamente.

### Cambiado

- El archivo del estudio pasa a **v3** y guarda la forma de la sección. Los
  `.json` de la 2.1.0 se abren igual y se interpretan como viga rectangular.
  La versión sube en vez de agregar la clave en silencio porque una versión
  anterior leería un estudio de viga T como rectangular y daría un número
  distinto sin avisar.
- En la pestaña de cortante, «b» se identifica como el ancho del alma cuando la
  viga tiene ala. La forma se define una sola vez, en flexión, y de ahí la
  toman el `d_v` de AASHTO y el `A_cp` de torsión.

### Alcance

- Se modela el **ala comprimida**, es decir momento positivo. Para una zona de
  momento negativo, donde el ala queda traccionada, corresponde elegir sección
  rectangular con el ancho del alma.
- La losa sigue siendo una franja rectangular de 1 m: no tiene selector de
  forma.

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

"""Generador de memoria de cálculo HTML + LaTeX (MathJax).

Hay una memoria por elemento, no por análisis:

- :func:`generate_beam_report`  → viga: flexión, cortante y torsión.
- :func:`generate_slab_report`  → losa: flexión y cortante.

Cada documento es autocontenido (datos de entrada unificados, cálculos paso a
paso con referencias a la norma usada, advertencias y un resumen global) y está
estilizado para imprimir en A4. Los ``_*_fragments`` arman cada parte y reciben
el número de sección que les toca dentro del documento final.

Las dos normas comparten la mayor parte del documento —datos de entrada,
geometría, bloque de compresión, fuerzas internas, separaciones— y difieren en
unos pocos bloques de cálculo. Esos bloques los arman los ``_*_steps``, uno por
norma, y el resto del armado es común.
"""
import math
from datetime import datetime
from html import escape
from typing import Optional

from core.design_code import DesignCode, code_of, spec
from core.flexion import FlexionDesignResult
from core.project import ProjectInfo
from core.version import APP_NAME, __version__
from core.bar_tables import REBAR_SIZES
from core.units import UnitSystem, get_converter
from core.shear import BeamShearResult, SlabShearResult
from core.torsion import BeamShearTorsionResult


def _ref(code: DesignCode, seccion: str) -> str:
    """Etiqueta de referencia normativa, con el prefijo de la norma activa."""
    prefijo = "ACI 318-19" if code is DesignCode.ACI_318_19 else "AASHTO LRFD"
    return f'<span class="aci-ref">{prefijo} {seccion}</span>'


# Las etiquetas que devuelve core.aashto.shear.dv_effective son texto plano,
# pensado también para la interfaz; en la memoria se muestran como fórmula.
_DV_TEX = {
    "d_e − a/2": r"d_e - a/2",
    "0.9·d_e": r"0.9\,d_e",
    "0.72·h": r"0.72\,h",
}


def _dv_tex(etiqueta: str) -> str:
    """La rama que gobierna d_v, escrita como matemática inline."""
    tex = _DV_TEX.get(etiqueta)
    return f"${tex}$" if tex else escape(etiqueta)


def _bar_label(db_mm: float) -> str:
    """Devuelve '#N' para un diámetro dado (mejor coincidencia)."""
    for r in REBAR_SIZES:
        if abs(r.diameter_mm - db_mm) < 0.1:
            return f"#{r.number}"
    return f"db={db_mm:.1f}mm"


def _fmt_layer(layer, cv) -> str:
    return f"{layer.n_bars} × {_bar_label(layer.bar_diameter_mm)}"


def _aci_flexion_steps(result: FlexionDesignResult, cv) -> dict:
    """Bloques de cálculo de flexión propios de ACI 318-19."""
    A = lambda cm2, d=2: cv.format_area(cm2, d)
    M = lambda knm, d=2: f"{knm / cv.moment_to_knm:.{d}f} {cv.moment_unit}"

    fc, fy = result.fc_mpa, result.fy_mpa
    b, d = result.b_mm, result.d_mm
    beta_1 = result.beta_1
    mu_nmm = result.mu_demand_knm * 1e6
    m_val = fy / (0.85 * fc) if fc > 0 else 0.0
    rho_max = (0.85 * beta_1 * fc / fy) * (0.003 / 0.007) if fy > 0 else 0.0
    term1 = (0.25 * math.sqrt(fc) / fy * b * d / 100) if fy > 0 else 0.0
    term2 = (1.4 / fy * b * d / 100) if fy > 0 else 0.0
    as_prov_mm2 = result.as_provided_cm2 * 100.0

    return {
        "phi": 0.9,
        "alpha_1": 0.85,
        "alpha_tex": "0.85",
        "whitney_title": "Bloque equivalente de esfuerzos (Whitney)",
        "whitney_ref": _ref(DesignCode.ACI_318_19, "§22.2.2.4"),
        "spacing_ref": _ref(DesignCode.ACI_318_19, "§25.2.1 / §25.2.2"),
        "beta_block": f"""
<h3>2.1 Factor de reducción $\\beta_1$
  {_ref(DesignCode.ACI_318_19, "§22.2.2.4.3")}
</h3>
<p>El factor $\\beta_1$ relaciona la profundidad del bloque de esfuerzos equivalente
con la profundidad al eje neutro:</p>

<div class="step">
  <div class="step-title">Cálculo de $\\beta_1$</div>
  $$\\beta_1 = \\begin{{cases}}
    0.85 & \\text{{si }} f'_c \\le 28\\,\\text{{MPa}} \\\\
    0.85 - 0.05 \\cdot \\dfrac{{f'_c - 28}}{{7}} \\ge 0.65 & \\text{{si }} f'_c > 28\\,\\text{{MPa}}
  \\end{{cases}}$$
  $$\\beta_1 = {beta_1:.3f}$$
</div>
""",
        "required_block": f"""
<h3>2.3 Cuantía requerida
  {_ref(DesignCode.ACI_318_19, "§22.2")}
</h3>
<p>A partir del equilibrio de la sección y aplicando $\\phi = 0.9$ para flexión
controlada por tracción:</p>

<div class="step">
  <div class="step-title">Resistencia nominal requerida</div>
  $$R_n = \\dfrac{{M_u}}{{\\phi \\cdot b \\cdot d^2}} =
    \\dfrac{{{mu_nmm:.0f}}}{{0.9 \\cdot {b:.1f} \\cdot {d:.2f}^2}} =
    {result.rn:.4f}\\;\\text{{MPa}}$$
</div>

<div class="step">
  <div class="step-title">Constante $m$</div>
  $$m = \\dfrac{{f_y}}{{0.85 \\cdot f'_c}} =
    \\dfrac{{{fy:.1f}}}{{0.85 \\cdot {fc:.1f}}} = {m_val:.3f}$$
</div>

<div class="step">
  <div class="step-title">Cuantía requerida</div>
  $$\\rho_{{req}} = \\dfrac{{1}}{{m}} \\left( 1 - \\sqrt{{1 - \\dfrac{{2\\,m\\,R_n}}{{f_y}}}} \\right) = {result.rho_required:.5f}$$
</div>

<div class="step">
  <div class="step-title">Área de acero requerida</div>
  $$A_{{s,req}} = \\rho_{{req}} \\cdot b \\cdot d =
    {result.rho_required:.5f} \\cdot {b:.1f} \\cdot {d:.2f} =
    {result.as_required_cm2*100:.1f}\\;\\text{{mm}}^2 = {A(result.as_required_cm2)}$$
</div>
""",
        "min_block": f"""
<h3>2.4 Acero mínimo
  {_ref(DesignCode.ACI_318_19, "§9.6.1.2")}
</h3>
<div class="step">
  <div class="step-title">Cálculo de $A_{{s,min}}$</div>
  $$A_{{s,min}} = \\max\\left( \\dfrac{{0.25\\sqrt{{f'_c}}}}{{f_y}},\\; \\dfrac{{1.4}}{{f_y}} \\right) \\cdot b \\cdot d$$
  $$\\dfrac{{0.25\\sqrt{{{fc:.1f}}}}}{{{fy:.1f}}} \\cdot b \\cdot d = {term1*100:.1f}\\;\\text{{mm}}^2$$
  $$\\dfrac{{1.4}}{{{fy:.1f}}} \\cdot b \\cdot d = {term2*100:.1f}\\;\\text{{mm}}^2$$
  $$A_{{s,min}} = {A(result.as_min_cm2)}$$
</div>
""",
        "max_block": f"""
<h3>2.5 Acero máximo
  {_ref(DesignCode.ACI_318_19, "§21.2 — Condición de tracción controlada")}
</h3>
<p>Para que la falla sea dúctil ($\\varepsilon_t \\ge 0.004$):</p>
<div class="step">
  <div class="step-title">Cálculo de $\\rho_{{max}}$ y $A_{{s,max}}$</div>
  $$\\rho_{{max}} = \\dfrac{{0.85 \\beta_1 f'_c}}{{f_y}} \\cdot \\dfrac{{0.003}}{{0.003 + 0.004}} = {rho_max:.5f}$$
  $$A_{{s,max}} = \\rho_{{max}} \\cdot b \\cdot d = {A(result.as_max_cm2)}$$
</div>
""",
        "capacity_block": f"""
<h3>2.8 Momento resistente nominal y reducido</h3>
<div class="step">
  <div class="step-title">Capacidad de la sección</div>
  $$M_n = A_s f_y \\left( d - \\dfrac{{a}}{{2}} \\right) =
    {as_prov_mm2:.1f} \\cdot {fy:.1f} \\cdot {result.jd_mm:.2f} =
    {result.phi_mn_knm/0.9*1e6:.0f}\\;\\text{{N·mm}}$$
  $$\\phi M_n = 0.9 \\cdot M_n = {result.phi_mn_knm:.2f}\\;\\text{{kN·m}} = {M(result.phi_mn_knm)}$$
</div>
""",
        "verification_rows": f"""
  <tr>
    <td>Acero máximo</td>
    <td>$A_{{s,max}}$</td>
    <td class="num">{A(result.as_max_cm2)}</td>
  </tr>
""",
        "extra_sections": "",
    }


def _aashto_flexion_steps(result, cv) -> dict:
    """Bloques de cálculo de flexión propios de AASHTO LRFD 2020."""
    A = lambda cm2, d=2: cv.format_area(cm2, d)
    M = lambda knm, d=2: f"{knm / cv.moment_to_knm:.{d}f} {cv.moment_unit}"
    L = lambda mm, d=1: cv.format_length_small(mm, d)
    S = lambda mpa, d=1: f"{mpa / cv.stress_to_mpa:.{d}f} {cv.stress_unit}"

    fc, fy = result.fc_mpa, result.fy_mpa
    b, d = result.b_mm, result.d_mm
    a1 = result.alpha_1
    phi = result.phi_flexion
    as_prov_mm2 = result.as_provided_cm2 * 100.0
    mn_knm = result.phi_mn_knm / phi if phi > 0 else 0.0

    comportamiento_chip = {
        "TRACCIÓN CONTROLADA": "ok",
        "TRANSICIÓN": "warn",
        "COMPRESIÓN CONTROLADA": "fail",
    }.get(result.section_behaviour, "warn")

    # --- Control de fisuración, sólo si hay momento de servicio ---
    if result.crack_control_applies:
        chip = "ok" if result.crack_control_ok else "fail"
        texto = "CUMPLE" if result.crack_control_ok else "NO CUMPLE"
        fisuracion = f"""
<h3>3.4 Control de fisuración
  {_ref(DesignCode.AASHTO_LRFD_2020, "§5.6.7")}
</h3>
<p>La separación del refuerzo en estado límite de servicio se limita para
controlar el ancho de fisura. Con el momento de servicio
$M_s = {M(result.ms_knm)}$ y exposición clase {result.exposure_class}
($\\gamma_e = {result.gamma_e:.2f}$):</p>

<div class="step">
  <div class="step-title">Esfuerzo del acero en servicio</div>
  <p>De la sección fisurada transformada, con $n = E_s/E_c$:</p>
  $$f_{{ss}} = \\dfrac{{M_s}}{{A_s \\, j \\, d}} = {S(result.fss_mpa)}
    \\quad (\\le 0.6\\,f_y = {S(0.6*fy)})$$
</div>

<div class="step">
  <div class="step-title">Separación máxima admisible</div>
  $$d_c = {L(result.dc_mm, 2)}, \\qquad
    \\beta_s = 1 + \\dfrac{{d_c}}{{0.7\\,(h - d_c)}} = {result.beta_s:.3f}$$
  $$s_{{max}} = \\dfrac{{123000 \\, \\gamma_e}}{{\\beta_s \\, f_{{ss}}}} - 2 d_c =
    \\dfrac{{123000 \\cdot {result.gamma_e:.2f}}}{{{result.beta_s:.3f} \\cdot {result.fss_mpa:.1f}}}
    - 2 \\cdot {result.dc_mm:.1f} = {result.crack_spacing_max_mm:.0f}\\;\\text{{mm}}$$
</div>

<table class="data">
  <tr>
    <td>Separación real (centro a centro)</td>
    <td>$s$</td>
    <td class="num">{L(result.crack_spacing_mm, 1) if result.crack_spacing_mm > 0 else '—'}</td>
  </tr>
  <tr>
    <td>Separación máxima admisible</td>
    <td>$s_{{max}}$</td>
    <td class="num">{L(result.crack_spacing_max_mm, 1)}
      <span class="chip {chip}">{texto}</span>
    </td>
  </tr>
</table>
"""
    else:
        fisuracion = f"""
<h3>3.4 Control de fisuración
  {_ref(DesignCode.AASHTO_LRFD_2020, "§5.6.7")}
</h3>
<div class="alert alert-info">
  <p>No se revisó: el control de fisuración necesita el <b>momento de
  servicio</b> $M_s$, que no se ingresó. Cargalo en el panel de datos para
  incluir esta verificación.</p>
</div>
"""

    min_chip = "ok" if result.min_reinf_ok else "fail"
    min_texto = "CUMPLE" if result.min_reinf_ok else "NO CUMPLE"

    return {
        "phi": phi,
        "alpha_1": a1,
        "alpha_tex": f"{a1:.2f}",
        "whitney_title": "Bloque rectangular equivalente de esfuerzos",
        "whitney_ref": _ref(DesignCode.AASHTO_LRFD_2020, "§5.6.2.2"),
        "spacing_ref": _ref(DesignCode.AASHTO_LRFD_2020, "§5.10.3.1"),
        "beta_block": f"""
<h3>2.1 Factores del bloque de compresión $\\alpha_1$ y $\\beta_1$
  {_ref(DesignCode.AASHTO_LRFD_2020, "§5.6.2.2")}
</h3>
<p>El bloque rectangular equivalente tiene un esfuerzo $\\alpha_1 f'_c$ sobre una
profundidad $a = \\beta_1 c$:</p>

<div class="step">
  <div class="step-title">Cálculo de $\\beta_1$</div>
  $$\\beta_1 = \\begin{{cases}}
    0.85 & \\text{{si }} f'_c \\le 28\\,\\text{{MPa}} \\\\
    0.85 - 0.05 \\cdot \\dfrac{{f'_c - 28}}{{7}} \\ge 0.65 & \\text{{si }} f'_c > 28\\,\\text{{MPa}}
  \\end{{cases}}$$
  $$\\beta_1 = {result.beta_1:.3f}$$
</div>

<div class="step">
  <div class="step-title">Cálculo de $\\alpha_1$</div>
  <p>Vale 0.85 hasta 70 MPa; por encima baja 0.02 por cada 7 MPa, con piso 0.75.</p>
  $$\\alpha_1 = {a1:.3f}$$
</div>
""",
        "required_block": f"""
<h3>2.3 Acero requerido
  {_ref(DesignCode.AASHTO_LRFD_2020, "§5.6.3.2")}
</h3>
<p>A diferencia de ACI 318-19, en AASHTO el factor $\\phi$ <b>no es constante</b>:
depende de la deformación $\\varepsilon_t$ del acero extremo en tracción, que a su
vez depende del acero colocado. El área requerida se obtiene iterando hasta que
$\\phi$ se estabiliza.</p>

<div class="step">
  <div class="step-title">Resistencia nominal requerida</div>
  $$R_n = \\dfrac{{M_u}}{{\\phi \\cdot b \\cdot d^2}} =
    \\dfrac{{{result.mu_demand_knm*1e6:.0f}}}{{{phi:.3f} \\cdot {b:.1f} \\cdot {d:.2f}^2}} =
    {result.rn:.4f}\\;\\text{{MPa}}$$
</div>

<div class="step">
  <div class="step-title">Área de acero requerida</div>
  $$\\rho_{{req}} = {result.rho_required:.5f} \\qquad
    A_{{s,req}} = \\rho_{{req}} \\cdot b \\cdot d =
    {result.as_required_cm2*100:.1f}\\;\\text{{mm}}^2 = {A(result.as_required_cm2)}$$
</div>
""",
        "min_block": f"""
<h3>2.4 Refuerzo mínimo
  {_ref(DesignCode.AASHTO_LRFD_2020, "§5.6.3.3")}
</h3>
<p>AASHTO plantea el mínimo como un <b>criterio de momento</b>, no de área: la
sección debe resistir el menor entre $1.33\\,M_u$ y el momento de fisuración
$M_{{cr}}$, para que el acero no fluya al fisurarse el concreto.</p>

<div class="step">
  <div class="step-title">Módulo de rotura {_ref(DesignCode.AASHTO_LRFD_2020, "§5.4.2.6")}</div>
  $$f_r = 0.62 \\, \\lambda \\sqrt{{f'_c}} = 0.62 \\sqrt{{{fc:.1f}}} =
    {result.fr_mpa:.3f}\\;\\text{{MPa}}$$
</div>

<div class="step">
  <div class="step-title">Momento de fisuración</div>
  $$S_c = \\dfrac{{b\\,h^2}}{{6}} = {result.sc_mm3:.0f}\\;\\text{{mm}}^3$$
  $$M_{{cr}} = \\gamma_3 \\, \\gamma_1 \\, f_r \\, S_c =
    {result.gamma_3:.2f} \\cdot {result.gamma_1:.1f} \\cdot {result.fr_mpa:.3f}
    \\cdot {result.sc_mm3:.0f} = {M(result.mcr_knm)}$$
  <p>$\\gamma_1 = 1.6$ (variabilidad del momento de fisuración) y
  $\\gamma_3 = {result.gamma_3:.2f}$ (barras {escape(result.bar_spec)}).</p>
</div>

<div class="step">
  <div class="step-title">Momento mínimo exigido</div>
  $$M_{{u,min}} = \\min(1.33\\,M_u,\\; M_{{cr}}) =
    \\min({M(1.33*result.mu_demand_knm)},\\; {M(result.mcr_knm)}) = {M(result.mu_min_knm)}$$
  <p>Equivale a un área de acero de {A(result.as_min_cm2)}.</p>
</div>
""",
        "max_block": f"""
<h3>2.5 Límite superior del refuerzo
  {_ref(DesignCode.AASHTO_LRFD_2020, "§5.5.4.2 / §5.6.2.1")}
</h3>
<p>AASHTO <b>no fija un $A_{{s,max}}$</b>. En su lugar, cuando la sección se arma
de más, $\\varepsilon_t$ baja y con ella $\\phi$, de modo que el sobrearmado se
penaliza en la resistencia. El valor de abajo es el acero con el que la sección
llega al límite de compresión controlada $\\varepsilon_t = \\varepsilon_{{cl}}$:</p>
<div class="step">
  <div class="step-title">Acero en el límite de compresión controlada</div>
  $$\\varepsilon_{{cl}} = \\dfrac{{f_y}}{{E_s}} = {result.epsilon_cl:.5f}, \\qquad
    \\varepsilon_{{tl}} = {result.epsilon_tl:.5f}$$
  $$A_{{s}}(\\varepsilon_t = \\varepsilon_{{cl}}) = {A(result.as_max_cm2)}$$
</div>
""",
        "capacity_block": f"""
<h3>2.8 Deformación, factor $\\phi$ y momento resistente
  {_ref(DesignCode.AASHTO_LRFD_2020, "§5.5.4.2")}
</h3>
<div class="step">
  <div class="step-title">Deformación del acero extremo en tracción</div>
  $$\\varepsilon_t = \\varepsilon_{{cu}} \\dfrac{{d_t - c}}{{c}} =
    0.003 \\cdot \\dfrac{{{result.dt_mm:.2f} - {result.c_mm:.2f}}}{{{result.c_mm:.2f}}} =
    {result.epsilon_t:.5f}$$
  <p>Comportamiento:
    <span class="chip {comportamiento_chip}">{result.section_behaviour}</span></p>
</div>

<div class="step">
  <div class="step-title">Factor de resistencia</div>
  $$\\phi = \\begin{{cases}}
    0.75 & \\varepsilon_t \\le \\varepsilon_{{cl}} \\\\
    0.75 + 0.15 \\dfrac{{\\varepsilon_t - \\varepsilon_{{cl}}}}{{\\varepsilon_{{tl}} - \\varepsilon_{{cl}}}}
      & \\varepsilon_{{cl}} < \\varepsilon_t < \\varepsilon_{{tl}} \\\\
    0.90 & \\varepsilon_t \\ge \\varepsilon_{{tl}}
  \\end{{cases}}$$
  $$\\phi = {phi:.3f}$$
</div>

<div class="step">
  <div class="step-title">Capacidad de la sección</div>
  $$M_n = A_s f_y \\left( d - \\dfrac{{a}}{{2}} \\right) =
    {as_prov_mm2:.1f} \\cdot {fy:.1f} \\cdot {result.jd_mm:.2f} =
    {mn_knm*1e6:.0f}\\;\\text{{N·mm}}$$
  $$M_r = \\phi M_n = {phi:.3f} \\cdot M_n = {M(result.phi_mn_knm)}$$
</div>
""",
        "verification_rows": f"""
  <tr>
    <td>Momento mínimo exigido</td>
    <td>$M_{{u,min}}$</td>
    <td class="num">{M(result.mu_min_knm)}
      <span class="chip {min_chip}">{min_texto}</span>
    </td>
  </tr>
  <tr>
    <td>Factor de resistencia aplicado</td>
    <td>$\\phi$</td>
    <td class="num">{phi:.3f}</td>
  </tr>
  <tr>
    <td>Deformación del acero extremo</td>
    <td>$\\varepsilon_t$</td>
    <td class="num">{result.epsilon_t:.5f}</td>
  </tr>
""",
        "extra_sections": fisuracion,
    }


def _flexion_steps(result, cv, code: DesignCode) -> dict:
    if code is DesignCode.AASHTO_LRFD_2020:
        return _aashto_flexion_steps(result, cv)
    return _aci_flexion_steps(result, cv)


def _flexion_fragments(
    result: FlexionDesignResult,
    unit_system: UnitSystem,
    section_type: str = "Viga",
    extra_load_rows: str = "",
    extra_material_rows: str = "",
    extra_input_blocks: str = "",
    code: DesignCode = DesignCode.ACI_318_19,
) -> dict:
    """Fragmentos HTML de la parte de flexión de la memoria.

    Devuelve las claves ``inputs`` (sección 1) y ``calc`` (secciones 2 y 3),
    más los datos que la memoria unificada necesita para el resumen final.
    Las secciones de cortante y torsión se numeran a continuación.
    """
    cv = get_converter(unit_system)
    reinf = result.reinforcement

    # Helpers de formato
    L = lambda mm, d=1: cv.format_length_small(mm, d)        # cm/in
    A = lambda cm2, d=2: cv.format_area(cm2, d)
    M = lambda knm, d=2: f"{knm / cv.moment_to_knm:.{d}f} {cv.moment_unit}"
    S = lambda mpa, d=1: f"{mpa / cv.stress_to_mpa:.{d}f} {cv.stress_unit}"

    status_class = {
        "OK": "ok",
        "ARMADO INSUFICIENTE": "fail",
        "AUMENTAR SECCIÓN": "fail",
        "REDUCIR SECCIÓN": "warn",
        "ERROR": "fail",
    }.get(result.status, "warn")

    # Resumen del refuerzo
    if reinf and reinf.layers:
        layers_summary = " + ".join(_fmt_layer(L_, cv) for L_ in reinf.layers)
    else:
        layers_summary = "—"

    # ===== Cálculos paso a paso (valores intermedios para LaTeX) =====
    # Para mostrar números con buena precisión en las ecuaciones, usamos SI (MPa, mm).
    fc = result.fc_mpa
    fy = result.fy_mpa
    b = result.b_mm
    h = result.h_mm
    cover = result.cover_mm
    d = result.d_mm
    a = result.a_mm
    c = result.c_mm
    beta_1 = result.beta_1
    as_req = result.as_required_cm2
    as_min = result.as_min_cm2
    as_prov = result.as_provided_cm2
    rho_prov = result.rho_provided
    as_prov_mm2 = as_prov * 100.0
    c_force = result.compression_kn
    t_force = result.tension_kn
    phi_mn = result.phi_mn_knm

    # Los bloques que cambian con la norma los arma el motor de pasos.
    steps = _flexion_steps(result, cv, code)
    alpha_1 = steps["alpha_1"]
    alpha_tex = steps["alpha_tex"]

    # Cálculo del peralte efectivo - explicación
    if reinf and reinf.layers and result.layer_y_positions_mm:
        db_stirrup = reinf.stirrup_diameter_mm
        db_main = max(L_.bar_diameter_mm for L_ in reinf.layers)
        if len(reinf.layers) == 1:
            d_eq = (rf"d = h - r - d_{{e}} - \dfrac{{d_b}}{{2}} = "
                    rf"{h:.1f} - {cover:.1f} - {db_stirrup:.1f} - "
                    rf"\dfrac{{{db_main:.1f}}}{{2}} = "
                    rf"{d:.2f} \;\text{{mm}}")
            d_expl = (
                "Para un solo lecho, el peralte efectivo se mide desde la "
                "fibra extrema en compresión hasta el centroide del acero "
                "de tensión."
            )
        else:
            d_eq = (rf"\bar{{y}} = \dfrac{{\sum A_{{si}} y_i}}{{\sum A_{{si}}}}, "
                    rf"\quad d = h - \bar{{y}} = {d:.2f} \;\text{{mm}}")
            d_expl = (
                f"Con {len(reinf.layers)} lechos, se calcula el centroide ponderado "
                "del acero de tensión usando las áreas y distancias desde la "
                "fibra extrema inferior. Posiciones desde la fibra inferior: "
                + ", ".join(f"y<sub>{i+1}</sub> = {y:.2f} mm"
                            for i, y in enumerate(result.layer_y_positions_mm))
            )
    else:
        d_eq = rf"d \approx {d:.2f} \;\text{{mm}}"
        d_expl = "Peralte efectivo asumido por defecto."

    # Tabla de barras detallada
    bars_table_rows = ""
    if reinf and reinf.layers:
        for i, layer in enumerate(reinf.layers, 1):
            bars_table_rows += f"""
            <tr>
                <td>Lecho {i}</td>
                <td>{layer.n_bars}</td>
                <td>{_bar_label(layer.bar_diameter_mm)}</td>
                <td>{layer.bar_diameter_mm:.2f} mm</td>
                <td>{layer.area_mm2 / 100:.2f} cm²</td>
            </tr>"""

    # Lista de advertencias
    warnings_html = ""
    if result.warnings:
        warnings_html = (
            '<div class="alert alert-warn"><h3>⚠ Advertencias</h3><ul>'
            + "".join(f"<li>{w}</li>" for w in result.warnings)
            + "</ul></div>"
        )

    # Capacidad
    ratio = phi_mn / result.mu_demand_knm if result.mu_demand_knm > 0 else 0
    capacity_class = "ok" if ratio >= 1.0 else "fail"
    capacity_text = "CUMPLE" if ratio >= 1.0 else "NO CUMPLE"

    # Separación
    sep_h_status = "✓ OK" if result.horizontal_spacing_ok else "✗ FALLA"
    sep_v_status = "✓ OK" if result.vertical_spacing_ok else "✗ FALLA"
    sep_h_class = "ok" if result.horizontal_spacing_ok else "fail"
    sep_v_class = "ok" if result.vertical_spacing_ok else "fail"
    sep_v_applies = result.vertical_spacing_mm > 0

    return {
        "inputs": f"""
<!-- ============ 1. DATOS DE ENTRADA ============ -->
<h2>1. Datos de entrada</h2>

<h3>1.1 Solicitación</h3>
<table class="data">
  <tr>
    <td>Momento último de diseño</td>
    <td>$M_u$</td>
    <td class="num">{M(result.mu_demand_knm)}</td>
  </tr>
  {extra_load_rows}
</table>

<h3>1.2 Geometría</h3>
<table class="data">
  <tr>
    <td>Ancho de la sección</td>
    <td>$b$</td>
    <td class="num">{L(b)}</td>
  </tr>
  <tr>
    <td>Altura total</td>
    <td>$h$</td>
    <td class="num">{L(h)}</td>
  </tr>
  <tr>
    <td>Recubrimiento libre</td>
    <td>$r$</td>
    <td class="num">{L(cover)}</td>
  </tr>
</table>

<h3>1.3 Materiales</h3>
<table class="data">
  <tr>
    <td>Resistencia a compresión del concreto</td>
    <td>$f'_c$</td>
    <td class="num">{S(fc)}</td>
  </tr>
  <tr>
    <td>Esfuerzo de fluencia del acero</td>
    <td>$f_y$</td>
    <td class="num">{S(fy)}</td>
  </tr>
  {extra_material_rows}
</table>

<h3>1.4 Refuerzo propuesto</h3>
<table class="data">
  <tr>
    <th>Lecho</th><th>N° barras</th><th>Designación</th>
    <th>Diámetro</th><th>Área total</th>
  </tr>
  {bars_table_rows}
  <tr>
    <td colspan="4"><b>Total acero proporcionado</b></td>
    <td class="num"><b>{A(as_prov)}</b></td>
  </tr>
</table>

{extra_input_blocks}
""",
        "calc": f"""
<!-- ============ 2. CÁLCULOS ============ -->
<h2>2. Cálculos de diseño (flexión)</h2>
{steps["beta_block"]}
<h3>2.2 Peralte efectivo</h3>
<p>{d_expl}</p>
<div class="step">
  <div class="step-title">Cálculo de $d$</div>
  $${d_eq}$$
</div>
{steps["required_block"]}
{steps["min_block"]}
{steps["max_block"]}
<h3>2.6 {steps["whitney_title"]}
  {steps["whitney_ref"]}
</h3>
<p>Con el acero proporcionado $A_{{s}} = {A(as_prov)}$:</p>
<div class="step">
  <div class="step-title">Profundidad del bloque equivalente $a$</div>
  $$a = \\dfrac{{A_s f_y}}{{{alpha_tex} f'_c b}} =
    \\dfrac{{{as_prov_mm2:.1f} \\cdot {fy:.1f}}}{{{alpha_tex} \\cdot {fc:.1f} \\cdot {b:.1f}}} =
    {a:.2f}\\;\\text{{mm}} = {L(a, 2)}$$
</div>
<div class="step">
  <div class="step-title">Profundidad al eje neutro $c$</div>
  $$c = \\dfrac{{a}}{{\\beta_1}} = \\dfrac{{{a:.2f}}}{{{beta_1:.3f}}} =
    {c:.2f}\\;\\text{{mm}} = {L(c, 2)}$$
</div>
<div class="step">
  <div class="step-title">Brazo de palanca $jd$</div>
  $$jd = d - \\dfrac{{a}}{{2}} = {d:.2f} - \\dfrac{{{a:.2f}}}{{2}} =
    {result.jd_mm:.2f}\\;\\text{{mm}} = {L(result.jd_mm, 2)}$$
</div>

<h3>2.7 Fuerzas internas</h3>
<div class="step">
  <div class="step-title">Resultante de compresión $C$</div>
  $$C = {alpha_tex} \\cdot f'_c \\cdot b \\cdot a =
    {alpha_tex} \\cdot {fc:.1f} \\cdot {b:.1f} \\cdot {a:.2f} =
    {c_force*1000:.0f}\\;\\text{{N}} = {c_force:.2f}\\;\\text{{kN}}$$
</div>
<div class="step">
  <div class="step-title">Resultante de tensión $T$</div>
  $$T = A_s \\cdot f_y = {as_prov_mm2:.1f} \\cdot {fy:.1f} =
    {t_force*1000:.0f}\\;\\text{{N}} = {t_force:.2f}\\;\\text{{kN}}$$
</div>
<p>Verificación de equilibrio: $C \\approx T$ &nbsp;<span class="chip {'ok' if abs(c_force - t_force) < 0.5 else 'fail'}">{'CUMPLE' if abs(c_force - t_force) < 0.5 else 'NO CUMPLE'}</span></p>
{steps["capacity_block"]}
<!-- ============ 3. VERIFICACIONES ============ -->
<h2>3. Verificaciones (flexión)</h2>

<h3>3.1 Capacidad vs Demanda</h3>
<table class="data">
  <tr>
    <td>Momento resistente reducido</td>
    <td>$\\phi M_n$</td>
    <td class="num">{M(phi_mn)}</td>
  </tr>
  <tr>
    <td>Momento último de diseño</td>
    <td>$M_u$</td>
    <td class="num">{M(result.mu_demand_knm)}</td>
  </tr>
  <tr>
    <td>Relación capacidad/demanda</td>
    <td>$\\phi M_n / M_u$</td>
    <td class="num">{ratio:.3f}
      <span class="chip {capacity_class}">{capacity_text}</span>
    </td>
  </tr>
</table>

<h3>3.2 Verificación de acero</h3>
<table class="data">
  <tr>
    <td>Acero requerido</td>
    <td>$A_{{s,req}}$</td>
    <td class="num">{A(as_req)}</td>
  </tr>
  <tr>
    <td>Acero mínimo</td>
    <td>$A_{{s,min}}$</td>
    <td class="num">{A(as_min)}</td>
  </tr>
{steps["verification_rows"]}
  <tr>
    <td><b>Acero proporcionado</b></td>
    <td>$A_s$</td>
    <td class="num"><b>{A(as_prov)}</b>
      <span class="chip {'ok' if as_prov >= max(as_req, as_min) else 'fail'}">
        {'CUMPLE' if as_prov >= max(as_req, as_min) else 'NO CUMPLE'}
      </span>
    </td>
  </tr>
  <tr>
    <td>Cuantía proporcionada</td>
    <td>$\\rho$</td>
    <td class="num">{rho_prov:.5f}</td>
  </tr>
</table>

<h3>3.3 Separación entre barras
  {steps["spacing_ref"]}
</h3>
<p>La separación libre mínima requerida es:</p>
$$s_{{min}} = \\max(d_b,\\; 25\\,\\text{{mm}})$$

<table class="data">
  <tr>
    <th>Dirección</th>
    <th>Calculada</th>
    <th>Mínima</th>
    <th>Estado</th>
  </tr>
  <tr>
    <td>Horizontal</td>
    <td class="num">{L(result.horizontal_spacing_mm, 1) if result.horizontal_spacing_mm > 0 else '—'}</td>
    <td class="num">{L(result.horizontal_spacing_min_mm, 1)}</td>
    <td><span class="chip {sep_h_class}">{sep_h_status}</span></td>
  </tr>
  <tr>
    <td>Vertical (entre lechos)</td>
    <td class="num">{L(result.vertical_spacing_mm, 1) if sep_v_applies else 'n/a'}</td>
    <td class="num">{L(result.vertical_spacing_min_mm, 1)}</td>
    <td>{('<span class="chip ' + sep_v_class + '">' + sep_v_status + '</span>') if sep_v_applies else '<i>no aplica</i>'}</td>
  </tr>
</table>
{steps["extra_sections"]}
""",
        "warnings": warnings_html,
        "ratio": ratio,
        "status_class": status_class,
        "layers_summary": layers_summary,
    }


# ============================================================
#         Plantilla y estilos comunes a todas las memorias
# ============================================================

_REPORT_CSS = """
@page { size: A4; margin: 2cm 2cm 2.5cm 2.5cm; }
* { box-sizing: border-box; }
body { font-family: 'Cambria', 'Georgia', 'Times New Roman', serif;
       font-size: 11pt; line-height: 1.5; color: #000; background: #fff;
       margin: 0; padding: 0; }
.page { max-width: 21cm; margin: 0 auto; padding: 2.5cm 2cm; background: #fff; }
.doc-header { text-align: center; border-bottom: 3px double #000;
              padding-bottom: 12px; margin-bottom: 24px; }
.doc-header h1 { font-size: 18pt; margin: 0 0 4px 0; text-transform: uppercase;
                 letter-spacing: 1px; }
.doc-header .subtitle { font-size: 11pt; font-style: italic; color: #444; margin: 0; }
.metadata { display: grid; grid-template-columns: max-content 1fr max-content 1fr;
            gap: 4px 12px; font-size: 10pt; margin-bottom: 24px; padding: 8px 12px;
            border: 1px solid #999; background: #f5f5f5; }
.metadata .label { font-weight: bold; }
.doc-notes { font-size: 10pt; margin: -16px 0 24px 0; padding: 8px 12px;
             border: 1px solid #999; border-top: none; background: #fcfcfc; }
h2 { font-size: 14pt; margin: 24px 0 10px 0; padding-bottom: 4px;
     border-bottom: 2px solid #333; page-break-after: avoid; }
h3 { font-size: 12pt; margin: 16px 0 6px 0; color: #222; page-break-after: avoid; }
p { margin: 6px 0; text-align: justify; }
.aci-ref { display: inline-block; font-size: 9pt; font-style: italic; color: #555;
           background: #eef; padding: 1px 6px; border-left: 3px solid #336; margin-left: 6px; }
.step { margin: 12px 0; padding: 8px 12px; border-left: 3px solid #ccc;
        background: #fafafa; page-break-inside: avoid; }
.step .step-title { font-weight: bold; color: #333; margin-bottom: 4px; }
table.data { width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 10.5pt; }
table.data th, table.data td { border: 1px solid #888; padding: 5px 8px; text-align: left; }
table.data th { background: #ddd; font-weight: bold; }
table.data td.num { text-align: right;
                    font-family: 'Cambria Math', 'Consolas', monospace; }
table.data tr:nth-child(even) td { background: #f7f7f7; }
.result-summary { margin: 20px 0; padding: 14px; border: 2px solid; page-break-inside: avoid; }
.result-summary.ok   { border-color: #0a6; background: #f0fff4; }
.result-summary.fail { border-color: #c00; background: #fff0f0; }
.result-summary.warn { border-color: #c70; background: #fffaf0; }
.result-summary h3 { margin: 0 0 8px 0; font-size: 13pt; }
.result-summary.ok h3::before   { content: "✓ "; }
.result-summary.fail h3::before { content: "✗ "; }
.result-summary.warn h3::before { content: "⚠ "; }
.alert { margin: 16px 0; padding: 10px 14px; border-left: 4px solid; }
.alert-warn { background: #fff8e1; border-color: #c70; }
.alert-warn h3 { margin-top: 0; color: #850; }
.alert-info { background: #eef4ff; border-color: #36c; }
.alert-info h3 { margin-top: 0; color: #245; }
.alert-info p { margin: 0; }
.chip { display: inline-block; padding: 1px 8px; border-radius: 10px;
        font-size: 9pt; font-weight: bold; }
.chip.ok   { background: #d4edda; color: #155724; border: 1px solid #28a745; }
.chip.fail { background: #f8d7da; color: #721c24; border: 1px solid #dc3545; }
.doc-footer { margin-top: 40px; padding-top: 8px; border-top: 1px solid #888;
              font-size: 9pt; color: #555; text-align: center; }
.print-bar { position: sticky; top: 0; background: #2c3e50; color: #fff;
             padding: 8px 16px; display: flex; gap: 12px; align-items: center;
             z-index: 100; box-shadow: 0 2px 6px rgba(0,0,0,0.2); }
.print-bar button { background: #3498db; color: #fff; border: none;
                    padding: 6px 14px; border-radius: 4px; cursor: pointer; font-size: 10pt; }
.print-bar button:hover { background: #5dade2; }
@media print { .print-bar { display: none; } body { background: #fff; }
               .page { box-shadow: none; padding: 0; } .step { background: transparent; } }
@media screen { body { background: #e8e8e8; padding: 0; }
                .page { box-shadow: 0 4px 16px rgba(0,0,0,0.15);
                        margin-top: 20px; margin-bottom: 20px; } }
"""


def _document(
    body_inner: str, title: str, element_name: str, kind: str = "Cortante"
) -> str:
    """Plantilla HTML+MathJax común a todas las memorias."""
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<script>
window.MathJax = {{
  tex: {{
    inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
    displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
    processEscapes: true, tags: 'ams'
  }},
  svg: {{ fontCache: 'global' }}
}};
</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
<style>{_REPORT_CSS}</style>
</head>
<body>
<div class="print-bar">
  <strong>📄 Memoria de Cálculo — {kind}</strong>
  <button onclick="window.print()">🖨 Imprimir / Guardar PDF</button>
  <span style="margin-left:auto; font-size:10pt;">{element_name}</span>
</div>
<div class="page">
{body_inner}
</div>
</body>
</html>
"""


def _torsion_report_block(t: BeamShearTorsionResult, L, F, S, M, A, sec: int = 3,
                          code: DesignCode = DesignCode.ACI_318_19) -> str:
    """Sección de la memoria: cálculos de torsión y combinación V + T."""
    if code is DesignCode.AASHTO_LRFD_2020:
        return _aashto_torsion_block(t, L, F, S, M, A, sec)
    return _aci_torsion_block(t, L, F, S, M, A, sec)


def _aashto_torsion_block(t, L, F, S, M, A, sec: int = 3) -> str:
    """Torsión y combinación V + T según AASHTO LRFD 2020."""
    fc = t.fc_mpa
    fyt = t.fyt_mpa
    fy_l = t.fy_long_mpa
    tcr_nmm = t.t_cr_knm * 1e6

    header = f"""
<h2>{sec}. Cálculos de diseño (torsión)</h2>

<h3>{sec}.1 Torsión de agrietamiento y umbral
  {_ref(DesignCode.AASHTO_LRFD_2020, "§5.7.2.1")}
</h3>
<p>AASHTO usa una sola torsión de referencia —la de agrietamiento— y permite
despreciar la torsión cuando no llega a un cuarto de ella:</p>
<div class="step">
  <div class="step-title">$T_{{cr}} = 0.125\\,\\lambda \\sqrt{{f'_c}}
    \\left(\\dfrac{{A_{{cp}}^2}}{{p_c}}\\right)$</div>
  $$T_{{cr}} = 0.125 \\cdot {t.lam:.2f} \\cdot \\sqrt{{{fc:.1f}}} \\cdot
    \\dfrac{{{t.acp_mm2:.0f}^2}}{{{t.pcp_mm:.0f}}}
    = {tcr_nmm:.0f}\\;\\text{{N·mm}} = {M(t.t_cr_knm)}$$
  $$\\text{{Umbral}} = 0.25\\,\\phi\\,T_{{cr}} = 0.25 \\cdot 0.90 \\cdot
    {M(t.t_cr_knm)} = {M(t.phi_t_th_knm)}$$
</div>
<table class="data">
  <tr><td>$T_u$</td><td class="num">{M(t.tu_knm)}</td></tr>
  <tr><td>$0.25\\,\\phi T_{{cr}}$</td><td class="num">{M(t.phi_t_th_knm)}</td></tr>
</table>
"""

    if t.torsion_regime != "DISEÑO":
        return header + """
<div class="result-summary ok">
  <h3>Torsión despreciable</h3>
  <p>$T_u \\le 0.25\\,\\phi T_{cr}$ — la torsión puede despreciarse (AASHTO
  §5.7.2.1) y el armado transversal queda gobernado exclusivamente por el
  cortante.</p>
</div>
"""

    sec_ok = t.section_ok
    vu_eq_n = t.vu_equivalent_kn * 1000.0

    long_bars_html = ""
    if t.long_bars is not None:
        lb = t.long_bars
        long_bars_html = f"""
<p>Distribución sugerida del acero longitudinal faltante, repartido en el
perímetro de la sección:</p>
<table class="data">
  <tr><td>Número de barras</td><td class="num">{lb.n_bars}</td></tr>
  <tr><td>Diámetro</td><td class="num">#{lb.bar_number} ({lb.bar_diameter_mm:.2f} mm)</td></tr>
  <tr><td>Separación perimetral</td><td class="num">{lb.spacing_mm:.0f} mm</td></tr>
  <tr><td><b>Área provista</b></td><td class="num"><b>{A(lb.area_total_mm2)}</b></td></tr>
</table>
"""

    if t.long_check_applies:
        long_chip = "ok" if t.long_reinf_ok else "fail"
        long_txt = "CUMPLE" if t.long_reinf_ok else "NO CUMPLE"
        long_rows = f"""
  <tr><td>Tracción exigida</td>
      <td class="num">{F(t.long_demand_n / 1000.0)}</td></tr>
  <tr><td>Aporte del acero de flexión $A_s f_y$</td>
      <td class="num">{F(t.long_capacity_n / 1000.0)}
        <span class="chip {long_chip}">{long_txt}</span></td></tr>
  <tr><td><b>$A_l$ adicional necesario</b></td>
      <td class="num"><b>{A(t.al_required_mm2)}</b></td></tr>
"""
    else:
        long_rows = """
  <tr><td colspan="2"><i>No se pudo revisar: hacen falta $M_u$ y el acero de
      flexión de esta misma sección.</i></td></tr>
"""

    return header + f"""
<h3>{sec}.2 Cortante equivalente
  {_ref(DesignCode.AASHTO_LRFD_2020, "§5.7.3.6.2")}
</h3>
<p>En secciones sólidas, AASHTO no compara esfuerzos combinados como ACI: suma
el efecto de la torsión al cortante mediante un cortante equivalente.</p>
<div class="step">
  $$V_{{u,eq}} = \\sqrt{{V_u^2 +
    \\left(\\dfrac{{0.9\\,p_h\\,T_u}}{{2 A_o}}\\right)^2}}
    = \\sqrt{{{t.vu_kn * 1000.0:.0f}^2 +
    \\left(\\dfrac{{0.9 \\cdot {t.ph_mm:.0f} \\cdot {t.tu_knm * 1e6:.0f}}}
    {{2 \\cdot {t.ao_mm2:.0f}}}\\right)^2}}
    = {vu_eq_n:.0f}\\;\\text{{N}} = {F(t.vu_equivalent_kn)}$$
</div>

<h3>{sec}.3 Tope de la sección
  {_ref(DesignCode.AASHTO_LRFD_2020, "§5.7.3.3-2")}
</h3>
<div class="step">
  $$\\dfrac{{V_{{u,eq}}}}{{\\phi\\,b_v d_v}} \\le 0.25 f'_c$$
  $$\\dfrac{{{vu_eq_n:.0f}}}{{0.90 \\cdot {t.b_mm:.1f} \\cdot {t.dv_mm:.2f}}}
    = {t.stress_demand_mpa:.3f}\\;\\text{{MPa}}
    \\quad\\le\\quad 0.25 \\cdot {fc:.1f} = {t.stress_limit_mpa:.3f}\\;\\text{{MPa}}$$
</div>
<table class="data">
  <tr><td>Esfuerzo de demanda</td>
      <td class="num">{t.stress_demand_mpa:.3f} MPa</td></tr>
  <tr><td>Límite $0.25 f'_c$</td>
      <td class="num">{t.stress_limit_mpa:.3f} MPa</td></tr>
  <tr><td><b>Verificación</b></td>
      <td class="num"><span class="chip {'ok' if sec_ok else 'fail'}">
      {'CUMPLE' if sec_ok else 'NO CUMPLE — AUMENTAR SECCIÓN'}</span></td></tr>
</table>

<h3>{sec}.4 Refuerzo transversal por torsión
  {_ref(DesignCode.AASHTO_LRFD_2020, "§5.7.3.6.2")}
</h3>
<div class="step">
  <div class="step-title">$T_n = \\dfrac{{2 A_o A_t f_y \\cot\\theta}}{{s}}$
    &nbsp;→&nbsp; $\\dfrac{{A_t}}{{s}} = \\dfrac{{T_u/\\phi}}{{2 A_o f_y \\cot\\theta}}$</div>
  $$\\dfrac{{A_t}}{{s}} =
    \\dfrac{{{t.tu_knm * 1e6 / 0.90:.0f}}}
           {{2 \\cdot {t.ao_mm2:.0f} \\cdot {fyt:.1f} \\cdot \\cot {t.theta_deg:.0f}°}}
    = {t.at_s_required:.4f}\\;\\text{{mm}}^2/\\text{{mm}}$$
</div>
<p>$A_t$ corresponde a <b>una rama</b> del estribo cerrado más exterior.</p>

<h3>{sec}.5 Refuerzo transversal combinado $V + T$
  {_ref(DesignCode.AASHTO_LRFD_2020, "§5.7.2.5 / §5.7.2.6")}
</h3>
<div class="step">
  <div class="step-title">Demanda combinada</div>
  $$\\dfrac{{A_v + 2A_t}}{{s}} = {t.av_s_required:.4f} + 2({t.at_s_required:.4f})
    = {t.avt_s_required:.4f}\\;\\text{{mm}}^2/\\text{{mm}}$$
  $$\\left(\\dfrac{{A_v}}{{s}}\\right)_{{min}} =
    \\dfrac{{0.083\\sqrt{{f'_c}}\\,b_v}}{{f_y}}
    = {t.avt_s_min:.4f}\\;\\text{{mm}}^2/\\text{{mm}}$$
</div>
<p>Sólo las dos ramas exteriores del estribo cerrado son efectivas en torsión,
mientras que todas las ramas trabajan en cortante. La separación por resistencia
se obtiene entonces exigiendo, por rama exterior:</p>
<div class="step">
  $$\\dfrac{{A_b}}{{s}} \\ge \\dfrac{{A_t}}{{s}} + \\dfrac{{A_v/s}}{{n_{{ramas}}}}
    = {t.at_s_required:.4f} + \\dfrac{{{t.av_s_required:.4f}}}{{{t.stirrup_legs}}}
    \\;\\Rightarrow\\; s \\le {L(t.s_combined_required_mm, 1)}$$
</div>
<table class="data">
  <tr><td>$s$ por resistencia combinada $V+T$</td>
      <td class="num">{L(t.s_combined_required_mm, 1)}</td></tr>
  <tr><td>$s$ por refuerzo mínimo {_ref(DesignCode.AASHTO_LRFD_2020, "§5.7.2.5")}</td>
      <td class="num">{L(t.s_min_required_mm, 1) if t.s_min_required_mm > 0 else '—'}</td></tr>
  <tr><td>$s_{{max}}$ con $V_{{u,eq}}$
      {_ref(DesignCode.AASHTO_LRFD_2020, "§5.7.2.6")}</td>
      <td class="num">{L(t.s_max_mm, 1)}</td></tr>
  <tr><td><b>$s$ ADOPTADO</b></td>
      <td class="num"><b>{L(t.s_adopted_mm, 1)}</b></td></tr>
  <tr><td>$(A_v + 2A_t)/s$ provisto</td>
      <td class="num">{t.avt_s_provided:.4f} mm²/mm</td></tr>
</table>
<p><i>AASHTO no agrega una separación máxima propia de torsión: a diferencia de
ACI 318-19 §9.7.6.3.3, no aparece el límite $\\min(p_h/8,\\,300\\,\\text{{mm}})$.</i></p>

<h3>{sec}.6 Refuerzo longitudinal para $M + V + T$
  {_ref(DesignCode.AASHTO_LRFD_2020, "§5.7.3.6.3")}
</h3>
<p>AASHTO no calcula un $A_l$ independiente como ACI: exige que el acero
longitudinal cubra, en conjunto, el momento, el cortante y la torsión.</p>
<div class="step">
  $$A_s f_y \\ge \\dfrac{{|M_u|}}{{\\phi_f d_v}} + \\cot\\theta
    \\sqrt{{\\left(\\dfrac{{V_u}}{{\\phi_v}} - 0.5 V_s\\right)^2 +
    \\left(\\dfrac{{0.45\\,p_h\\,T_u}}{{2 A_o \\phi}}\\right)^2}}$$
  $$\\text{{demanda}} = {t.long_demand_n:.0f}\\;\\text{{N}}
    = {F(t.long_demand_n / 1000.0)}$$
</div>
<table class="data">
{long_rows}
</table>
{long_bars_html}
"""


def _aci_torsion_block(t: BeamShearTorsionResult, L, F, S, M, A, sec: int = 3) -> str:
    """Torsión y combinación V + T según ACI 318-19."""
    fc = t.fc_mpa
    fyt = t.fyt_mpa
    fy_l = t.fy_long_mpa
    sqrt_fc = math.sqrt(fc) if fc > 0 else 0.0
    tth_nmm = t.t_th_knm * 1e6
    tcr_nmm = t.t_cr_knm * 1e6

    header = f"""
<h2>{sec}. Cálculos de diseño (torsión)</h2>

<h3>{sec}.1 Torsión umbral $T_{{th}}$
  <span class="aci-ref">ACI 318-19 §22.7.4.1</span>
</h3>
<p>Por debajo del umbral se permite despreciar los efectos de torsión:</p>
<div class="step">
  <div class="step-title">$T_{{th}} = 0.083\\,\\lambda \\sqrt{{f'_c}}
    \\left(\\dfrac{{A_{{cp}}^2}}{{p_{{cp}}}}\\right)$</div>
  $$T_{{th}} = 0.083 \\cdot {t.lam:.2f} \\cdot \\sqrt{{{fc:.1f}}} \\cdot
    \\dfrac{{{t.acp_mm2:.0f}^2}}{{{t.pcp_mm:.0f}}}
    = {tth_nmm:.0f}\\;\\text{{N·mm}} = {M(t.t_th_knm)}$$
  $$\\phi T_{{th}} = 0.75 \\cdot T_{{th}} = {M(t.phi_t_th_knm)}$$
</div>
<table class="data">
  <tr><td>$T_u$</td><td class="num">{M(t.tu_knm)}</td></tr>
  <tr><td>$\\phi T_{{th}}$</td><td class="num">{M(t.phi_t_th_knm)}</td></tr>
</table>
"""

    if t.torsion_regime != "DISEÑO":
        return header + """
<div class="result-summary ok">
  <h3>Torsión despreciable</h3>
  <p>$T_u \\le \\phi T_{th}$ — la torsión puede despreciarse (ACI 22.7.1.1) y el
  armado transversal queda gobernado exclusivamente por el cortante.</p>
</div>
"""

    tipo_txt = (
        "Compatibilidad (estáticamente indeterminada)"
        if t.torsion_type == "COMPATIBILIDAD" else "Equilibrio (estáticamente determinada)"
    )
    if t.redistributed:
        redistrib_txt = (
            f"Como $T_u > \\phi T_{{cr}}$ y la torsión es por compatibilidad, se "
            f"reduce el torsor de diseño a $\\phi T_{{cr}} = {M(t.phi_t_cr_knm)}$ "
            f"(ACI 22.7.3.2)."
        )
    elif t.torsion_type == "COMPATIBILIDAD":
        redistrib_txt = (
            "La torsión es por compatibilidad pero $T_u \\le \\phi T_{cr}$, "
            "por lo que no procede reducción alguna."
        )
    else:
        redistrib_txt = (
            "La torsión es de equilibrio: no se admite redistribución y se diseña "
            "para el $T_u$ completo (ACI 22.7.3.1)."
        )

    sec_ok = t.section_ok
    at_s_floor = 0.175 * t.b_mm / fyt

    long_bars_html = ""
    if t.long_bars is not None:
        lb = t.long_bars
        long_bars_html = f"""
<p>Distribución sugerida (ACI 9.7.5.1: separación perimetral ≤ 300 mm,
$d_b \\ge \\max(0.042\\,s,\\,\\#3)$, al menos una barra en cada esquina):</p>
<table class="data">
  <tr><td>Número de barras</td><td class="num">{lb.n_bars}</td></tr>
  <tr><td>Diámetro</td><td class="num">#{lb.bar_number} ({lb.bar_diameter_mm:.2f} mm)</td></tr>
  <tr><td>Separación perimetral</td><td class="num">{lb.spacing_mm:.0f} mm</td></tr>
  <tr><td><b>Área provista</b></td><td class="num"><b>{A(lb.area_total_mm2)}</b></td></tr>
</table>
"""

    return header + f"""
<h3>{sec}.2 Tipo de torsión y torsor de diseño
  <span class="aci-ref">ACI 318-19 §22.7.3 / §22.7.5.1</span>
</h3>
<p>Tipo declarado: <b>{tipo_txt}</b>.</p>
<div class="step">
  <div class="step-title">Torsión de agrietamiento</div>
  $$T_{{cr}} = 0.33\\,\\lambda \\sqrt{{f'_c}}
    \\left(\\dfrac{{A_{{cp}}^2}}{{p_{{cp}}}}\\right)
    = {tcr_nmm:.0f}\\;\\text{{N·mm}} = {M(t.t_cr_knm)}$$
  $$\\phi T_{{cr}} = {M(t.phi_t_cr_knm)}$$
</div>
<p>{redistrib_txt}</p>
<table class="data">
  <tr><td><b>$T_u$ de diseño</b></td>
      <td class="num"><b>{M(t.tu_design_knm)}</b></td></tr>
</table>

<h3>{sec}.3 Límite de dimensiones de la sección
  <span class="aci-ref">ACI 318-19 §22.7.7.1</span>
</h3>
<p>Se limita el esfuerzo combinado de cortante y torsión para controlar el
aplastamiento del concreto:</p>
<div class="step">
  $$\\sqrt{{\\left(\\dfrac{{V_u}}{{b_w d}}\\right)^2 +
    \\left(\\dfrac{{T_u p_h}}{{1.7 A_{{oh}}^2}}\\right)^2}}
    \\le \\phi\\left(\\dfrac{{V_c}}{{b_w d}} + 0.66\\sqrt{{f'_c}}\\right)$$
  $$\\sqrt{{\\left({(t.vu_kn * 1000.0 / (t.b_mm * t.d_mm)):.3f}\\right)^2 +
    \\left({(t.tu_design_knm * 1e6 * t.ph_mm / (1.7 * t.aoh_mm2 ** 2)):.3f}\\right)^2}}
    = {t.stress_demand_mpa:.3f}\\;\\text{{MPa}}
    \\quad\\le\\quad {t.stress_limit_mpa:.3f}\\;\\text{{MPa}}$$
</div>
<table class="data">
  <tr><td>Esfuerzo combinado (demanda)</td>
      <td class="num">{t.stress_demand_mpa:.3f} MPa</td></tr>
  <tr><td>Límite $\\phi(V_c/(b_w d) + 0.66\\sqrt{{f'_c}})$</td>
      <td class="num">{t.stress_limit_mpa:.3f} MPa</td></tr>
  <tr><td><b>Verificación</b></td>
      <td class="num"><span class="chip {'ok' if sec_ok else 'fail'}">
      {'CUMPLE' if sec_ok else 'NO CUMPLE — AUMENTAR SECCIÓN'}</span></td></tr>
</table>

<h3>{sec}.4 Refuerzo transversal por torsión
  <span class="aci-ref">ACI 318-19 §22.7.6.1a</span>
</h3>
<div class="step">
  <div class="step-title">$T_n = \\dfrac{{2 A_o A_t f_{{yt}}}}{{s}}\\cot\\theta$
    &nbsp;→&nbsp; $\\dfrac{{A_t}}{{s}} = \\dfrac{{T_u/\\phi}}{{2 A_o f_{{yt}} \\cot\\theta}}$</div>
  $$\\dfrac{{A_t}}{{s}} =
    \\dfrac{{{t.tu_design_knm * 1e6 / 0.75:.0f}}}
           {{2 \\cdot {t.ao_mm2:.0f} \\cdot {fyt:.1f} \\cdot \\cot {t.theta_deg:.0f}°}}
    = {t.at_s_required:.4f}\\;\\text{{mm}}^2/\\text{{mm}}$$
</div>
<p>$A_t$ corresponde a <b>una rama</b> del estribo cerrado más exterior.</p>

<h3>{sec}.5 Refuerzo transversal combinado $V + T$
  <span class="aci-ref">ACI 318-19 §9.6.4.2 / §9.7.6.3.3</span>
</h3>
<div class="step">
  <div class="step-title">Demanda combinada</div>
  $$\\dfrac{{A_v + 2A_t}}{{s}} = {t.av_s_required:.4f} + 2({t.at_s_required:.4f})
    = {t.avt_s_required:.4f}\\;\\text{{mm}}^2/\\text{{mm}}$$
  $$\\left(\\dfrac{{A_v + 2A_t}}{{s}}\\right)_{{min}} =
    \\max\\!\\left(\\dfrac{{0.062\\sqrt{{f'_c}}}}{{f_{{yt}}}},\\;
    \\dfrac{{0.35}}{{f_{{yt}}}}\\right) b_w
    = {t.avt_s_min:.4f}\\;\\text{{mm}}^2/\\text{{mm}}$$
</div>
<p>Sólo las dos ramas exteriores del estribo cerrado son efectivas en torsión,
mientras que todas las ramas trabajan en cortante. La separación por resistencia
se obtiene entonces exigiendo, por rama exterior:</p>
<div class="step">
  $$\\dfrac{{A_b}}{{s}} \\ge \\dfrac{{A_t}}{{s}} + \\dfrac{{A_v/s}}{{n_{{ramas}}}}
    = {t.at_s_required:.4f} + \\dfrac{{{t.av_s_required:.4f}}}{{{t.stirrup_legs}}}
    \\;\\Rightarrow\\; s \\le {L(t.s_combined_required_mm, 1)}$$
</div>
<table class="data">
  <tr><td>$s$ por resistencia combinada $V+T$</td>
      <td class="num">{L(t.s_combined_required_mm, 1)}</td></tr>
  <tr><td>$s$ por refuerzo mínimo <span class="aci-ref">§9.6.4.2</span></td>
      <td class="num">{L(t.s_min_required_mm, 1) if t.s_min_required_mm > 0 else '—'}</td></tr>
  <tr><td>$s_{{max}}$ por cortante <span class="aci-ref">§9.7.6.2.2</span></td>
      <td class="num">{L(t.s_shear_only_max_mm, 1)}</td></tr>
  <tr><td>$s_{{max}}$ por torsión $=\\min(p_h/8,\\,300)$
      <span class="aci-ref">§9.7.6.3.3</span></td>
      <td class="num">{L(t.s_torsion_max_mm, 1)}</td></tr>
  <tr><td><b>$s$ ADOPTADO</b></td>
      <td class="num"><b>{L(t.s_adopted_mm, 1)}</b></td></tr>
  <tr><td>$(A_v + 2A_t)/s$ provisto</td>
      <td class="num">{t.avt_s_provided:.4f} mm²/mm</td></tr>
</table>

<h3>{sec}.6 Refuerzo longitudinal por torsión
  <span class="aci-ref">ACI 318-19 §22.7.6.1b / §9.6.4.3</span>
</h3>
<div class="step">
  <div class="step-title">$A_l = \\dfrac{{A_t}}{{s}} p_h
    \\left(\\dfrac{{f_{{yt}}}}{{f_y}}\\right)\\cot^2\\theta$</div>
  $$A_l = {t.at_s_required:.4f} \\cdot {t.ph_mm:.0f} \\cdot
    \\dfrac{{{fyt:.1f}}}{{{fy_l:.1f}}} \\cdot \\cot^2 {t.theta_deg:.0f}°
    = {t.al_required_mm2:.1f}\\;\\text{{mm}}^2 = {A(t.al_required_mm2)}$$
</div>
<div class="step">
  <div class="step-title">Mínimo (ACI 9.6.4.3), con
    $A_t/s \\ge 0.175 b_w / f_{{yt}} = {at_s_floor:.4f}$</div>
  $$A_{{l,min}} = \\dfrac{{0.42\\sqrt{{f'_c}}\\,A_{{cp}}}}{{f_y}}
    - \\left(\\dfrac{{A_t}}{{s}}\\right) p_h \\dfrac{{f_{{yt}}}}{{f_y}}
    = \\dfrac{{0.42 \\cdot {sqrt_fc:.3f} \\cdot {t.acp_mm2:.0f}}}{{{fy_l:.1f}}}
    - \\dots = {t.al_min_mm2:.1f}\\;\\text{{mm}}^2 = {A(t.al_min_mm2)}$$
</div>
<table class="data">
  <tr><td>$A_l$ por resistencia</td><td class="num">{A(t.al_required_mm2)}</td></tr>
  <tr><td>$A_{{l,min}}$</td><td class="num">{A(t.al_min_mm2)}</td></tr>
  <tr><td><b>$A_l$ ADOPTADO $=\\max$</b></td>
      <td class="num"><b>{A(t.al_adopted_mm2)}</b></td></tr>
</table>
{long_bars_html}
"""


def _aci_shear_steps(result, fmt, sc: int, st: int) -> dict:
    """Bloques de cálculo de cortante propios de ACI 318-19."""
    L, F, S, M, A = fmt["L"], fmt["F"], fmt["S"], fmt["M"], fmt["A"]
    fc, fyt, b, d, lam = result.fc_mpa, result.fyt_mpa, result.b_mm, result.d_mm, result.lam
    vu_n = result.vu_kn * 1000.0
    vc_n = result.vc_kn * 1000.0
    phi_vc_n = result.phi_vc_kn * 1000.0
    vs_req_n = result.vs_required_kn * 1000.0
    vs_lim_n = result.vs_max_kn * 1000.0
    sqrt_fc = math.sqrt(fc) if fc > 0 else 0.0

    if result.regime == "DISEÑO":
        vs_block = f"""
<h3>{sc}.4 Cortante requerido del refuerzo $V_s$
  {_ref(DesignCode.ACI_318_19, "§22.5.1.1")}
</h3>
<div class="step">
  <div class="step-title">$V_s$ requerido</div>
  $$V_s = \\dfrac{{V_u - \\phi V_c}}{{\\phi}} =
    \\dfrac{{{vu_n:.0f} - {phi_vc_n:.0f}}}{{0.75}} =
    {vs_req_n:.0f}\\;\\text{{N}} = {F(result.vs_required_kn)}$$
</div>
<p>Verificación del límite máximo (ACI 22.5.1.2):
$V_s \\le 0.66\\sqrt{{f'_c}}\\,b_w d = {vs_lim_n:.0f}\\;\\text{{N}} = {F(result.vs_max_kn)}$
&nbsp;<span class="chip {'ok' if vs_req_n <= vs_lim_n else 'fail'}">
{'CUMPLE' if vs_req_n <= vs_lim_n else 'EXCEDE'}</span></p>

<h3>{sc}.5 Separación por resistencia</h3>
<div class="step">
  <div class="step-title">$s$ requerido</div>
  $$\\left(\\dfrac{{A_v}}{{s}}\\right)_{{req}} = \\dfrac{{V_s}}{{f_{{yt}}\\,d}}
    = \\dfrac{{{vs_req_n:.0f}}}{{{fyt:.1f} \\cdot {d:.2f}}}
    = {(vs_req_n / (fyt * d)) if fyt > 0 and d > 0 else 0.0:.4f}\\;\\text{{mm}}^2/\\text{{mm}}$$
  $$s_{{req}} = \\dfrac{{A_v}}{{(A_v/s)_{{req}}}} = {L(result.s_required_mm, 1)}$$
</div>
"""
    elif result.regime == "MINIMO":
        vs_block = f"""
<h3>{sc}.4 Régimen</h3>
<p>$0.5 \\phi V_c < V_u \\le \\phi V_c$ — no se requiere Vs por resistencia; se
adopta el armado mínimo por cortante.</p>
"""
    elif result.regime == "TORSION":
        vs_block = f"""
<h3>{sc}.4 Régimen</h3>
<p>$V_u \\le 0.5 \\phi V_c$ — el cortante por sí solo no exigiría estribos, pero
la torsión sí los requiere. La separación adoptada proviene de la combinación
$V + T$ de la sección {st}.</p>
"""
    else:
        vs_block = f"""
<h3>{sc}.4 Régimen</h3>
<p>$V_u \\le 0.5 \\phi V_c$ — la viga no requiere refuerzo por cortante. Aun así
es recomendable disponer estribos mínimos por consideraciones constructivas.</p>
"""

    return {
        "geometry_rows": "",
        "vc_block": f"""
<h3>{sc}.1 Resistencia del concreto $V_c$
  {_ref(DesignCode.ACI_318_19, "§22.5.5.1 (simplificada)")}
</h3>
<div class="step">
  <div class="step-title">$V_c = 0.17 \\lambda \\sqrt{{f'_c}}\\, b_w d$</div>
  $$V_c = 0.17 \\cdot {lam:.2f} \\cdot \\sqrt{{{fc:.1f}}} \\cdot {b:.1f} \\cdot {d:.2f}
    = {vc_n:.0f}\\;\\text{{N}} = {F(result.vc_kn)}$$
</div>
""",
        "phi_block": f"""
<h3>{sc}.2 Capacidad reducida del concreto
  {_ref(DesignCode.ACI_318_19, "§21.2.1, $\\phi = 0.75$")}
</h3>
<div class="step">
  $$\\phi V_c = 0.75 \\cdot V_c = {phi_vc_n:.0f}\\;\\text{{N}} = {F(result.phi_vc_kn)}$$
</div>
""",
        "vs_block": vs_block,
        "min_max_block": f"""
<h3>{sc}.6 Armado mínimo y separación máxima</h3>
<p>Refuerzo mínimo por cortante {_ref(DesignCode.ACI_318_19, "§9.6.3.4")}:</p>
<div class="step">
  $$\\left(\\dfrac{{A_v}}{{s}}\\right)_{{min}} =
     \\max\\!\\left(\\dfrac{{0.062 \\sqrt{{f'_c}}}}{{f_{{yt}}}},\\;
     \\dfrac{{0.35}}{{f_{{yt}}}}\\right)\\, b_w
     = \\max\\!\\left(\\dfrac{{0.062 \\cdot {sqrt_fc:.3f}}}{{{fyt:.1f}}},\\;
     \\dfrac{{0.35}}{{{fyt:.1f}}}\\right) \\cdot {b:.1f}$$
</div>
<p>Separación máxima {_ref(DesignCode.ACI_318_19, "§9.7.6.2.2")}:</p>
<div class="step">
  $$s_{{max}} = \\begin{{cases}}
       \\min(d/2,\\;600\\,\\text{{mm}}) & \\text{{si }} V_s \\le 0.33\\sqrt{{f'_c}}\\,b_w d \\\\
       \\min(d/4,\\;300\\,\\text{{mm}}) & \\text{{en caso contrario}}
     \\end{{cases}}$$
  $$s_{{max}} = {L(result.s_max_mm, 1)}$$
</div>
""",
        "s_min_ref": _ref(DesignCode.ACI_318_19, "§9.6.3.4"),
        "s_max_ref": _ref(DesignCode.ACI_318_19, "§9.7.6.2.2"),
        "phi_vn_tex": "$\\phi V_n = \\phi(V_c + V_s)$ con $s$ adoptado",
        "extra_result_rows": "",
    }


def _aashto_shear_steps(result, fmt, sc: int, st: int) -> dict:
    """Bloques de cálculo de cortante propios de AASHTO LRFD 2020."""
    L, F, S, M, A = fmt["L"], fmt["F"], fmt["S"], fmt["M"], fmt["A"]
    fc, fyt, b, lam = result.fc_mpa, result.fyt_mpa, result.b_mm, result.lam
    dv = result.dv_mm
    vu_n = result.vu_kn * 1000.0
    vc_n = result.vc_kn * 1000.0
    phi_vc_n = result.phi_vc_kn * 1000.0
    vs_req_n = result.vs_required_kn * 1000.0
    sqrt_fc = math.sqrt(fc) if fc > 0 else 0.0
    corte = 0.125 * fc

    if result.regime == "DISEÑO":
        vs_block = f"""
<h3>{sc}.4 Cortante requerido del refuerzo $V_s$
  {_ref(DesignCode.AASHTO_LRFD_2020, "§5.7.3.3")}
</h3>
<div class="step">
  <div class="step-title">$V_s$ requerido</div>
  $$V_s = \\dfrac{{V_u}}{{\\phi}} - V_c =
    \\dfrac{{{vu_n:.0f}}}{{0.90}} - {vc_n:.0f} =
    {vs_req_n:.0f}\\;\\text{{N}} = {F(result.vs_required_kn)}$$
</div>
<p>El tope no está sobre $V_s$ sino sobre la resistencia total
{_ref(DesignCode.AASHTO_LRFD_2020, "§5.7.3.3-2")}:
$V_n \\le 0.25 f'_c b_v d_v = {F(result.vn_max_kn)}$, es decir
$\\phi V_{{n,max}} = {F(result.phi_vn_max_kn)}$
&nbsp;<span class="chip {'ok' if result.vu_kn <= result.phi_vn_max_kn else 'fail'}">
{'CUMPLE' if result.vu_kn <= result.phi_vn_max_kn else 'EXCEDE'}</span></p>

<h3>{sc}.5 Separación por resistencia</h3>
<div class="step">
  <div class="step-title">$s$ requerido</div>
  <p>Con estribos verticales y $\\theta = 45^\\circ$ ($\\cot\\theta = 1$):</p>
  $$\\left(\\dfrac{{A_v}}{{s}}\\right)_{{req}} = \\dfrac{{V_s}}{{f_y\\,d_v \\cot\\theta}}
    = \\dfrac{{{vs_req_n:.0f}}}{{{fyt:.1f} \\cdot {dv:.2f}}}
    = {(vs_req_n / (fyt * dv)) if fyt > 0 and dv > 0 else 0.0:.4f}\\;\\text{{mm}}^2/\\text{{mm}}$$
  $$s_{{req}} = \\dfrac{{A_v}}{{(A_v/s)_{{req}}}} = {L(result.s_required_mm, 1)}$$
</div>
"""
    elif result.regime == "MINIMO":
        vs_block = f"""
<h3>{sc}.4 Régimen</h3>
<p>$0.5 \\phi V_c < V_u \\le \\phi V_c$ — se exige refuerzo transversal
{_ref(DesignCode.AASHTO_LRFD_2020, "§5.7.2.3")} pero no por resistencia: se
adopta el mínimo de §5.7.2.5.</p>
"""
    elif result.regime == "TORSION":
        vs_block = f"""
<h3>{sc}.4 Régimen</h3>
<p>$V_u \\le 0.5 \\phi V_c$ — el cortante por sí solo no exigiría estribos, pero
la torsión sí los requiere. La separación adoptada proviene de la combinación
$V + T$ de la sección {st}.</p>
"""
    else:
        vs_block = f"""
<h3>{sc}.4 Régimen</h3>
<p>$V_u \\le 0.5\\,\\phi V_c$ — no se exige refuerzo transversal
{_ref(DesignCode.AASHTO_LRFD_2020, "§5.7.2.3")}. Aun así es recomendable
disponer estribos mínimos por consideraciones constructivas.</p>
"""

    # Revisión del refuerzo longitudinal (§5.7.3.5)
    if result.long_check_applies:
        chip = "ok" if result.long_reinf_ok else "fail"
        texto = "CUMPLE" if result.long_reinf_ok else "NO CUMPLE"
        extra_rows = f"""
<tr><td>Tracción exigida al acero longitudinal
    {_ref(DesignCode.AASHTO_LRFD_2020, "§5.7.3.5")}</td>
    <td class="num">{F(result.long_demand_n / 1000.0)}</td></tr>
<tr><td>Aporte del acero de flexión $A_s f_y$</td>
    <td class="num">{F(result.long_capacity_n / 1000.0)}
      <span class="chip {chip}">{texto}</span></td></tr>
"""
    else:
        extra_rows = f"""
<tr><td colspan="2"><i>No se revisó el refuerzo longitudinal de
    {_ref(DesignCode.AASHTO_LRFD_2020, "§5.7.3.5")}: requiere $M_u$ y el acero
    de flexión de esta misma sección.</i></td></tr>
"""

    return {
        "geometry_rows": f"""
  <tr><td>Peralte efectivo de flexión</td><td>$d_e$</td>
      <td class="num">{L(result.de_mm, 2)}</td></tr>
  <tr><td>Peralte efectivo de cortante
      {_ref(DesignCode.AASHTO_LRFD_2020, "§5.7.2.8")}</td><td>$d_v$</td>
      <td class="num">{L(dv, 2)} <i>(manda {_dv_tex(result.dv_governing)})</i></td></tr>
""",
        "vc_block": f"""
<h3>{sc}.1 Peralte efectivo de cortante y resistencia del concreto
  {_ref(DesignCode.AASHTO_LRFD_2020, "§5.7.2.8 / §5.7.3.3")}
</h3>
<p>AASHTO no usa $d$ sino el peralte efectivo de cortante $d_v$, que tiene dos
pisos para que no se degrade en secciones muy armadas:</p>
<div class="step">
  <div class="step-title">Peralte efectivo de cortante</div>
  $$d_v = \\max\\left(d_e - \\dfrac{{a}}{{2}},\\; 0.9\\,d_e,\\; 0.72\\,h\\right)
    = {dv:.2f}\\;\\text{{mm}} = {L(dv, 2)}$$
  <p>Gobierna el término {_dv_tex(result.dv_governing)}.</p>
</div>
<div class="step">
  <div class="step-title">Resistencia del concreto, procedimiento simplificado
    {_ref(DesignCode.AASHTO_LRFD_2020, "§5.7.3.4.1")}</div>
  <p>Con $\\beta = 2.0$ y $\\theta = 45^\\circ$:</p>
  $$V_c = 0.083 \\, \\beta \\, \\lambda \\sqrt{{f'_c}} \\, b_v d_v =
    0.083 \\cdot 2.0 \\cdot {lam:.2f} \\cdot \\sqrt{{{fc:.1f}}} \\cdot {b:.1f} \\cdot {dv:.2f}
    = {vc_n:.0f}\\;\\text{{N}} = {F(result.vc_kn)}$$
</div>
""",
        "phi_block": f"""
<h3>{sc}.2 Capacidad reducida del concreto
  {_ref(DesignCode.AASHTO_LRFD_2020, "§5.5.4.2, $\\phi = 0.90$")}
</h3>
<p>AASHTO calibra sus factores de carga y de resistencia en conjunto, por lo que
$\\phi = 0.90$ para cortante no es comparable directamente con el 0.75 de ACI.</p>
<div class="step">
  $$\\phi V_c = 0.90 \\cdot V_c = {phi_vc_n:.0f}\\;\\text{{N}} = {F(result.phi_vc_kn)}$$
</div>
""",
        "vs_block": vs_block,
        "min_max_block": f"""
<h3>{sc}.6 Armado mínimo y separación máxima</h3>
<p>Refuerzo transversal mínimo {_ref(DesignCode.AASHTO_LRFD_2020, "§5.7.2.5")}:</p>
<div class="step">
  $$\\left(\\dfrac{{A_v}}{{s}}\\right)_{{min}} =
     \\dfrac{{0.083 \\sqrt{{f'_c}} \\, b_v}}{{f_y}}
     = \\dfrac{{0.083 \\cdot {sqrt_fc:.3f} \\cdot {b:.1f}}}{{{fyt:.1f}}}
     = {result.av_s_min_value:.4f}\\;\\text{{mm}}^2/\\text{{mm}}$$
</div>
<p>Separación máxima {_ref(DesignCode.AASHTO_LRFD_2020, "§5.7.2.6")}, según el
esfuerzo cortante de la sección:</p>
<div class="step">
  $$v_u = \\dfrac{{V_u}}{{\\phi\\, b_v d_v}} =
    \\dfrac{{{vu_n:.0f}}}{{0.90 \\cdot {b:.1f} \\cdot {dv:.2f}}} =
    {(vu_n / (0.9 * b * dv)) if b > 0 and dv > 0 else 0.0:.3f}\\;\\text{{MPa}}
    \\qquad 0.125 f'_c = {corte:.3f}\\;\\text{{MPa}}$$
  $$s_{{max}} = \\begin{{cases}}
       \\min(0.8\\,d_v,\\;600\\,\\text{{mm}}) & \\text{{si }} v_u < 0.125 f'_c \\\\
       \\min(0.4\\,d_v,\\;300\\,\\text{{mm}}) & \\text{{en caso contrario}}
     \\end{{cases}}$$
  $$s_{{max}} = {L(result.s_max_mm, 1)}$$
</div>
""",
        "s_min_ref": _ref(DesignCode.AASHTO_LRFD_2020, "§5.7.2.5"),
        "s_max_ref": _ref(DesignCode.AASHTO_LRFD_2020, "§5.7.2.6"),
        "phi_vn_tex": (
            "$\\phi V_n = \\phi\\,\\min(V_c + V_s,\\; 0.25 f'_c b_v d_v)$ "
            "con $s$ adoptado"
        ),
        "extra_result_rows": extra_rows,
    }


def _shear_steps(result, fmt, sc: int, st: int, code: DesignCode) -> dict:
    if code is DesignCode.AASHTO_LRFD_2020:
        return _aashto_shear_steps(result, fmt, sc, st)
    return _aci_shear_steps(result, fmt, sc, st)


def _beam_shear_fragments(
    result: BeamShearResult,
    unit_system: UnitSystem,
    si: int = 1,
    sc: int = 4,
    st: int = 5,
    code: DesignCode = DesignCode.ACI_318_19,
) -> dict:
    """Fragmentos de la parte de cortante (y torsión) de la memoria de viga.

    Acepta tanto un :class:`~core.shear.BeamShearResult` como el resultado
    combinado :class:`~core.torsion.BeamShearTorsionResult`; los fragmentos de
    torsión salen vacíos cuando ésta no se incluyó en el diseño. ``si``, ``sc``
    y ``st`` son los números de sección de datos de entrada, cortante y torsión.
    """
    cv = get_converter(unit_system)

    L = lambda mm, d=1: cv.format_length_small(mm, d)
    F = lambda kn, d=2: f"{kn / cv.force_to_kn:.{d}f} {cv.force_unit}"
    S = lambda mpa, d=1: f"{mpa / cv.stress_to_mpa:.{d}f} {cv.stress_unit}"
    M = lambda knm, d=2: f"{knm / cv.moment_to_knm:.{d}f} {cv.moment_unit}"
    A = lambda mm2, d=2: cv.format_area(mm2 / 100.0, d)

    torsion = (
        result
        if isinstance(result, BeamShearTorsionResult)
        and result.torsion_active and result.tu_knm > 0
        else None
    )
    tor_design = torsion is not None and torsion.torsion_regime == "DISEÑO"

    fc = result.fc_mpa
    fyt = result.fyt_mpa
    b = result.b_mm
    h = result.h_mm
    d = result.d_mm
    lam = result.lam
    av = result.av_mm2
    vu_n = result.vu_kn * 1000.0
    vc_n = result.vc_kn * 1000.0
    phi_vc_n = result.phi_vc_kn * 1000.0
    vs_req_n = result.vs_required_kn * 1000.0
    vs_lim_n = result.vs_max_kn * 1000.0

    # Los bloques que cambian con la norma los arma el motor de pasos.
    steps = _shear_steps(
        result, {"L": L, "F": F, "S": S, "M": M, "A": A}, sc, st, code
    )

    status_class = {
        "OK": "ok",
        "NO REQUIERE ESTRIBOS": "ok",
        "AUMENTAR SECCIÓN": "fail",
        "ERROR": "fail",
    }.get(result.status, "warn")

    regime_label = {
        "NO REQUIERE": "No requiere estribos",
        "MINIMO": "Estribos por mínimo (Av,min)",
        "DISEÑO": "Estribos por diseño",
        "TORSION": "Sin exigencia por cortante; estribos exigidos por torsión",
    }.get(result.regime, result.regime)

    cap_ratio = (result.phi_vn_kn / result.vu_kn) if result.vu_kn > 0 else float("inf")
    cap_class = "ok" if (cap_ratio == float("inf") or cap_ratio >= 1.0) else "fail"
    cap_text = "CUMPLE" if (cap_ratio == float("inf") or cap_ratio >= 1.0) else "NO CUMPLE"
    cap_ratio_str = "∞" if cap_ratio == float("inf") else f"{cap_ratio:.3f}"

    # Tabla resumen del adoptado
    if result.regime != "NO REQUIERE":
        adopted_row = f"""
<tr><td>$s$ requerido por resistencia</td>
    <td class="num">{L(result.s_required_mm, 1) if result.s_required_mm > 0 else '—'}</td></tr>
<tr><td>$s$ por $A_{{v,min}}$ {steps["s_min_ref"]}</td>
    <td class="num">{L(result.s_min_required_mm, 1) if result.s_min_required_mm > 0 else '—'}</td></tr>
<tr><td>$s_{{max}}$ {steps["s_max_ref"]}</td>
    <td class="num">{L(result.s_max_mm, 1)}</td></tr>
<tr><td><b>$s$ ADOPTADO</b></td>
    <td class="num"><b>{L(result.s_adopted_mm, 1)}</b></td></tr>
"""
    else:
        adopted_row = ""

    # ----- Bloques específicos de torsión -----
    tu_row = ""
    fy_long_row = ""
    section_props_block = ""
    torsion_block = ""
    torsion_result_rows = ""
    torsion_summary_rows = ""

    if torsion is not None:
        t = torsion
        tipo_txt = (
            "Compatibilidad (redistribuible)"
            if t.torsion_type == "COMPATIBILIDAD" else "Equilibrio (no redistribuible)"
        )
        tu_row = (
            f'<tr><td>Torsor último</td><td>$T_u$</td>'
            f'<td class="num">{M(t.tu_knm)}</td></tr>\n'
        )
        if code is DesignCode.ACI_318_19:
            tu_row += (
                f'<tr><td>Tipo de torsión {_ref(code, "§22.7.3")}</td>'
                f'<td>—</td><td class="num">{tipo_txt}</td></tr>'
            )
        else:
            # AASHTO no admite la redistribución por compatibilidad de ACI,
            # así que el tipo declarado no altera el torsor de diseño.
            tu_row += (
                f'<tr><td>Torsor de diseño</td><td>$T_u$</td>'
                f'<td class="num">{M(t.tu_design_knm)}</td></tr>'
            )
        fy_long_row = (
            f'<tr><td>Fluencia del acero longitudinal</td><td>$f_y$</td>'
            f'<td class="num">{S(t.fy_long_mpa)}</td></tr>'
        )
        section_props_block = f"""
<h3>{si}.6 Propiedades de la sección para torsión</h3>
<table class="data">
  <tr><td>Área encerrada por el perímetro exterior</td><td>$A_{{cp}} = b\\,h$</td>
      <td class="num">{t.acp_mm2:,.0f} mm²</td></tr>
  <tr><td>Perímetro exterior</td><td>$p_{{cp}} = 2(b+h)$</td>
      <td class="num">{t.pcp_mm:,.0f} mm</td></tr>
  <tr><td>Área encerrada por el eje del estribo</td><td>$A_{{oh}}$</td>
      <td class="num">{t.aoh_mm2:,.0f} mm²</td></tr>
  <tr><td>Perímetro del eje del estribo</td><td>$p_h$</td>
      <td class="num">{t.ph_mm:,.0f} mm</td></tr>
  <tr><td>Área bruta del flujo cortante</td><td>$A_o = 0.85\\,A_{{oh}}$</td>
      <td class="num">{t.ao_mm2:,.0f} mm²</td></tr>
  <tr><td>Ángulo de las bielas</td><td>$\\theta$</td>
      <td class="num">{t.theta_deg:.0f}°</td></tr>
</table>
"""
        torsion_block = _torsion_report_block(t, L, F, S, M, A, sec=st, code=code)

        if tor_design:
            tor_ok = t.torsion_ratio >= 1.0
            torsion_result_rows = f"""
<tr><td>$\\phi T_n = \\phi\\,\\dfrac{{2 A_o A_t f_{{yt}} \\cot\\theta}}{{s}}$ con $s$ adoptado</td>
    <td class="num">{M(t.phi_tn_knm)}</td></tr>
<tr><td>Relación $\\phi T_n / T_u$</td>
    <td class="num">{t.torsion_ratio:.3f}
      <span class="chip {'ok' if tor_ok else 'fail'}">
      {'CUMPLE' if tor_ok else 'NO CUMPLE'}</span></td></tr>
<tr><td><b>$A_l$ ADOPTADO</b> {_ref(code, "§22.7.6.1b / §9.6.4.3"
        if code is DesignCode.ACI_318_19 else "§5.7.3.6.3")}</td>
    <td class="num"><b>{A(t.al_adopted_mm2)}</b></td></tr>
"""
            if t.long_bars is not None:
                torsion_result_rows += (
                    f'<tr><td>Distribución sugerida de $A_l$</td>'
                    f'<td class="num"><b>{t.long_bars.label}</b> = '
                    f'{A(t.long_bars.area_total_mm2)} '
                    f'(s ≈ {t.long_bars.spacing_mm:.0f} mm)</td></tr>\n'
                )
            torsion_summary_rows = f"""
    <tr><td>$T_u$</td><td class="num">{M(t.tu_knm)}</td>
        <td>$\\phi T_n$</td><td class="num"><b>{M(t.phi_tn_knm)}</b></td></tr>
    <tr><td>$A_l$</td>
        <td class="num"><b>{A(t.al_adopted_mm2)}</b></td>
        <td>$\\phi T_n / T_u$</td><td class="num"><b>{t.torsion_ratio:.2f}</b></td></tr>
"""
        else:
            umbral_tex, umbral_ref = (
                ("\\phi T_{th}", "ACI 318-19 §22.7.4.1")
                if code is DesignCode.ACI_318_19
                else ("0.25\\,\\phi T_{cr}", "AASHTO LRFD §5.7.2.1")
            )
            torsion_summary_rows = f"""
    <tr><td>$T_u$</td><td class="num">{M(t.tu_knm)}</td>
        <td>${umbral_tex}$</td><td class="num">{M(t.phi_t_th_knm)}</td></tr>
    <tr><td colspan="4">Torsión despreciable: $T_u \\le {umbral_tex}$
        ({umbral_ref}) — no requiere refuerzo por torsión.</td></tr>
"""

    loads_rows = f"""
  <tr><td>Cortante último</td><td>$V_u$</td><td class="num">{F(result.vu_kn)}</td></tr>
  {tu_row}"""

    materials_rows = f"""
  <tr><td>Fluencia del estribo</td><td>$f_{{yt}}$</td><td class="num">{S(fyt)}</td></tr>
  {fy_long_row}
  <tr><td>Factor por concreto</td><td>$\\lambda$</td><td class="num">{lam:.2f}</td></tr>"""

    stirrup_block = f"""
<h3>{si}.5 Estribo propuesto</h3>
<table class="data">
  <tr><td>Diámetro del estribo</td><td>$d_e$</td><td class="num">{_bar_label(result.stirrup_diameter_mm)} ({result.stirrup_diameter_mm:.2f} mm)</td></tr>
  <tr><td>Número de ramas</td><td>$n$</td><td class="num">{result.stirrup_legs}</td></tr>
  <tr><td>Área total de ramas</td><td>$A_v = n \\cdot A_b$</td><td class="num">{av:.1f} mm²</td></tr>
{steps["geometry_rows"]}
</table>
{section_props_block}"""

    calc = f"""
<h2>{sc}. Cálculos de diseño (cortante)</h2>
{steps["vc_block"]}
{steps["phi_block"]}
<h3>{sc}.3 Verificación del régimen</h3>
<p>Se compara $V_u$ con $\\phi V_c$ y $0.5\\,\\phi V_c$:</p>
<table class="data">
  <tr><td>$0.5\\,\\phi V_c$</td><td class="num">{F(result.phi_vc_kn * 0.5)}</td></tr>
  <tr><td>$\\phi V_c$</td><td class="num">{F(result.phi_vc_kn)}</td></tr>
  <tr><td>$V_u$</td><td class="num">{F(result.vu_kn)}</td></tr>
  <tr><td><b>Régimen detectado</b></td><td><b>{regime_label}</b></td></tr>
</table>

{steps["vs_block"]}
{steps["min_max_block"]}
{torsion_block}
<h3>{sc if torsion is None else st}.7 Resultado del refuerzo transversal</h3>
<table class="data">
{adopted_row}
<tr><td>{steps["phi_vn_tex"]}</td>
    <td class="num">{F(result.phi_vn_kn)}</td></tr>
<tr><td>Relación $\\phi V_n / V_u$</td>
    <td class="num">{cap_ratio_str}
      <span class="chip {cap_class}">{cap_text}</span></td></tr>
{steps["extra_result_rows"]}
{torsion_result_rows}
</table>
"""

    summary_rows = f"""
    <tr><td>Estribo</td><td><b>{_bar_label(result.stirrup_diameter_mm)} ({result.stirrup_legs} ramas)</b></td>
        <td>$\\phi V_c$</td><td class="num">{F(result.phi_vc_kn)}</td></tr>
    <tr><td>$s$ adoptado</td>
        <td><b>{L(result.s_adopted_mm, 1) if result.s_adopted_mm > 0 else '—'}</b></td>
        <td>$\\phi V_n$</td><td class="num"><b>{F(result.phi_vn_kn)}</b></td></tr>
{torsion_summary_rows}"""

    return {
        "loads": loads_rows,
        "materials": materials_rows,
        "stirrup": stirrup_block,
        "calc": calc,
        "summary_rows": summary_rows,
        "warnings": result.warnings,
        "has_torsion": torsion is not None,
        "status_class": status_class,
    }


def _slab_shear_fragments(
    result: SlabShearResult,
    unit_system: UnitSystem,
    sc: int = 4,
    code: DesignCode = DesignCode.ACI_318_19,
) -> dict:
    """Fragmentos de la revisión por cortante de la memoria de losa."""
    cv = get_converter(unit_system)

    L = lambda mm, d=1: cv.format_length_small(mm, d)
    F = lambda kn, d=2: f"{kn / cv.force_to_kn:.{d}f} {cv.force_unit}"
    S = lambda mpa, d=1: f"{mpa / cv.stress_to_mpa:.{d}f} {cv.stress_unit}"

    fc = result.fc_mpa
    b = result.b_mm
    h = result.h_mm
    d = result.d_mm
    lam = result.lam
    vu_n = result.vu_kn * 1000.0
    vc_n = result.vc_kn * 1000.0
    phi_vc_n = result.phi_vc_kn * 1000.0

    status_class = {
        "OK": "ok",
        "AUMENTAR SECCIÓN": "fail",
        "ERROR": "fail",
    }.get(result.status, "warn")

    ratio = result.ratio
    ratio_str = "∞" if ratio == float("inf") else f"{ratio:.3f}"
    cap_class = "ok" if (ratio == float("inf") or ratio >= 1.0) else "fail"
    cap_text = "CUMPLE" if (ratio == float("inf") or ratio >= 1.0) else "NO CUMPLE"

    if code is DesignCode.AASHTO_LRFD_2020:
        vc_block = f"""
<h3>{sc}.1 Peralte efectivo de cortante y resistencia del concreto
  {_ref(code, "§5.7.2.8 / §5.7.3.4.1")}
</h3>
<p>AASHTO evalúa el cortante sobre el peralte efectivo $d_v$, no sobre $d$. Con
el procedimiento simplificado, $\\beta = 2.0$ y $\\theta = 45^\\circ$; a diferencia
de ACI 318-19, la cuantía longitudinal <b>no</b> interviene en $V_c$.</p>
<div class="step">
  <div class="step-title">Peralte efectivo de cortante</div>
  $$d_v = \\max\\left(d_e - \\dfrac{{a}}{{2}},\\; 0.9\\,d_e,\\; 0.72\\,h\\right)
    = {result.dv_mm:.2f}\\;\\text{{mm}} = {L(result.dv_mm, 2)}$$
  <p>Con $d_e = {L(result.de_mm, 2)}$; gobierna el término
  {_dv_tex(result.dv_governing)}.</p>
</div>
<div class="step">
  <div class="step-title">$V_c = 0.083\\,\\beta\\,\\lambda \\sqrt{{f'_c}}\\, b_v d_v$</div>
  $$V_c = 0.083 \\cdot 2.0 \\cdot {lam:.2f} \\cdot \\sqrt{{{fc:.1f}}} \\cdot
    {b:.1f} \\cdot {result.dv_mm:.2f}
    = {vc_n:.0f}\\;\\text{{N}} = {F(result.vc_kn)}$$
</div>
{'' if result.simplified_applicable else f'''
<div class="alert alert-warn">
  <h3>⚠ Fuera del alcance del procedimiento simplificado</h3>
  <p>La losa tiene $h = {h:.0f}$ mm ≥ 400 mm y no lleva refuerzo transversal, de
  modo que no cumple ninguna de las dos condiciones de §5.7.3.4.1. AASHTO exige
  aquí el procedimiento general de §5.7.3.4.2, que esta aplicación no implementa:
  <b>este resultado no es válido como verificación normativa</b>.</p>
</div>'''}

<h3>{sc}.2 Capacidad reducida
  {_ref(code, "§5.5.4.2, $\\phi = 0.90$")}
</h3>
<div class="step">
  $$\\phi V_c = 0.90 \\cdot V_c = {phi_vc_n:.0f}\\;\\text{{N}} = {F(result.phi_vc_kn)}$$
</div>
"""
        summary_first_row = f"""
    <tr><td>$d_v$ usado en $V_c$</td><td class="num">{L(result.dv_mm, 2)}</td>
        <td>$\\phi V_c$</td><td class="num"><b>{F(result.phi_vc_kn)}</b></td></tr>"""
    else:
        rho_note = (
            " La cuantía se tomó del acero de flexión diseñado en esta misma memoria."
            if not result.rho_w_assumed else
            f" No se conoce el acero longitudinal, por lo que se usó el mínimo por "
            f"retracción y temperatura $\\rho_w = {result.rho_w:.4f}$ (ACI 24.4.3.2)."
        )
        vc_block = f"""
<h3>{sc}.1 Resistencia del concreto $V_c$
  {_ref(code, "Tabla 22.5.5.1 ($A_v < A_{v,min}$)")}
</h3>
<p>La losa no lleva refuerzo transversal (ACI 8.6.1), así que $V_c$ se evalúa con
la cuantía longitudinal y el factor de tamaño, no con la forma simplificada
$0.17\\lambda\\sqrt{{f'_c}}$, que sólo aplica a elementos con $A_v \\ge A_{{v,min}}$.
{rho_note}</p>
<div class="step">
  <div class="step-title">Cuantía longitudinal</div>
  $$\\rho_w = \\dfrac{{A_s}}{{b\\,d}} = \\dfrac{{{result.as_long_mm2:.0f}}}{{{b:.1f} \\cdot {d:.2f}}}
    = {result.rho_w:.5f}$$
</div>
<div class="step">
  <div class="step-title">Factor de tamaño
    {_ref(code, "§22.5.5.1.3")}</div>
  $$\\lambda_s = \\sqrt{{\\dfrac{{2}}{{1 + d/250}}}} \\le 1.0
    = \\sqrt{{\\dfrac{{2}}{{1 + {d:.2f}/250}}}} = {result.lambda_s:.3f}$$
</div>
<div class="step">
  <div class="step-title">$V_c = 0.66\\,\\lambda_s\\,\\lambda\\,(\\rho_w)^{{1/3}}
    \\sqrt{{f'_c}}\\, b\\, d$</div>
  $$V_c = 0.66 \\cdot {result.lambda_s:.3f} \\cdot {lam:.2f} \\cdot
    ({result.rho_w:.5f})^{{1/3}} \\cdot \\sqrt{{{fc:.1f}}} \\cdot {b:.1f} \\cdot {d:.2f}
    = {vc_n:.0f}\\;\\text{{N}} = {F(result.vc_kn)}$$
</div>

<h3>{sc}.2 Capacidad reducida
  {_ref(code, "§21.2.1, $\\phi = 0.75$")}
</h3>
<div class="step">
  $$\\phi V_c = 0.75 \\cdot V_c = {phi_vc_n:.0f}\\;\\text{{N}} = {F(result.phi_vc_kn)}$$
</div>
"""
        summary_first_row = f"""
    <tr><td>$\\rho_w$ usado en $V_c$</td><td class="num">{result.rho_w:.5f}</td>
        <td>$\\phi V_c$</td><td class="num"><b>{F(result.phi_vc_kn)}</b></td></tr>"""

    loads_rows = f"""
  <tr><td>Cortante último por franja unitaria</td><td>$V_u$</td>
      <td class="num">{F(result.vu_kn)}</td></tr>"""

    materials_rows = f"""
  <tr><td>Factor por concreto</td><td>$\\lambda$</td><td class="num">{lam:.2f}</td></tr>"""

    calc = f"""
<h2>{sc}. Revisión por cortante</h2>
{vc_block}
<h3>{sc}.3 Verificación</h3>
<p>Para que la losa no requiera refuerzo por cortante debe cumplirse
$\\phi V_c \\ge V_u$:</p>

<table class="data">
  <tr><td>$\\phi V_c$ (capacidad)</td><td class="num">{F(result.phi_vc_kn)}</td></tr>
  <tr><td>$V_u$ (demanda)</td><td class="num">{F(result.vu_kn)}</td></tr>
  <tr><td><b>$\\phi V_c / V_u$</b></td>
      <td class="num"><b>{ratio_str}</b>
        <span class="chip {cap_class}">{cap_text}</span></td></tr>
</table>
"""

    summary_rows = f"""{summary_first_row}
    <tr><td>$V_u$</td><td class="num">{F(result.vu_kn)}</td>
        <td>$\\phi V_c / V_u$</td><td class="num"><b>{ratio_str}</b></td></tr>"""

    return {
        "loads": loads_rows,
        "materials": materials_rows,
        "calc": calc,
        "summary_rows": summary_rows,
        "warnings": result.warnings,
        "status_class": status_class,
    }


# ============================================================
#              Memorias unificadas por elemento
# ============================================================

def _worst_status(*statuses: str) -> str:
    """Estado global: manda el más desfavorable de los análisis."""
    for bad in ("ERROR", "AUMENTAR SECCIÓN", "ARMADO INSUFICIENTE", "REDUCIR SECCIÓN"):
        if bad in statuses:
            return bad
    return "OK"


def _warnings_block(*groups) -> str:
    items = [w for group in groups for w in group]
    if not items:
        return ""
    return (
        '<div class="alert alert-warn"><h3>⚠ Advertencias</h3><ul>'
        + "".join(f"<li>{w}</li>" for w in items)
        + "</ul></div>"
    )


def _doc_head(subtitle: str, info: "ProjectInfo", element_name: str,
              section_type: str, fecha: str,
              code: DesignCode = DesignCode.ACI_318_19) -> str:
    notes = (
        f'<div class="doc-notes"><b>Notas:</b> {escape(info.notes)}</div>'
        if info.notes else ""
    )
    return f"""
<div class="doc-header">
  <h1>Memoria de Cálculo</h1>
  <p class="subtitle">{subtitle}</p>
</div>

<div class="metadata">
  <span class="label">Proyecto:</span><span>{escape(info.project)}</span>
  <span class="label">Fecha:</span><span>{fecha}</span>
  <span class="label">Elemento:</span><span>{escape(element_name)}</span>
  <span class="label">Tipo:</span><span>{section_type}</span>
  <span class="label">Diseñador:</span><span>{escape(info.designer) or "—"}</span>
  <span class="label">Revisor:</span><span>{escape(info.reviewer) or "—"}</span>
  <span class="label">Revisión:</span><span>{escape(info.revision) or "—"}</span>
  <span class="label">Norma:</span><span>{spec(code).label}</span>
</div>
{notes}
"""


def _doc_footer(fecha: str, code: DesignCode = DesignCode.ACI_318_19) -> str:
    return f"""
<div class="doc-footer">
  <p>Memoria generada por <b>{APP_NAME} v{__version__}</b> —
  Diseño conforme a {spec(code).full_name} — {fecha}</p>
</div>
"""


def generate_beam_report(
    flexion: FlexionDesignResult,
    shear: BeamShearResult,
    unit_system: UnitSystem,
    info: Optional[ProjectInfo] = None,
) -> str:
    """Memoria única de viga: flexión, cortante y —si aplica— torsión."""
    info = info or ProjectInfo()
    element_name = info.beam_name
    cv = get_converter(unit_system)
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
    L = lambda mm, d=1: cv.format_length_small(mm, d)
    A = lambda cm2, d=2: cv.format_area(cm2, d)
    M = lambda knm, d=2: f"{knm / cv.moment_to_knm:.{d}f} {cv.moment_unit}"
    F = lambda kn, d=2: f"{kn / cv.force_to_kn:.{d}f} {cv.force_unit}"

    # La norma la dicta el resultado, no el llamador: así una memoria no puede
    # rotularse con una norma distinta de la que produjo los números.
    code = code_of(flexion)
    norma = spec(code).label

    sh = _beam_shear_fragments(shear, unit_system, si=1, sc=4, st=5, code=code)
    fx = _flexion_fragments(
        flexion, unit_system, section_type="Viga",
        extra_load_rows=sh["loads"],
        extra_material_rows=sh["materials"],
        extra_input_blocks=sh["stirrup"],
        code=code,
    )

    sec_summary = 6 if sh["has_torsion"] else 5
    subtitle = (
        f"Diseño por flexión, cortante y torsión en viga según {norma}"
        if sh["has_torsion"] else
        f"Diseño por flexión y cortante en viga según {norma}"
    )
    status = _worst_status(flexion.status, shear.status)
    status_class = (
        "ok" if status == "OK"
        else "warn" if status == "REDUCIR SECCIÓN" else "fail"
    )

    body = (
        _doc_head(subtitle, info, element_name, "Viga rectangular", fecha, code)
        + fx["inputs"]
        + fx["calc"]
        + sh["calc"]
        + _warnings_block(flexion.warnings, sh["warnings"])
        + f"""
<h2>{sec_summary}. Resumen del diseño</h2>
<div class="result-summary {status_class}">
  <h3>Estado: {status}</h3>
  <table class="data" style="margin-top: 8px;">
    <tr><td>Sección</td><td>${L(flexion.b_mm, 1)} \\times {L(flexion.h_mm, 1)}$</td>
        <td>$d$ efectivo</td><td class="num">{L(flexion.d_mm, 2)}</td></tr>
    <tr><td>Refuerzo a flexión</td><td><b>{fx["layers_summary"]}</b></td>
        <td>$A_s$ total</td><td class="num"><b>{A(flexion.as_provided_cm2)}</b></td></tr>
    <tr><td>$M_u$</td><td class="num">{M(flexion.mu_demand_knm)}</td>
        <td>$\\phi M_n$</td><td class="num"><b>{M(flexion.phi_mn_knm)}</b></td></tr>
    <tr><td>Estado a flexión</td><td>{flexion.status}</td>
        <td>$\\phi M_n / M_u$</td><td class="num"><b>{fx["ratio"]:.3f}</b></td></tr>
    <tr><td>$V_u$</td><td class="num">{F(shear.vu_kn)}</td>
        <td>Estado a cortante</td><td>{shear.status}</td></tr>
{sh["summary_rows"]}
  </table>
</div>
"""
        + _doc_footer(fecha, code)
    )

    kind = "Flexión, Cortante y Torsión" if sh["has_torsion"] else "Flexión y Cortante"
    return _document(
        body, f"Memoria — {element_name}", element_name, kind=kind
    )


def generate_slab_report(
    flexion: FlexionDesignResult,
    shear: SlabShearResult,
    unit_system: UnitSystem,
    info: Optional[ProjectInfo] = None,
) -> str:
    """Memoria única de losa: flexión y cortante sobre la franja unitaria."""
    info = info or ProjectInfo()
    element_name = info.slab_name
    cv = get_converter(unit_system)
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
    L = lambda mm, d=1: cv.format_length_small(mm, d)
    A = lambda cm2, d=2: cv.format_area(cm2, d)
    M = lambda knm, d=2: f"{knm / cv.moment_to_knm:.{d}f} {cv.moment_unit}"

    code = code_of(flexion)
    norma = spec(code).label

    sh = _slab_shear_fragments(shear, unit_system, sc=4, code=code)
    fx = _flexion_fragments(
        flexion, unit_system, section_type="Losa (franja unitaria)",
        extra_load_rows=sh["loads"],
        extra_material_rows=sh["materials"],
        code=code,
    )

    status = _worst_status(flexion.status, shear.status)
    status_class = (
        "ok" if status == "OK"
        else "warn" if status == "REDUCIR SECCIÓN" else "fail"
    )

    body = (
        _doc_head(f"Diseño por flexión y revisión por cortante en losa según {norma}",
                  info, element_name, "Losa (franja unitaria 1 m)", fecha, code)
        + fx["inputs"]
        + fx["calc"]
        + sh["calc"]
        + _warnings_block(flexion.warnings, sh["warnings"])
        + f"""
<h2>5. Resumen del diseño</h2>
<div class="result-summary {status_class}">
  <h3>Estado: {status}</h3>
  <table class="data" style="margin-top: 8px;">
    <tr><td>Franja</td><td>${L(flexion.b_mm, 1)} \\times {L(flexion.h_mm, 1)}$</td>
        <td>$d$ efectivo</td><td class="num">{L(flexion.d_mm, 2)}</td></tr>
    <tr><td>Refuerzo a flexión</td><td><b>{fx["layers_summary"]}</b></td>
        <td>$A_s$ total</td><td class="num"><b>{A(flexion.as_provided_cm2)}</b></td></tr>
    <tr><td>$M_u$</td><td class="num">{M(flexion.mu_demand_knm)}</td>
        <td>$\\phi M_n$</td><td class="num"><b>{M(flexion.phi_mn_knm)}</b></td></tr>
    <tr><td>Estado a flexión</td><td>{flexion.status}</td>
        <td>$\\phi M_n / M_u$</td><td class="num"><b>{fx["ratio"]:.3f}</b></td></tr>
    <tr><td>Estado a cortante</td><td>{shear.status}</td>
        <td>{"$d_v$" if code is DesignCode.AASHTO_LRFD_2020 else "$d$"} usado en $V_c$</td>
        <td class="num">{L(shear.d_mm, 2)}</td></tr>
{sh["summary_rows"]}
  </table>
</div>
"""
        + _doc_footer(fecha, code)
    )

    return _document(
        body, f"Memoria — {element_name}", element_name,
        kind="Flexión y Cortante"
    )

"""Generador de memoria de cálculo HTML + LaTeX (MathJax).

Hay una memoria por elemento, no por análisis:

- :func:`generate_beam_report`  → viga: flexión, cortante y torsión.
- :func:`generate_slab_report`  → losa: flexión y cortante.

Cada documento es autocontenido (datos de entrada unificados, cálculos paso a
paso con referencias al ACI 318-19, advertencias y un resumen global) y está
estilizado para imprimir en A4. Los ``_*_fragments`` arman cada parte y reciben
el número de sección que les toca dentro del documento final.
"""
import math
from datetime import datetime
from html import escape
from typing import Optional

from core.flexion import FlexionDesignResult
from core.project import ProjectInfo
from core.version import APP_NAME, __version__
from core.bar_tables import REBAR_SIZES
from core.units import UnitSystem, get_converter
from core.shear import BeamShearResult, SlabShearResult
from core.torsion import BeamShearTorsionResult


def _bar_label(db_mm: float) -> str:
    """Devuelve '#N' para un diámetro dado (mejor coincidencia)."""
    for r in REBAR_SIZES:
        if abs(r.diameter_mm - db_mm) < 0.1:
            return f"#{r.number}"
    return f"db={db_mm:.1f}mm"


def _fmt_layer(layer, cv) -> str:
    return f"{layer.n_bars} × {_bar_label(layer.bar_diameter_mm)}"


def _flexion_fragments(
    result: FlexionDesignResult,
    unit_system: UnitSystem,
    section_type: str = "Viga",
    extra_load_rows: str = "",
    extra_material_rows: str = "",
    extra_input_blocks: str = "",
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
    mu_nmm = result.mu_demand_knm * 1e6
    phi = 0.9
    rn = result.rn
    m_val = fy / (0.85 * fc) if fc > 0 else 0
    rho_req = result.rho_required
    as_req = result.as_required_cm2
    as_min = result.as_min_cm2
    as_max = result.as_max_cm2
    as_prov = result.as_provided_cm2
    rho_prov = result.rho_provided
    rho_max = (0.85 * beta_1 * fc / fy) * (0.003 / 0.007) if fy > 0 else 0
    as_prov_mm2 = as_prov * 100.0
    c_force = result.compression_kn
    t_force = result.tension_kn
    phi_mn = result.phi_mn_knm

    # Term1 y term2 del As_min
    term1 = (0.25 * math.sqrt(fc) / fy * b * d / 100) if fy > 0 else 0
    term2 = (1.4 / fy * b * d / 100) if fy > 0 else 0

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

<h3>2.1 Factor de reducción $\\beta_1$
  <span class="aci-ref">ACI 318-19 §22.2.2.4.3</span>
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

<h3>2.2 Peralte efectivo</h3>
<p>{d_expl}</p>
<div class="step">
  <div class="step-title">Cálculo de $d$</div>
  $${d_eq}$$
</div>

<h3>2.3 Cuantía requerida
  <span class="aci-ref">ACI 318-19 §22.2</span>
</h3>
<p>A partir del equilibrio de la sección y aplicando $\\phi = 0.9$ para flexión
controlada por tracción:</p>

<div class="step">
  <div class="step-title">Resistencia nominal requerida</div>
  $$R_n = \\dfrac{{M_u}}{{\\phi \\cdot b \\cdot d^2}} =
    \\dfrac{{{mu_nmm:.0f}}}{{0.9 \\cdot {b:.1f} \\cdot {d:.2f}^2}} =
    {rn:.4f}\\;\\text{{MPa}}$$
</div>

<div class="step">
  <div class="step-title">Constante $m$</div>
  $$m = \\dfrac{{f_y}}{{0.85 \\cdot f'_c}} =
    \\dfrac{{{fy:.1f}}}{{0.85 \\cdot {fc:.1f}}} = {m_val:.3f}$$
</div>

<div class="step">
  <div class="step-title">Cuantía requerida</div>
  $$\\rho_{{req}} = \\dfrac{{1}}{{m}} \\left( 1 - \\sqrt{{1 - \\dfrac{{2\\,m\\,R_n}}{{f_y}}}} \\right) = {rho_req:.5f}$$
</div>

<div class="step">
  <div class="step-title">Área de acero requerida</div>
  $$A_{{s,req}} = \\rho_{{req}} \\cdot b \\cdot d =
    {rho_req:.5f} \\cdot {b:.1f} \\cdot {d:.2f} = {as_req*100:.1f}\\;\\text{{mm}}^2 = {A(as_req)}$$
</div>

<h3>2.4 Acero mínimo
  <span class="aci-ref">ACI 318-19 §9.6.1.2</span>
</h3>
<div class="step">
  <div class="step-title">Cálculo de $A_{{s,min}}$</div>
  $$A_{{s,min}} = \\max\\left( \\dfrac{{0.25\\sqrt{{f'_c}}}}{{f_y}},\\; \\dfrac{{1.4}}{{f_y}} \\right) \\cdot b \\cdot d$$
  $$\\dfrac{{0.25\\sqrt{{{fc:.1f}}}}}{{{fy:.1f}}} \\cdot b \\cdot d = {term1*100:.1f}\\;\\text{{mm}}^2$$
  $$\\dfrac{{1.4}}{{{fy:.1f}}} \\cdot b \\cdot d = {term2*100:.1f}\\;\\text{{mm}}^2$$
  $$A_{{s,min}} = {A(as_min)}$$
</div>

<h3>2.5 Acero máximo
  <span class="aci-ref">ACI 318-19 §21.2 — Condición de tracción controlada</span>
</h3>
<p>Para que la falla sea dúctil ($\\varepsilon_t \\ge 0.004$):</p>
<div class="step">
  <div class="step-title">Cálculo de $\\rho_{{max}}$ y $A_{{s,max}}$</div>
  $$\\rho_{{max}} = \\dfrac{{0.85 \\beta_1 f'_c}}{{f_y}} \\cdot \\dfrac{{0.003}}{{0.003 + 0.004}} = {rho_max:.5f}$$
  $$A_{{s,max}} = \\rho_{{max}} \\cdot b \\cdot d = {A(as_max)}$$
</div>

<h3>2.6 Bloque equivalente de esfuerzos (Whitney)
  <span class="aci-ref">ACI 318-19 §22.2.2.4</span>
</h3>
<p>Con el acero proporcionado $A_{{s}} = {A(as_prov)}$:</p>
<div class="step">
  <div class="step-title">Profundidad del bloque equivalente $a$</div>
  $$a = \\dfrac{{A_s f_y}}{{0.85 f'_c b}} =
    \\dfrac{{{as_prov_mm2:.1f} \\cdot {fy:.1f}}}{{0.85 \\cdot {fc:.1f} \\cdot {b:.1f}}} =
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
  $$C = 0.85 \\cdot f'_c \\cdot b \\cdot a =
    0.85 \\cdot {fc:.1f} \\cdot {b:.1f} \\cdot {a:.2f} =
    {c_force*1000:.0f}\\;\\text{{N}} = {c_force:.2f}\\;\\text{{kN}}$$
</div>
<div class="step">
  <div class="step-title">Resultante de tensión $T$</div>
  $$T = A_s \\cdot f_y = {as_prov_mm2:.1f} \\cdot {fy:.1f} =
    {t_force*1000:.0f}\\;\\text{{N}} = {t_force:.2f}\\;\\text{{kN}}$$
</div>
<p>Verificación de equilibrio: $C \\approx T$ &nbsp;<span class="chip {'ok' if abs(c_force - t_force) < 0.5 else 'fail'}">{'CUMPLE' if abs(c_force - t_force) < 0.5 else 'NO CUMPLE'}</span></p>

<h3>2.8 Momento resistente nominal y reducido</h3>
<div class="step">
  <div class="step-title">Capacidad de la sección</div>
  $$M_n = A_s f_y \\left( d - \\dfrac{{a}}{{2}} \\right) =
    {as_prov_mm2:.1f} \\cdot {fy:.1f} \\cdot {result.jd_mm:.2f} =
    {phi_mn/phi*1e6:.0f}\\;\\text{{N·mm}}$$
  $$\\phi M_n = 0.9 \\cdot M_n = {phi_mn:.2f}\\;\\text{{kN·m}} = {M(phi_mn)}$$
</div>

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
  <tr>
    <td>Acero máximo</td>
    <td>$A_{{s,max}}$</td>
    <td class="num">{A(as_max)}</td>
  </tr>
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
  <span class="aci-ref">ACI 318-19 §25.2.1 / §25.2.2</span>
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


def _torsion_report_block(t: BeamShearTorsionResult, L, F, S, M, A, sec: int = 3) -> str:
    """Sección de la memoria: cálculos de torsión y combinación V + T."""
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


def _beam_shear_fragments(
    result: BeamShearResult,
    unit_system: UnitSystem,
    si: int = 1,
    sc: int = 4,
    st: int = 5,
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

    sqrt_fc = math.sqrt(fc) if fc > 0 else 0.0

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

    # Bloque de cálculo de Vs / s
    if result.regime == "DISEÑO":
        vs_block = f"""
<h3>{sc}.4 Cortante requerido del refuerzo $V_s$
  <span class="aci-ref">ACI 318-19 §22.5.1.1</span>
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
    = {(vs_req_n / (fyt * d)):.4f}\\;\\text{{mm}}^2/\\text{{mm}}$$
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

    # Tabla resumen del adoptado
    if result.regime != "NO REQUIERE":
        adopted_row = f"""
<tr><td>$s$ requerido por resistencia</td>
    <td class="num">{L(result.s_required_mm, 1) if result.s_required_mm > 0 else '—'}</td></tr>
<tr><td>$s$ por $A_{{v,min}}$ <span class="aci-ref">ACI 9.6.3.4</span></td>
    <td class="num">{L(result.s_min_required_mm, 1) if result.s_min_required_mm > 0 else '—'}</td></tr>
<tr><td>$s_{{max}}$ <span class="aci-ref">ACI 9.7.6.2.2</span></td>
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
            f'<tr><td>Tipo de torsión <span class="aci-ref">ACI 22.7.3</span></td>'
            f'<td>—</td><td class="num">{tipo_txt}</td></tr>'
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
        torsion_block = _torsion_report_block(t, L, F, S, M, A, sec=st)

        if tor_design:
            tor_ok = t.torsion_ratio >= 1.0
            torsion_result_rows = f"""
<tr><td>$\\phi T_n = \\phi\\,\\dfrac{{2 A_o A_t f_{{yt}} \\cot\\theta}}{{s}}$ con $s$ adoptado</td>
    <td class="num">{M(t.phi_tn_knm)}</td></tr>
<tr><td>Relación $\\phi T_n / T_u$</td>
    <td class="num">{t.torsion_ratio:.3f}
      <span class="chip {'ok' if tor_ok else 'fail'}">
      {'CUMPLE' if tor_ok else 'NO CUMPLE'}</span></td></tr>
<tr><td><b>$A_l$ ADOPTADO</b> <span class="aci-ref">ACI 22.7.6.1b / 9.6.4.3</span></td>
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
            torsion_summary_rows = f"""
    <tr><td>$T_u$</td><td class="num">{M(t.tu_knm)}</td>
        <td>$\\phi T_{{th}}$</td><td class="num">{M(t.phi_t_th_knm)}</td></tr>
    <tr><td colspan="4">Torsión despreciable: $T_u \\le \\phi T_{{th}}$
        (ACI 22.7.4.1) — no requiere refuerzo por torsión.</td></tr>
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
</table>
{section_props_block}"""

    calc = f"""
<h2>{sc}. Cálculos de diseño (cortante)</h2>

<h3>{sc}.1 Resistencia del concreto $V_c$
  <span class="aci-ref">ACI 318-19 §22.5.5.1 (simplificada)</span>
</h3>
<div class="step">
  <div class="step-title">$V_c = 0.17 \\lambda \\sqrt{{f'_c}}\\, b_w d$</div>
  $$V_c = 0.17 \\cdot {lam:.2f} \\cdot \\sqrt{{{fc:.1f}}} \\cdot {b:.1f} \\cdot {d:.2f}
    = {vc_n:.0f}\\;\\text{{N}} = {F(result.vc_kn)}$$
</div>

<h3>{sc}.2 Capacidad reducida del concreto
  <span class="aci-ref">ACI 318-19 §21.2.1, $\\phi = 0.75$</span>
</h3>
<div class="step">
  $$\\phi V_c = 0.75 \\cdot V_c = {phi_vc_n:.0f}\\;\\text{{N}} = {F(result.phi_vc_kn)}$$
</div>

<h3>{sc}.3 Verificación del régimen</h3>
<p>Se compara $V_u$ con $\\phi V_c$ y $0.5\\,\\phi V_c$:</p>
<table class="data">
  <tr><td>$0.5\\,\\phi V_c$</td><td class="num">{F(result.phi_vc_kn * 0.5)}</td></tr>
  <tr><td>$\\phi V_c$</td><td class="num">{F(result.phi_vc_kn)}</td></tr>
  <tr><td>$V_u$</td><td class="num">{F(result.vu_kn)}</td></tr>
  <tr><td><b>Régimen detectado</b></td><td><b>{regime_label}</b></td></tr>
</table>

{vs_block}

<h3>{sc}.6 Armado mínimo y separación máxima</h3>
<p>Refuerzo mínimo por cortante <span class="aci-ref">ACI 318-19 §9.6.3.4</span>:</p>
<div class="step">
  $$\\left(\\dfrac{{A_v}}{{s}}\\right)_{{min}} =
     \\max\\!\\left(\\dfrac{{0.062 \\sqrt{{f'_c}}}}{{f_{{yt}}}},\\;
     \\dfrac{{0.35}}{{f_{{yt}}}}\\right)\\, b_w
     = \\max\\!\\left(\\dfrac{{0.062 \\cdot {sqrt_fc:.3f}}}{{{fyt:.1f}}},\\;
     \\dfrac{{0.35}}{{{fyt:.1f}}}\\right) \\cdot {b:.1f}$$
</div>
<p>Separación máxima <span class="aci-ref">ACI 318-19 §9.7.6.2.2</span>:</p>
<div class="step">
  $$s_{{max}} = \\begin{{cases}}
       \\min(d/2,\\;600\\,\\text{{mm}}) & \\text{{si }} V_s \\le 0.33\\sqrt{{f'_c}}\\,b_w d \\\\
       \\min(d/4,\\;300\\,\\text{{mm}}) & \\text{{en caso contrario}}
     \\end{{cases}}$$
  $$s_{{max}} = {L(result.s_max_mm, 1)}$$
</div>
{torsion_block}
<h3>{sc if torsion is None else st}.7 Resultado del refuerzo transversal</h3>
<table class="data">
{adopted_row}
<tr><td>$\\phi V_n = \\phi(V_c + V_s)$ con $s$ adoptado</td>
    <td class="num">{F(result.phi_vn_kn)}</td></tr>
<tr><td>Relación $\\phi V_n / V_u$</td>
    <td class="num">{cap_ratio_str}
      <span class="chip {cap_class}">{cap_text}</span></td></tr>
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

    rho_note = (
        " La cuantía se tomó del acero de flexión diseñado en esta misma memoria."
        if not result.rho_w_assumed else
        f" No se conoce el acero longitudinal, por lo que se usó el mínimo por "
        f"retracción y temperatura $\\rho_w = {result.rho_w:.4f}$ (ACI 24.4.3.2)."
    )

    loads_rows = f"""
  <tr><td>Cortante último por franja unitaria</td><td>$V_u$</td>
      <td class="num">{F(result.vu_kn)}</td></tr>"""

    materials_rows = f"""
  <tr><td>Factor por concreto</td><td>$\\lambda$</td><td class="num">{lam:.2f}</td></tr>"""

    calc = f"""
<h2>{sc}. Revisión por cortante</h2>

<h3>{sc}.1 Resistencia del concreto $V_c$
  <span class="aci-ref">ACI 318-19 Tabla 22.5.5.1 ($A_v < A_{{v,min}}$)</span>
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
    <span class="aci-ref">ACI 318-19 §22.5.5.1.3</span></div>
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
  <span class="aci-ref">ACI 318-19 §21.2.1, $\\phi = 0.75$</span>
</h3>
<div class="step">
  $$\\phi V_c = 0.75 \\cdot V_c = {phi_vc_n:.0f}\\;\\text{{N}} = {F(result.phi_vc_kn)}$$
</div>

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

    summary_rows = f"""
    <tr><td>$\\rho_w$ usado en $V_c$</td><td class="num">{result.rho_w:.5f}</td>
        <td>$\\phi V_c$</td><td class="num"><b>{F(result.phi_vc_kn)}</b></td></tr>
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
              section_type: str, fecha: str) -> str:
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
  <span class="label">Norma:</span><span>ACI 318-19</span>
</div>
{notes}
"""


def _doc_footer(fecha: str) -> str:
    return f"""
<div class="doc-footer">
  <p>Memoria generada por <b>{APP_NAME} v{__version__}</b> —
  Diseño conforme a ACI 318-19 — {fecha}</p>
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

    sh = _beam_shear_fragments(shear, unit_system, si=1, sc=4, st=5)
    fx = _flexion_fragments(
        flexion, unit_system, section_type="Viga",
        extra_load_rows=sh["loads"],
        extra_material_rows=sh["materials"],
        extra_input_blocks=sh["stirrup"],
    )

    sec_summary = 6 if sh["has_torsion"] else 5
    subtitle = (
        "Diseño por flexión, cortante y torsión en viga según ACI 318-19"
        if sh["has_torsion"] else
        "Diseño por flexión y cortante en viga según ACI 318-19"
    )
    status = _worst_status(flexion.status, shear.status)
    status_class = (
        "ok" if status == "OK"
        else "warn" if status == "REDUCIR SECCIÓN" else "fail"
    )

    body = (
        _doc_head(subtitle, info, element_name, "Viga rectangular", fecha)
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
        + _doc_footer(fecha)
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

    sh = _slab_shear_fragments(shear, unit_system, sc=4)
    fx = _flexion_fragments(
        flexion, unit_system, section_type="Losa (franja unitaria)",
        extra_load_rows=sh["loads"],
        extra_material_rows=sh["materials"],
    )

    status = _worst_status(flexion.status, shear.status)
    status_class = (
        "ok" if status == "OK"
        else "warn" if status == "REDUCIR SECCIÓN" else "fail"
    )

    body = (
        _doc_head("Diseño por flexión y revisión por cortante en losa según ACI 318-19",
                  info, element_name, "Losa (franja unitaria 1 m)", fecha)
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
        <td>$d$ usado en $V_c$</td><td class="num">{L(shear.d_mm, 2)}</td></tr>
{sh["summary_rows"]}
  </table>
</div>
"""
        + _doc_footer(fecha)
    )

    return _document(
        body, f"Memoria — {element_name}", element_name,
        kind="Flexión y Cortante"
    )

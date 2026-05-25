"""Generador de memoria de cálculo HTML + LaTeX (MathJax).

Produce un documento autocontenido con:
- Encabezado y metadatos
- Datos de entrada (geometría, materiales, refuerzo)
- Cálculos paso a paso con fórmulas LaTeX
- Referencias al ACI 318-19
- Verificaciones de armado y separación
- Estilos optimizados para imprimir (fondo blanco, márgenes A4)
"""
import math
from datetime import datetime
from typing import Optional

from core.flexion import FlexionDesignResult, BeamSection, ReinforcementConfig
from core.bar_tables import REBAR_SIZES
from core.units import UnitSystem, get_converter


def _bar_label(db_mm: float) -> str:
    """Devuelve '#N' para un diámetro dado (mejor coincidencia)."""
    for r in REBAR_SIZES:
        if abs(r.diameter_mm - db_mm) < 0.1:
            return f"#{r.number}"
    return f"db={db_mm:.1f}mm"


def _fmt_layer(layer, cv) -> str:
    return f"{layer.n_bars} × {_bar_label(layer.bar_diameter_mm)}"


def generate_html_report(
    result: FlexionDesignResult,
    inputs_user: dict,
    unit_system: UnitSystem,
    section_type: str = "Viga",
    project_name: str = "Proyecto sin título",
    element_name: str = "Elemento sin nombre",
    designer: str = "",
) -> str:
    """Genera el HTML completo de la memoria de cálculo.

    inputs_user: dict con valores en la unidad del usuario (mu, b, h, cover, fc, fy)
    """
    cv = get_converter(unit_system)
    reinf = result.reinforcement
    is_slab = section_type.lower().startswith("losa")

    # Helpers de formato
    L = lambda mm, d=1: cv.format_length_small(mm, d)        # cm/in
    Lbig = lambda mm, d=2: cv.format_length(mm, d)            # m/ft (no usado mucho)
    A = lambda cm2, d=2: cv.format_area(cm2, d)
    M = lambda knm, d=2: f"{knm / cv.moment_to_knm:.{d}f} {cv.moment_unit}"
    F = lambda kn, d=2: f"{kn:.{d}f} kN"
    S = lambda mpa, d=1: f"{mpa / cv.stress_to_mpa:.{d}f} {cv.stress_unit}"

    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
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

    # Solo mostrar sección de estribo si es viga
    stirrup_section = ""
    if not is_slab and reinf:
        stirrup_section = f"""
                <tr>
                    <td>Diámetro del estribo</td>
                    <td>{_bar_label(reinf.stirrup_diameter_mm)}</td>
                    <td>{reinf.stirrup_diameter_mm:.2f} mm</td>
                </tr>"""

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Memoria de Cálculo — {element_name}</title>
<script>
window.MathJax = {{
  tex: {{
    inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
    displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
    processEscapes: true,
    tags: 'ams'
  }},
  svg: {{ fontCache: 'global' }}
}};
</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
<style>
@page {{
  size: A4;
  margin: 2cm 2cm 2.5cm 2.5cm;
}}

* {{
  box-sizing: border-box;
}}

body {{
  font-family: 'Cambria', 'Georgia', 'Times New Roman', serif;
  font-size: 11pt;
  line-height: 1.5;
  color: #000;
  background: #fff;
  margin: 0;
  padding: 0;
}}

.page {{
  max-width: 21cm;
  margin: 0 auto;
  padding: 2.5cm 2cm;
  background: #fff;
}}

/* Header */
.doc-header {{
  text-align: center;
  border-bottom: 3px double #000;
  padding-bottom: 12px;
  margin-bottom: 24px;
}}

.doc-header h1 {{
  font-size: 18pt;
  margin: 0 0 4px 0;
  text-transform: uppercase;
  letter-spacing: 1px;
}}

.doc-header .subtitle {{
  font-size: 11pt;
  font-style: italic;
  color: #444;
  margin: 0;
}}

.metadata {{
  display: grid;
  grid-template-columns: max-content 1fr max-content 1fr;
  gap: 4px 12px;
  font-size: 10pt;
  margin-bottom: 24px;
  padding: 8px 12px;
  border: 1px solid #999;
  background: #f5f5f5;
}}

.metadata .label {{
  font-weight: bold;
}}

/* Headings */
h2 {{
  font-size: 14pt;
  margin: 24px 0 10px 0;
  padding-bottom: 4px;
  border-bottom: 2px solid #333;
  page-break-after: avoid;
}}

h3 {{
  font-size: 12pt;
  margin: 16px 0 6px 0;
  color: #222;
  page-break-after: avoid;
}}

h4 {{
  font-size: 11pt;
  font-style: italic;
  margin: 10px 0 4px 0;
  color: #333;
  page-break-after: avoid;
}}

p {{
  margin: 6px 0;
  text-align: justify;
}}

/* Reference badges */
.aci-ref {{
  display: inline-block;
  font-size: 9pt;
  font-style: italic;
  color: #555;
  background: #eef;
  padding: 1px 6px;
  border-left: 3px solid #336;
  margin-left: 6px;
}}

/* Step containers */
.step {{
  margin: 12px 0;
  padding: 8px 12px;
  border-left: 3px solid #ccc;
  background: #fafafa;
  page-break-inside: avoid;
}}

.step .step-title {{
  font-weight: bold;
  color: #333;
  margin-bottom: 4px;
}}

/* Tables */
table.data {{
  width: 100%;
  border-collapse: collapse;
  margin: 10px 0;
  font-size: 10.5pt;
}}

table.data th, table.data td {{
  border: 1px solid #888;
  padding: 5px 8px;
  text-align: left;
}}

table.data th {{
  background: #ddd;
  font-weight: bold;
}}

table.data td.num {{
  text-align: right;
  font-family: 'Cambria Math', 'Consolas', monospace;
}}

table.data tr:nth-child(even) td {{
  background: #f7f7f7;
}}

/* Result summary */
.result-summary {{
  margin: 20px 0;
  padding: 14px;
  border: 2px solid;
  page-break-inside: avoid;
}}

.result-summary.ok {{
  border-color: #0a6;
  background: #f0fff4;
}}

.result-summary.fail {{
  border-color: #c00;
  background: #fff0f0;
}}

.result-summary.warn {{
  border-color: #c70;
  background: #fffaf0;
}}

.result-summary h3 {{
  margin: 0 0 8px 0;
  font-size: 13pt;
}}

.result-summary.ok h3::before {{ content: "✓ "; }}
.result-summary.fail h3::before {{ content: "✗ "; }}
.result-summary.warn h3::before {{ content: "⚠ "; }}

/* Alerts */
.alert {{
  margin: 16px 0;
  padding: 10px 14px;
  border-left: 4px solid;
}}

.alert-warn {{
  background: #fff8e1;
  border-color: #c70;
}}

.alert-warn h3 {{
  margin-top: 0;
  color: #850;
}}

/* Status chips inside table */
.chip {{
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 9pt;
  font-weight: bold;
}}
.chip.ok    {{ background: #d4edda; color: #155724; border: 1px solid #28a745; }}
.chip.fail  {{ background: #f8d7da; color: #721c24; border: 1px solid #dc3545; }}

/* Footer */
.doc-footer {{
  margin-top: 40px;
  padding-top: 8px;
  border-top: 1px solid #888;
  font-size: 9pt;
  color: #555;
  text-align: center;
}}

/* Print: hide controls, fit nicely */
.print-bar {{
  position: sticky;
  top: 0;
  background: #2c3e50;
  color: #fff;
  padding: 8px 16px;
  display: flex;
  gap: 12px;
  align-items: center;
  z-index: 100;
  box-shadow: 0 2px 6px rgba(0,0,0,0.2);
}}

.print-bar button {{
  background: #3498db;
  color: #fff;
  border: none;
  padding: 6px 14px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 10pt;
}}

.print-bar button:hover {{
  background: #5dade2;
}}

@media print {{
  .print-bar {{ display: none; }}
  body {{ background: #fff; }}
  .page {{ box-shadow: none; padding: 0; }}
  .step {{ background: transparent; }}
}}

@media screen {{
  body {{ background: #e8e8e8; padding: 0; }}
  .page {{
    box-shadow: 0 4px 16px rgba(0,0,0,0.15);
    margin-top: 20px;
    margin-bottom: 20px;
  }}
}}
</style>
</head>
<body>

<div class="print-bar">
  <strong>📄 Memoria de Cálculo</strong>
  <button onclick="window.print()">🖨 Imprimir / Guardar PDF</button>
  <span style="margin-left:auto; font-size:10pt;">{element_name}</span>
</div>

<div class="page">

<div class="doc-header">
  <h1>Memoria de Cálculo</h1>
  <p class="subtitle">Diseño por flexión según ACI 318-19</p>
</div>

<div class="metadata">
  <span class="label">Proyecto:</span><span>{project_name}</span>
  <span class="label">Fecha:</span><span>{fecha}</span>
  <span class="label">Elemento:</span><span>{element_name}</span>
  <span class="label">Tipo:</span><span>{section_type}</span>
  <span class="label">Diseñador:</span><span>{designer or "—"}</span>
  <span class="label">Norma:</span><span>ACI 318-19</span>
</div>

<!-- ============ 1. DATOS DE ENTRADA ============ -->
<h2>1. Datos de entrada</h2>

<h3>1.1 Solicitación</h3>
<table class="data">
  <tr>
    <td>Momento último de diseño</td>
    <td>$M_u$</td>
    <td class="num">{M(result.mu_demand_knm)}</td>
  </tr>
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

{('<table class="data"><tr><td>Diámetro del estribo</td><td>' +
  _bar_label(reinf.stirrup_diameter_mm) +
  f'</td><td class="num">{reinf.stirrup_diameter_mm:.2f} mm</td></tr></table>')
  if (not is_slab and reinf) else ''}

<!-- ============ 2. CÁLCULOS ============ -->
<h2>2. Cálculos de diseño</h2>

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
<p>Verificación de equilibrio: $C \\approx T$ ⇒ <b>{abs(c_force - t_force) < 0.5}</b></p>

<h3>2.8 Momento resistente nominal y reducido</h3>
<div class="step">
  <div class="step-title">Capacidad de la sección</div>
  $$M_n = A_s f_y \\left( d - \\dfrac{{a}}{{2}} \\right) =
    {as_prov_mm2:.1f} \\cdot {fy:.1f} \\cdot {result.jd_mm:.2f} =
    {phi_mn/phi*1e6:.0f}\\;\\text{{N·mm}}$$
  $$\\phi M_n = 0.9 \\cdot M_n = {phi_mn:.2f}\\;\\text{{kN·m}} = {M(phi_mn)}$$
</div>

<!-- ============ 3. VERIFICACIONES ============ -->
<h2>3. Verificaciones</h2>

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

{warnings_html}

<!-- ============ 4. RESUMEN ============ -->
<h2>4. Resumen del diseño</h2>

<div class="result-summary {status_class}">
  <h3>Estado: {result.status}</h3>
  <table class="data" style="margin-top: 8px;">
    <tr>
      <td>Tipo</td><td><b>{section_type}</b></td>
      <td>$d$ efectivo</td><td class="num">{L(d, 2)}</td>
    </tr>
    <tr>
      <td>Sección</td><td>${L(b, 1)} \\times {L(h, 1)}$</td>
      <td>$\\phi M_n$</td><td class="num"><b>{M(phi_mn)}</b></td>
    </tr>
    <tr>
      <td>Refuerzo</td><td><b>{layers_summary}</b></td>
      <td>$M_u$</td><td class="num">{M(result.mu_demand_knm)}</td>
    </tr>
    <tr>
      <td>$A_s$ total</td><td><b>{A(as_prov)}</b></td>
      <td>$\\phi M_n / M_u$</td>
      <td class="num"><b>{ratio:.3f}</b></td>
    </tr>
  </table>
</div>

<div class="doc-footer">
  <p>Memoria de cálculo generada por <b>Calculadora de Acero por Flexión</b> —
  Diseño conforme a ACI 318-19 — {fecha}</p>
</div>

</div>

</body>
</html>
"""

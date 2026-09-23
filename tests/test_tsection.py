"""Secciones con ala (T y L), contra cálculo a mano.

Como en `test_aashto.py`, cada valor esperado está calculado aparte y anotado
en la prueba, de modo que se pueda re-verificar con lápiz y papel sin ejecutar
nada.

La sección de referencia de casi todas las pruebas es:

    b_w = 300 mm, h = 600 mm, recubrimiento 40 mm, estribo #3 (9.52 mm),
    f'c = 28 MPa, f_y = 420 MPa, 4 barras #8 (A_s = 4 · 506.7 = 2026.8 mm²)

    d = 600 − (40 + 9.52 + 25.4/2) = 537.78 mm
"""
import unittest
from dataclasses import asdict

from core.aashto.flexion import AashtoBeamSection
from core.aashto.torsion import AashtoBeamShearTorsionDesign
from core.flexion import BeamSection
from core.section_geometry import (
    RebarLayer,
    ReinforcementConfig,
    SectionProfile,
    SectionShape,
    steel_for_flanged_moment,
)
from core.torsion import BeamShearTorsionDesign


def armado_4n8() -> ReinforcementConfig:
    """4 barras #8 en un lecho, estribo #3. A_s = 2026.8 mm²."""
    return ReinforcementConfig(
        layers=[RebarLayer(4, 25.4, 506.7)], stirrup_diameter_mm=9.52
    )


SECCION = dict(
    b_mm=300.0, h_mm=600.0, cover_mm=40.0, fc_mpa=28.0, fy_mpa=420.0,
)
D_ESPERADO = 537.78


class Geometria(unittest.TestCase):
    """El perfil por sí solo, antes de que ninguna norma lo toque."""

    def setUp(self):
        self.t = SectionProfile.create(
            SectionShape.T, bw_mm=300.0, h_mm=600.0, bf_mm=1200.0, hf_mm=100.0
        )

    def test_rectangular_is_the_degenerate_case(self):
        # Con b_f = b_w el ala desaparece: A_c(a) = b·a y el centroide es a/2,
        # que es exactamente la sección rectangular de siempre.
        r = SectionProfile.create(SectionShape.RECTANGULAR, bw_mm=300.0, h_mm=500.0)
        self.assertEqual(r.compression_area_mm2(120.0), 300.0 * 120.0)
        self.assertEqual(r.compression_centroid_mm(120.0), 60.0)
        self.assertEqual(r.block_depth_mm(36000.0), 120.0)

    def test_a_flange_narrower_than_the_web_degrades_to_rectangular(self):
        # Un b_f mal ingresado no debe producir un ala de ancho negativo.
        p = SectionProfile.create(
            SectionShape.T, bw_mm=300.0, h_mm=600.0, bf_mm=250.0, hf_mm=100.0
        )
        self.assertIs(p.shape, SectionShape.RECTANGULAR)
        self.assertFalse(p.is_flanged)

    def test_compression_area_inside_and_below_the_flange(self):
        # a = 80 ≤ h_f = 100  ->  A_c = 1200 · 80
        self.assertAlmostEqual(self.t.compression_area_mm2(80.0), 96000.0)
        # a = 200 > h_f       ->  A_c = 1200·100 + 300·100
        self.assertAlmostEqual(self.t.compression_area_mm2(200.0), 150000.0)

    def test_compression_centroid_below_the_flange(self):
        # ȳ = (120000·50 + 30000·150) / 150000 = 70 mm
        self.assertAlmostEqual(self.t.compression_centroid_mm(200.0), 70.0)

    def test_block_depth_inverts_the_area(self):
        self.assertAlmostEqual(self.t.block_depth_mm(150000.0), 200.0)
        self.assertAlmostEqual(self.t.block_depth_mm(96000.0), 80.0)

    def test_gross_properties_of_the_t(self):
        # A_g = 1200·100 + 300·500 = 270 000 mm²
        # y_sup = (120000·50 + 150000·350)/270000 = 216.67 mm
        # I_g   = 9 225 · 10⁶ mm⁴ ;  S_inf = I_g/383.33 = 24.065 · 10⁶ mm³
        ag, y_inf, ig, s_inf = self.t.gross_properties()
        self.assertAlmostEqual(ag, 270000.0)
        self.assertAlmostEqual(y_inf, 383.333, places=2)
        self.assertAlmostEqual(ig / 1e6, 9225.0, places=1)
        self.assertAlmostEqual(s_inf / 1e6, 24.065, places=3)

    def test_gross_properties_reduce_to_bh2_over_6(self):
        r = SectionProfile.create(SectionShape.RECTANGULAR, bw_mm=300.0, h_mm=600.0)
        self.assertAlmostEqual(r.gross_properties()[3], 300.0 * 600.0 ** 2 / 6.0)

    def test_flange_width_limit_by_thickness(self):
        # T: b_w + 2·8·h_f = 300 + 1600 = 1900 mm  (ACI Tabla 6.3.2.1)
        self.assertAlmostEqual(self.t.aci_max_flange_width_mm(), 1900.0)
        # L: b_w + 1·6·h_f = 300 + 600 = 900 mm
        ele = SectionProfile.create(
            SectionShape.L, bw_mm=300.0, h_mm=600.0, bf_mm=800.0, hf_mm=100.0
        )
        self.assertAlmostEqual(ele.aci_max_flange_width_mm(), 900.0)

    def test_torsion_overhang_is_capped(self):
        # Voladizo real 450 mm, proyección del alma 500 mm, 4·h_f = 400 mm.
        # Manda el menor: 400 mm.
        self.assertAlmostEqual(self.t.torsion_overhang_mm(), 400.0)
        acp, pcp = self.t.torsion_gross_properties()
        self.assertAlmostEqual(acp, 300.0 * 600.0 + 2 * 400.0 * 100.0)   # 260 000
        self.assertAlmostEqual(pcp, 2 * (300.0 + 600.0) + 2 * 2 * 400.0)  # 3 400


class SolverPorPartes(unittest.TestCase):
    """El solver que comparten las dos normas (ala + alma)."""

    def test_block_that_fits_in_the_flange_uses_the_full_flange_width(self):
        perfil = SectionProfile.create(
            SectionShape.T, bw_mm=300.0, h_mm=600.0, bf_mm=1200.0, hf_mm=150.0
        )
        # M_n = 300 kN·m sobre b_f = 1200:
        #   disc = 537.78² − 2·300e6/(23.8·1200) = 289207 − 21008 = 268199
        #   a = 537.78 − 517.88 = 19.90 mm ≤ 150  ->  cabe en el ala
        #   A_s = 23.8 · 1200 · 19.90 / 420 = 1353 mm²
        as_mm2, ok = steel_for_flanged_moment(perfil, 300e6, D_ESPERADO, 23.8, 420.0)
        self.assertTrue(ok)
        self.assertAlmostEqual(as_mm2, 1353.0, delta=3.0)

    def test_block_below_the_flange_splits_flange_and_web(self):
        perfil = SectionProfile.create(
            SectionShape.T, bw_mm=300.0, h_mm=600.0, bf_mm=400.0, hf_mm=50.0
        )
        # M_n = 380/0.9 = 422.22 kN·m
        #   A_sf = 23.8·(400−300)·50/420       = 283.3 mm²
        #   M_nf = 283.3·420·(537.78 − 25)     = 61.01 kN·m
        #   M_nw = 422.22 − 61.01              = 361.21 kN·m
        #   a_w  = 537.78 − √(289207 − 101180) = 104.18 mm
        #   A_sw = 23.8·300·104.18/420         = 1770.6 mm²
        #   A_s  = 283.3 + 1770.6              = 2053.9 mm²
        as_mm2, ok = steel_for_flanged_moment(
            perfil, 380e6 / 0.9, D_ESPERADO, 23.8, 420.0
        )
        self.assertTrue(ok)
        self.assertAlmostEqual(as_mm2, 2054.0, delta=2.0)

    def test_an_impossible_moment_is_reported_as_unfeasible(self):
        perfil = SectionProfile.create(
            SectionShape.T, bw_mm=300.0, h_mm=600.0, bf_mm=400.0, hf_mm=50.0
        )
        as_mm2, ok = steel_for_flanged_moment(
            perfil, 5000e6, D_ESPERADO, 23.8, 420.0
        )
        self.assertFalse(ok)
        self.assertEqual(as_mm2, 0.0)


class FlexionACI(unittest.TestCase):

    def viga(self, **extra):
        return BeamSection(
            mu_nmm=300e6, reinforcement=armado_4n8(), **SECCION, **extra
        ).design()

    def test_a_t_with_bf_equal_to_bw_matches_the_rectangular_section(self):
        # Es la garantía de que agregar el ala no movió la sección rectangular:
        # el mismo motor, por el camino con ala, debe dar lo mismo.
        rect = self.viga()
        degenerada = self.viga(
            section_shape=SectionShape.T, bf_mm=300.0, hf_mm=100.0
        )
        comunes = ("a_mm", "c_mm", "jd_mm", "phi_mn_knm", "as_required_cm2",
                   "as_min_cm2", "as_max_cm2", "compression_kn", "tension_kn",
                   "status")
        for campo in comunes:
            self.assertEqual(getattr(rect, campo), getattr(degenerada, campo),
                             f"difiere {campo}")

    def test_the_block_stays_inside_a_wide_flange(self):
        # A_c = 2026.8·420/23.8 = 35 768 mm² < b_f·h_f = 180 000
        #   ->  a = 35 768/1200 = 29.81 mm,  ȳ = a/2 = 14.90
        #       jd = 537.78 − 14.90 = 522.88
        #       φM_n = 0.9·2026.8·420·522.88 = 400.6 kN·m
        r = self.viga(section_shape=SectionShape.T, bf_mm=1200.0, hf_mm=150.0)
        self.assertAlmostEqual(r.a_mm, 29.81, places=2)
        self.assertAlmostEqual(r.yc_mm, 14.90, places=2)
        self.assertAlmostEqual(r.jd_mm, 522.88, places=2)
        self.assertAlmostEqual(r.phi_mn_knm, 400.6, places=1)
        self.assertFalse(r.flanged_behaviour)
        self.assertEqual(r.asf_cm2, 0.0)

    def test_the_block_reaching_the_web_makes_it_a_real_t(self):
        # A_c = 35 768 > b_f·h_f = 400·50 = 20 000
        #   ->  a = 50 + 15 768/300 = 102.56 mm
        #       ȳ = (20000·25 + 15768·(50+26.28))/35768 = 47.60 mm
        #       jd = 537.78 − 47.60 = 490.18
        #       A_sf = 23.8·100·50/420 = 283.3 mm² = 2.83 cm²
        r = self.viga(section_shape=SectionShape.T, bf_mm=400.0, hf_mm=50.0)
        self.assertAlmostEqual(r.a_mm, 102.56, places=2)
        self.assertAlmostEqual(r.yc_mm, 47.60, places=2)
        self.assertAlmostEqual(r.jd_mm, 490.18, places=2)
        self.assertTrue(r.flanged_behaviour)
        self.assertAlmostEqual(r.asf_cm2, 2.83, places=2)

    def test_the_flange_never_reduces_the_capacity(self):
        rect = self.viga()
        angosta = self.viga(section_shape=SectionShape.T, bf_mm=400.0, hf_mm=50.0)
        ancha = self.viga(section_shape=SectionShape.T, bf_mm=1200.0, hf_mm=150.0)
        self.assertLess(rect.phi_mn_knm, angosta.phi_mn_knm)
        self.assertLess(angosta.phi_mn_knm, ancha.phi_mn_knm)
        # Y a la inversa: con ala hace falta menos acero para el mismo M_u.
        self.assertLess(ancha.as_required_cm2, rect.as_required_cm2)

    def test_minimum_steel_uses_the_web_width(self):
        # §9.6.1.2 con el ala comprimida se mide sobre b_w, así que A_s,min no
        # puede cambiar al ensanchar el ala.
        rect = self.viga()
        con_ala = self.viga(section_shape=SectionShape.T, bf_mm=1500.0, hf_mm=150.0)
        self.assertAlmostEqual(rect.as_min_cm2, con_ala.as_min_cm2)

    def test_maximum_steel_grows_with_the_flange(self):
        # A_s,max sale del área comprimida a ε_t = 0.004, no de ρ_max·b·d.
        #   a_max = 0.85 · 537.78 · 3/7 = 195.91 mm
        #   A_c(a_max) = 1200·150 + 300·45.91 = 193 772 mm²
        #   A_s,max = 23.8 · 193 772 / 420 = 10 980 mm² = 109.80 cm²
        r = self.viga(section_shape=SectionShape.T, bf_mm=1200.0, hf_mm=150.0)
        self.assertAlmostEqual(r.as_max_cm2, 109.80, places=1)
        # Contra ρ_max·b_w·d = 33.30 cm² de la rectangular: el ala admite
        # bastante más acero antes de dejar de ser dúctil.
        self.assertAlmostEqual(self.viga().as_max_cm2, 33.30, places=1)

    def test_an_l_section_has_one_overhang_not_two(self):
        # Mismo b_f: la L tiene el mismo ancho comprimido que la T, así que la
        # diferencia está en los límites, no en la resistencia.
        te = self.viga(section_shape=SectionShape.T, bf_mm=900.0, hf_mm=150.0)
        ele = self.viga(section_shape=SectionShape.L, bf_mm=900.0, hf_mm=150.0)
        self.assertAlmostEqual(te.phi_mn_knm, ele.phi_mn_knm)
        self.assertAlmostEqual(te.bf_max_mm, 300 + 2 * 8 * 150)   # 2700
        self.assertAlmostEqual(ele.bf_max_mm, 300 + 1 * 6 * 150)  # 1200

    def test_an_excessive_flange_width_is_warned(self):
        # b_f = 1500 > b_w + 2·8·h_f = 300 + 800 = 1100
        r = self.viga(section_shape=SectionShape.T, bf_mm=1500.0, hf_mm=50.0)
        self.assertTrue(any("Tabla 6.3.2.1" in w for w in r.warnings), r.warnings)

    def test_a_flange_thicker_than_the_beam_is_an_error(self):
        r = self.viga(section_shape=SectionShape.T, bf_mm=900.0, hf_mm=600.0)
        self.assertEqual(r.status, "ERROR")


class FlexionAASHTO(unittest.TestCase):

    def viga(self, **extra):
        return AashtoBeamSection(
            mu_nmm=300e6, reinforcement=armado_4n8(), **SECCION, **extra
        ).design()

    def test_a_t_with_bf_equal_to_bw_matches_the_rectangular_section(self):
        rect = asdict(self.viga())
        degenerada = asdict(self.viga(
            section_shape=SectionShape.T, bf_mm=300.0, hf_mm=100.0))
        nuevos = {"section_shape", "bf_mm", "hf_mm", "yc_mm",
                  "flanged_behaviour", "asf_cm2", "bf_max_mm",
                  "warnings", "aashto_warnings"}
        for campo in rect:
            if campo in nuevos:
                continue
            self.assertEqual(rect[campo], degenerada[campo], f"difiere {campo}")

    def test_the_cracking_moment_uses_the_flanged_section_modulus(self):
        # S_inf = 24.065·10⁶ mm³ (ver Geometria), f_r = 0.62·√28 = 3.2807 MPa
        #   M_cr = 0.67 · 1.6 · 3.2807 · 24.065e6 = 84.6 kN·m
        # contra 63.3 kN·m de la rectangular con S = b·h²/6 = 18·10⁶.
        r = self.viga(section_shape=SectionShape.T, bf_mm=1200.0, hf_mm=100.0)
        self.assertAlmostEqual(r.sc_mm3 / 1e6, 24.065, places=3)
        self.assertAlmostEqual(r.mcr_knm, 84.6, places=1)
        self.assertAlmostEqual(self.viga().mcr_knm, 63.3, places=1)

    def test_the_flange_raises_the_strain_and_never_lowers_phi(self):
        # Con ala el eje neutro queda más arriba, así que ε_t crece y φ no
        # puede bajar: es el mecanismo con el que AASHTO premia la sección T.
        rect = self.viga()
        con_ala = self.viga(section_shape=SectionShape.T, bf_mm=1200.0, hf_mm=100.0)
        self.assertGreater(con_ala.epsilon_t, rect.epsilon_t)
        self.assertGreaterEqual(con_ala.phi_flexion, rect.phi_flexion)

    def test_the_effective_width_note_is_about_tributary_width(self):
        # AASHTO no ata b_f al espesor del ala: la memoria debe decirlo, y el
        # motor no debe emitir la advertencia de ACI como si fuera suya.
        r = self.viga(section_shape=SectionShape.T, bf_mm=1200.0, hf_mm=100.0)
        self.assertFalse(any("Tabla 6.3.2.1" in w for w in r.aashto_warnings))


class Cortante(unittest.TestCase):
    """El cortante usa el alma; el ala sólo mueve el brazo de palanca."""

    CORTANTE = dict(
        vu_n=180e3, b_mm=300.0, h_mm=600.0, cover_mm=40.0, fc_mpa=28.0,
        fyt_mpa=420.0, stirrup_diameter_mm=9.52, stirrup_area_mm2=71.0,
        stirrup_legs=2, lam=1.0, d_mm=D_ESPERADO, fy_long_mpa=420.0,
    )

    def test_aci_shear_ignores_the_flange(self):
        # V_c de ACI se calcula sobre b_w: el ala no puede cambiarlo.
        rect = BeamShearTorsionDesign(**self.CORTANTE).design()
        con_ala = BeamShearTorsionDesign(
            **self.CORTANTE, section_shape=SectionShape.T,
            bf_mm=1200.0, hf_mm=150.0
        ).design()
        self.assertAlmostEqual(rect.vc_kn, con_ala.vc_kn)
        self.assertAlmostEqual(rect.s_adopted_mm, con_ala.s_adopted_mm)

    def test_aashto_dv_uses_the_real_lever_arm(self):
        # Con ala, d_v se mide contra d_e − ȳ y no contra d_e − a/2, porque el
        # centroide de la compresión ya no está a media altura del bloque.
        from core.aashto.shear import AashtoBeamShearDesign
        comun = dict(
            vu_n=180e3, b_mm=300.0, h_mm=600.0, cover_mm=40.0, fc_mpa=28.0,
            fyt_mpa=420.0, stirrup_diameter_mm=9.52, stirrup_area_mm2=71.0,
            stirrup_legs=2, lam=1.0, d_mm=D_ESPERADO, a_mm=102.56,
        )
        rect = AashtoBeamShearDesign(**comun).design()
        con_ala = AashtoBeamShearDesign(
            **comun, section_shape=SectionShape.T, bf_mm=400.0, hf_mm=50.0
        ).design()
        self.assertEqual(rect.dv_governing, "d_e − a/2")
        self.assertEqual(con_ala.dv_governing, "d_e − ȳ")
        # ȳ = 47.60 < a/2 = 51.28, así que el brazo con ala es mayor.
        self.assertGreater(con_ala.dv_mm, rect.dv_mm)


class Torsion(unittest.TestCase):

    TORSION = dict(
        vu_n=180e3, b_mm=300.0, h_mm=600.0, cover_mm=40.0, fc_mpa=28.0,
        fyt_mpa=420.0, stirrup_diameter_mm=9.52, stirrup_area_mm2=71.0,
        stirrup_legs=2, lam=1.0, d_mm=D_ESPERADO, torsion_enabled=True,
        tu_nmm=40e6, fy_long_mpa=420.0, torsion_type="EQUILIBRIO",
    )

    def test_acp_includes_the_capped_flange_overhang(self):
        # b_e = min(450, 600−100, 4·100) = 400 mm
        #   A_cp = 300·600 + 2·400·100 = 260 000 mm²
        #   p_cp = 2·(300+600) + 2·2·400 = 3 400 mm
        r = BeamShearTorsionDesign(
            **self.TORSION, section_shape=SectionShape.T,
            bf_mm=1200.0, hf_mm=100.0
        ).design()
        self.assertAlmostEqual(r.acp_mm2, 260000.0)
        self.assertAlmostEqual(r.pcp_mm, 3400.0)
        self.assertAlmostEqual(r.flange_overhang_mm, 400.0)

    def test_the_stirrup_core_stays_on_the_web(self):
        # A_oh y p_h son los del estribo cerrado del alma: tomarlos menores
        # exige más estribo, que es el lado seguro.
        rect = BeamShearTorsionDesign(**self.TORSION).design()
        con_ala = BeamShearTorsionDesign(
            **self.TORSION, section_shape=SectionShape.T,
            bf_mm=1200.0, hf_mm=100.0
        ).design()
        self.assertAlmostEqual(rect.aoh_mm2, con_ala.aoh_mm2)
        self.assertAlmostEqual(rect.ph_mm, con_ala.ph_mm)

    def test_the_threshold_grows_with_acp(self):
        # T_th = 0.083·√28·A_cp²/p_cp
        #   rectangular: 0.4392 · 180000²/1800 = 7.91 kN·m
        #   T:           0.4392 · 260000²/3400 = 8.73 kN·m
        rect = BeamShearTorsionDesign(**self.TORSION).design()
        con_ala = BeamShearTorsionDesign(
            **self.TORSION, section_shape=SectionShape.T,
            bf_mm=1200.0, hf_mm=100.0
        ).design()
        self.assertAlmostEqual(rect.t_th_knm, 7.91, places=2)
        self.assertAlmostEqual(con_ala.t_th_knm, 8.73, places=2)

    def test_the_monolithic_flange_caveat_is_reported(self):
        r = BeamShearTorsionDesign(
            **self.TORSION, section_shape=SectionShape.T,
            bf_mm=1200.0, hf_mm=100.0
        ).design()
        self.assertTrue(any("§22.7.4.1" in w for w in r.warnings), r.warnings)

    def test_an_l_section_says_one_side_not_both(self):
        r = BeamShearTorsionDesign(
            **self.TORSION, section_shape=SectionShape.L,
            bf_mm=900.0, hf_mm=150.0
        ).design()
        texto = " ".join(r.warnings)
        self.assertIn("del lado del ala", texto)
        self.assertNotIn("a cada lado", texto)

    def test_aashto_torsion_uses_the_same_contour(self):
        comun = dict(self.TORSION)
        comun.update(a_mm=102.56, mu_nmm=380e6, as_long_mm2=2026.8)
        r = AashtoBeamShearTorsionDesign(
            **comun, section_shape=SectionShape.T, bf_mm=1200.0, hf_mm=100.0
        ).design()
        self.assertAlmostEqual(r.acp_mm2, 260000.0)
        self.assertAlmostEqual(r.pcp_mm, 3400.0)


class Memoria(unittest.TestCase):
    """La memoria describe lo que realmente se calculó."""

    def memoria(self, forma, bf, hf, code=None):
        from core.design_code import DesignCode, beam_shear_design, flexure_design
        from core.project import ProjectInfo
        from core.report import generate_beam_report
        from core.units import UnitSystem
        code = code or DesignCode.ACI_318_19
        flex = flexure_design(
            code, mu_nmm=380e6, reinforcement=armado_4n8(), **SECCION,
            section_shape=forma, bf_mm=bf, hf_mm=hf, ms_nmm=220e6,
            bar_spec="A615", exposure_class=1, lam=1.0,
        )
        cort = beam_shear_design(
            code, vu_n=180e3, b_mm=300.0, h_mm=600.0, cover_mm=40.0,
            fc_mpa=28.0, fyt_mpa=420.0, stirrup_diameter_mm=9.52,
            stirrup_area_mm2=71.0, stirrup_legs=2, lam=1.0, d_mm=flex.d_mm,
            a_mm=flex.a_mm, mu_nmm=380e6,
            as_long_mm2=flex.as_provided_cm2 * 100.0, torsion_enabled=True,
            tu_nmm=40e6, fy_long_mpa=420.0, torsion_type="EQUILIBRIO",
            section_shape=forma, bf_mm=bf, hf_mm=hf,
        )
        return generate_beam_report(
            flexion=flex, shear=cort, unit_system=UnitSystem.SI,
            info=ProjectInfo(),
        )

    def test_the_t_report_shows_the_two_step_derivation(self):
        html = self.memoria(SectionShape.T, 400.0, 50.0)
        self.assertIn("Viga T", html)
        self.assertIn("A_{sf}", html)
        self.assertIn("el alma toma el momento restante", html)
        self.assertIn(r"\bar{y}", html)

    def test_the_rectangular_report_keeps_the_classic_derivation(self):
        html = self.memoria(SectionShape.RECTANGULAR, 0.0, 0.0)
        self.assertIn("Viga rectangular", html)
        self.assertNotIn("A_{sf}", html)
        self.assertNotIn(r"\bar{y}", html)

    def test_each_code_states_its_own_effective_width_rule(self):
        from core.design_code import DesignCode
        aci = self.memoria(SectionShape.T, 1200.0, 150.0)
        aashto = self.memoria(SectionShape.T, 1200.0, 150.0,
                              DesignCode.AASHTO_LRFD_2020)
        self.assertIn("Tabla 6.3.2.1", aci)
        self.assertNotIn("4.6.2.6.1", aci)
        self.assertIn("4.6.2.6.1", aashto)
        self.assertIn("ancho tributario", aashto)


if __name__ == "__main__":
    unittest.main()

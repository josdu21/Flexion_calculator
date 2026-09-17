"""Motores AASHTO LRFD 2020, contra cálculo a mano.

Los valores esperados están calculados aparte con las ecuaciones de la norma en
su forma SI, y anotados en cada prueba para que se puedan re-verificar sin
ejecutar nada.
"""
import math
import unittest

from core.aashto.flexion import (
    AashtoBeamSection,
    alpha_1,
    beta_1,
    modulus_of_rupture,
    phi_flexure,
    strain_limits,
)
from core.aashto.shear import (
    PHI_SHEAR,
    AashtoBeamShearDesign,
    AashtoSlabShearCheck,
    av_s_min,
    dv_effective,
    s_max_mm,
    vc_nominal,
)
from core.aashto.torsion import (
    AashtoBeamShearTorsionDesign,
    equivalent_shear_n,
    t_cracking_nmm,
)
from core.section_geometry import RebarLayer, ReinforcementConfig


def viga_3n6() -> ReinforcementConfig:
    """3 barras #6 en un lecho, estribo #3."""
    return ReinforcementConfig(
        layers=[RebarLayer(3, 19.05, 284.0)], stirrup_diameter_mm=9.52
    )


class FactoresDeResistencia(unittest.TestCase):
    """φ variable con ε_t (§5.5.4.2) — el corazón del método AASHTO."""

    def test_tension_controlled_gets_the_full_factor(self):
        self.assertAlmostEqual(phi_flexure(0.0080, 420.0), 0.90)

    def test_compression_controlled_drops_to_075(self):
        self.assertAlmostEqual(phi_flexure(0.0015, 420.0), 0.75)

    def test_the_transition_interpolates_linearly(self):
        # Grado 60: ε_cl = 420/200000 = 0.0021, ε_tl = 0.0050.
        # En el punto medio ε_t = 0.00355 → φ = 0.75 + 0.15·0.5 = 0.825
        eps_cl, eps_tl = strain_limits(420.0)
        self.assertAlmostEqual(eps_cl, 0.0021)
        self.assertAlmostEqual(eps_tl, 0.0050)
        self.assertAlmostEqual(phi_flexure((eps_cl + eps_tl) / 2, 420.0), 0.825)

    def test_the_factor_never_leaves_its_bounds(self):
        for eps in (-1.0, 0.0, 0.002, 0.05, 100.0):
            self.assertGreaterEqual(phi_flexure(eps, 420.0), 0.75)
            self.assertLessEqual(phi_flexure(eps, 420.0), 0.90)

    def test_higher_grades_move_the_limits(self):
        # Grado 75 (520 MPa): ε_cl = 0.0026 y ε_tl = 0.0056 (Tabla C5.6.2.1-1)
        eps_cl, eps_tl = strain_limits(520.0)
        self.assertAlmostEqual(eps_cl, 0.0026)
        self.assertAlmostEqual(eps_tl, 0.0056)


class BloqueDeCompresion(unittest.TestCase):
    def test_beta_1_matches_aci(self):
        self.assertAlmostEqual(beta_1(28.0), 0.85)
        self.assertAlmostEqual(beta_1(35.0), 0.80)
        self.assertAlmostEqual(beta_1(100.0), 0.65)

    def test_alpha_1_only_drops_above_70_mpa(self):
        # §5.6.2.2: 0.85 hasta 70 MPa; luego −0.02 por cada 7 MPa, piso 0.75.
        self.assertAlmostEqual(alpha_1(28.0), 0.85)
        self.assertAlmostEqual(alpha_1(70.0), 0.85)
        self.assertAlmostEqual(alpha_1(77.0), 0.83)
        self.assertAlmostEqual(alpha_1(150.0), 0.75)


class Flexion(unittest.TestCase):
    """Viga 300×500, r = 40, f'c = 28, f_y = 420, 3 #6, M_u = 100 kN·m."""

    def setUp(self):
        self.r = AashtoBeamSection(
            mu_nmm=100e6, b_mm=300.0, h_mm=500.0, cover_mm=40.0,
            fc_mpa=28.0, fy_mpa=420.0, reinforcement=viga_3n6(),
        ).design()

    def test_effective_depth_and_compression_block(self):
        # d = 500 − (40 + 9.52 + 19.05/2) = 440.955
        # a = A_s·f_y/(α₁·f'c·b) = 852·420/(0.85·28·300) = 50.118
        # c = a/β₁ = 58.962
        self.assertAlmostEqual(self.r.d_mm, 440.955, places=3)
        self.assertAlmostEqual(self.r.a_mm, 50.1176, places=3)
        self.assertAlmostEqual(self.r.c_mm, 58.9619, places=3)

    def test_the_section_is_tension_controlled(self):
        # ε_t = 0.003·(d_t − c)/c = 0.003·(440.955 − 58.962)/58.962 = 0.01944
        self.assertAlmostEqual(self.r.epsilon_t, 0.019436, places=5)
        self.assertEqual(self.r.section_behaviour, "TRACCIÓN CONTROLADA")
        self.assertAlmostEqual(self.r.phi_flexion, 0.90)

    def test_resisting_moment(self):
        # φM_n = 0.9·852·420·(440.955 − 25.059) = 133.94 kN·m
        self.assertAlmostEqual(self.r.phi_mn_knm, 133.94, places=2)

    def test_cracking_moment_uses_the_gross_section(self):
        # f_r = 0.62·√28 = 3.2807 MPa; S_c = 300·500²/6 = 12.5e6 mm³
        # M_cr = γ₃·γ₁·f_r·S_c = 0.67·1.6·3.2807·12.5e6 = 43.96 kN·m
        self.assertAlmostEqual(modulus_of_rupture(28.0), 3.28073, places=5)
        self.assertAlmostEqual(self.r.sc_mm3, 12.5e6)
        self.assertAlmostEqual(self.r.mcr_knm, 43.9618, places=3)

    def test_minimum_reinforcement_is_a_moment_criterion(self):
        # min(1.33·M_u, M_cr) = min(133, 43.96) = 43.96 kN·m
        self.assertAlmostEqual(self.r.mu_min_knm, 43.9618, places=3)
        self.assertTrue(self.r.min_reinf_ok)

    def test_a706_bars_raise_the_cracking_moment(self):
        # γ₃ pasa de 0.67 a 0.75, así que M_cr sube en esa proporción.
        a706 = AashtoBeamSection(
            mu_nmm=100e6, b_mm=300.0, h_mm=500.0, cover_mm=40.0,
            fc_mpa=28.0, fy_mpa=420.0, reinforcement=viga_3n6(),
            bar_spec="A706",
        ).design()
        self.assertAlmostEqual(a706.gamma_3, 0.75)
        self.assertAlmostEqual(a706.mcr_knm, self.r.mcr_knm * 0.75 / 0.67, places=4)

    def test_a_heavily_reinforced_section_loses_phi(self):
        pesada = AashtoBeamSection(
            mu_nmm=400e6, b_mm=300.0, h_mm=500.0, cover_mm=40.0,
            fc_mpa=28.0, fy_mpa=420.0,
            reinforcement=ReinforcementConfig(
                layers=[RebarLayer(6, 31.75, 792.0)], stirrup_diameter_mm=9.52
            ),
        ).design()
        self.assertLess(pesada.phi_flexion, 0.90)
        self.assertNotEqual(pesada.section_behaviour, "TRACCIÓN CONTROLADA")
        self.assertTrue(
            any("§5.5.4.2" in w for w in pesada.warnings),
            "Debería avisar que φ bajó",
        )

    def test_as_max_is_the_compression_controlled_limit(self):
        # ε_t = ε_cl = 0.0021 → c = 0.003·440.955/0.0051 = 259.38
        # a = 0.85·c = 220.47 → A_s = 0.85·28·300·220.47/420 = 3748 mm²
        self.assertAlmostEqual(self.r.as_max_cm2, 37.4812, places=3)

    def test_a_section_that_cannot_take_the_moment_is_flagged(self):
        imposible = AashtoBeamSection(
            mu_nmm=2000e6, b_mm=300.0, h_mm=500.0, cover_mm=40.0,
            fc_mpa=28.0, fy_mpa=420.0, reinforcement=viga_3n6(),
        ).design()
        self.assertEqual(imposible.status, "AUMENTAR SECCIÓN")

    def test_zero_inputs_do_not_raise(self):
        for campo in ("b_mm", "fc_mpa", "fy_mpa"):
            with self.subTest(campo=campo):
                datos = dict(
                    mu_nmm=100e6, b_mm=300.0, h_mm=500.0, cover_mm=40.0,
                    fc_mpa=28.0, fy_mpa=420.0, reinforcement=viga_3n6(),
                )
                datos[campo] = 0.0
                self.assertEqual(AashtoBeamSection(**datos).design().status, "ERROR")


class ControlDeFisuracion(unittest.TestCase):
    """§5.6.7 — sólo se revisa si se dio el momento de servicio."""

    def _con_ms(self, ms_nmm, exposure_class=1):
        return AashtoBeamSection(
            mu_nmm=100e6, b_mm=300.0, h_mm=500.0, cover_mm=40.0,
            fc_mpa=28.0, fy_mpa=420.0, reinforcement=viga_3n6(),
            ms_nmm=ms_nmm, exposure_class=exposure_class,
        ).design()

    def test_it_is_skipped_without_a_service_moment(self):
        r = self._con_ms(0.0)
        self.assertFalse(r.crack_control_applies)
        self.assertTrue(r.crack_control_ok)

    def test_it_runs_when_the_service_moment_is_given(self):
        r = self._con_ms(65e6)
        self.assertTrue(r.crack_control_applies)
        # d_c = 40 + 9.52 + 19.05/2 = 59.045
        self.assertAlmostEqual(r.dc_mm, 59.045, places=3)
        # β_s = 1 + d_c/(0.7·(h − d_c)) = 1 + 59.045/(0.7·440.955) = 1.19129
        self.assertAlmostEqual(r.beta_s, 1.191289, places=5)
        self.assertGreater(r.crack_spacing_max_mm, 0.0)

    def test_class_2_exposure_is_stricter(self):
        clase1 = self._con_ms(65e6, exposure_class=1)
        clase2 = self._con_ms(65e6, exposure_class=2)
        self.assertAlmostEqual(clase2.gamma_e, 0.75)
        # γ_e multiplica el término principal, así que la separación admisible baja.
        self.assertLess(clase2.crack_spacing_max_mm, clase1.crack_spacing_max_mm)

    def test_the_service_stress_is_capped_at_06_fy(self):
        r = self._con_ms(900e6)
        self.assertAlmostEqual(r.fss_mpa, 0.6 * 420.0)


class CortanteViga(unittest.TestCase):
    """Viga 300×500, d = 440.955, a = 50.118, V_u = 250 kN, estribo #3 de 2 ramas."""

    def setUp(self):
        self.r = AashtoBeamShearDesign(
            vu_n=250e3, b_mm=300.0, h_mm=500.0, cover_mm=40.0, fc_mpa=28.0,
            fyt_mpa=420.0, stirrup_diameter_mm=9.52, stirrup_area_mm2=71.0,
            stirrup_legs=2, d_mm=440.955, a_mm=50.118,
            mu_nmm=100e6, as_long_mm2=852.0, fy_long_mpa=420.0,
        ).design()

    def test_dv_takes_the_largest_of_the_three_branches(self):
        # d_e − a/2 = 415.90 ; 0.9·d_e = 396.86 ; 0.72·h = 360.0
        self.assertAlmostEqual(self.r.dv_mm, 415.896, places=3)
        self.assertEqual(self.r.dv_governing, "d_e − a/2")

    def test_the_report_can_typeset_every_governing_label(self):
        # La memoria traduce esas etiquetas a LaTeX con una tabla fija; si el
        # motor renombra una rama, acá se nota antes de que salga en texto pelado.
        from core.report import _DV_TEX
        etiquetas = {
            dv_effective(de_mm=400.0, a_mm=10.0, h_mm=500.0)[1],
            dv_effective(de_mm=400.0, a_mm=120.0, h_mm=450.0)[1],
            dv_effective(de_mm=400.0, a_mm=120.0, h_mm=600.0)[1],
        }
        self.assertEqual(len(etiquetas), 3, "Las tres ramas deben ser distintas")
        for etiqueta in etiquetas:
            self.assertIn(etiqueta, _DV_TEX)

    def test_each_branch_can_govern(self):
        # Poco armada: el brazo interno queda alto y manda el propio d_e − a/2.
        dv, rama = dv_effective(de_mm=400.0, a_mm=10.0, h_mm=500.0)
        self.assertEqual(rama, "d_e − a/2")
        self.assertAlmostEqual(dv, 395.0)
        # Muy armada: a/2 se come el brazo, entra el piso 0.9·d_e.
        dv, rama = dv_effective(de_mm=400.0, a_mm=120.0, h_mm=450.0)
        self.assertEqual(rama, "0.9·d_e")
        self.assertAlmostEqual(dv, 360.0)
        # Sección poco esbelta con d_e chico: manda 0.72·h.
        dv, rama = dv_effective(de_mm=400.0, a_mm=120.0, h_mm=600.0)
        self.assertEqual(rama, "0.72·h")
        self.assertAlmostEqual(dv, 432.0)

    def test_concrete_contribution(self):
        # V_c = 0.083·2.0·√28·300·415.896 = 109.60 kN ; φ = 0.90
        self.assertAlmostEqual(self.r.vc_kn, 109.596, places=2)
        self.assertAlmostEqual(self.r.phi_vc_kn, 98.636, places=2)
        self.assertAlmostEqual(self.r.beta, 2.0)
        self.assertAlmostEqual(self.r.theta_deg, 45.0)

    def test_steel_demand_and_spacing(self):
        # V_s = V_u/φ − V_c = 277.78 − 109.60 = 168.18 kN
        # s = A_v·f_yt·d_v·cot θ/V_s = 142·420·415.896/168182 = 147.48 → 145 mm
        self.assertAlmostEqual(self.r.vs_required_kn, 168.182, places=2)
        self.assertAlmostEqual(self.r.s_required_mm, 147.483, places=2)
        self.assertAlmostEqual(self.r.s_adopted_mm, 145.0)

    def test_minimum_transverse_reinforcement(self):
        # (A_v/s)_min = 0.083·√28·300/420 = 0.31371 mm²/mm
        self.assertAlmostEqual(self.r.av_s_min_value, 0.313710, places=5)
        self.assertAlmostEqual(av_s_min(28.0, 300.0, 420.0), 0.313710, places=5)

    def test_maximum_spacing_switches_at_0125_fc(self):
        # v_u = V_u/(φ·b·d_v); el corte está en 0.125·f'c = 3.5 MPa
        bajo = s_max_mm(250e3, 28.0, 300.0, 415.896)
        self.assertAlmostEqual(bajo, min(0.8 * 415.896, 600.0), places=3)
        alto = s_max_mm(500e3, 28.0, 300.0, 415.896)
        self.assertAlmostEqual(alto, min(0.4 * 415.896, 300.0), places=3)

    def test_the_section_cap_is_on_total_resistance(self):
        # V_n ≤ 0.25·f'c·b_v·d_v = 873.4 kN → φ·V_n,max = 786.0 kN
        self.assertAlmostEqual(self.r.vn_max_kn, 873.382, places=2)
        self.assertAlmostEqual(self.r.phi_vn_max_kn, 786.043, places=2)

        excedida = AashtoBeamShearDesign(
            vu_n=900e3, b_mm=300.0, h_mm=500.0, cover_mm=40.0, fc_mpa=28.0,
            fyt_mpa=420.0, stirrup_diameter_mm=9.52, stirrup_area_mm2=71.0,
            d_mm=440.955, a_mm=50.118,
        ).design()
        self.assertEqual(excedida.status, "AUMENTAR SECCIÓN")

    def test_no_stirrups_below_half_of_phi_vc(self):
        floja = AashtoBeamShearDesign(
            vu_n=40e3, b_mm=300.0, h_mm=500.0, cover_mm=40.0, fc_mpa=28.0,
            fyt_mpa=420.0, stirrup_diameter_mm=9.52, stirrup_area_mm2=71.0,
            d_mm=440.955, a_mm=50.118,
        ).design()
        self.assertEqual(floja.regime, "NO REQUIERE")
        self.assertEqual(floja.s_adopted_mm, 0.0)

    def test_longitudinal_reinforcement_check(self):
        # M_u/(φ_f·d_v) + (V_u/φ_v − 0.5·V_s)·cot θ
        #   = 100e6/(0.9·415.896) + (277778 − 85531) = 267159 + 192247 = 459406 N
        self.assertTrue(self.r.long_check_applies)
        self.assertAlmostEqual(self.r.long_demand_n, 459406.0, delta=5.0)
        self.assertAlmostEqual(self.r.long_capacity_n, 852.0 * 420.0)
        self.assertFalse(self.r.long_reinf_ok)

    def test_the_longitudinal_check_is_skipped_without_data(self):
        sin_datos = AashtoBeamShearDesign(
            vu_n=250e3, b_mm=300.0, h_mm=500.0, cover_mm=40.0, fc_mpa=28.0,
            fyt_mpa=420.0, stirrup_diameter_mm=9.52, stirrup_area_mm2=71.0,
            d_mm=440.955, a_mm=50.118,
        ).design()
        self.assertFalse(sin_datos.long_check_applies)
        self.assertTrue(sin_datos.long_reinf_ok)


class CortanteLosa(unittest.TestCase):
    def test_capacity_of_a_thin_slab(self):
        # d_e = 200 − 20 − 6.35 = 173.65 ; d_v = 173.65 − 7.5 = 166.15
        # V_c = 0.083·2·√28·1000·166.15 = 145.94 kN
        r = AashtoSlabShearCheck(
            vu_n=60e3, b_mm=1000.0, h_mm=200.0, cover_mm=20.0,
            fc_mpa=28.0, a_mm=15.0,
        ).check()
        self.assertAlmostEqual(r.de_mm, 173.65, places=2)
        self.assertAlmostEqual(r.dv_mm, 166.15, places=2)
        self.assertAlmostEqual(r.vc_kn, 145.944, places=2)
        self.assertAlmostEqual(r.phi_vc_kn, 131.350, places=2)
        self.assertEqual(r.status, "OK")
        self.assertTrue(r.simplified_applicable)

    def test_a_thick_slab_falls_outside_the_simplified_procedure(self):
        # §5.7.3.4.1 sólo cubre elementos sin estribos si h < 400 mm.
        r = AashtoSlabShearCheck(
            vu_n=60e3, b_mm=1000.0, h_mm=450.0, cover_mm=25.0, fc_mpa=28.0,
        ).check()
        self.assertFalse(r.simplified_applicable)
        self.assertTrue(
            any("5.7.3.4.1" in w for w in r.warnings),
            "Debería avisar que queda fuera del procedimiento simplificado",
        )

    def test_an_overloaded_slab_is_flagged(self):
        r = AashtoSlabShearCheck(
            vu_n=400e3, b_mm=1000.0, h_mm=200.0, cover_mm=20.0, fc_mpa=28.0,
        ).check()
        self.assertEqual(r.status, "AUMENTAR SECCIÓN")

    def test_no_load_reports_an_infinite_ratio(self):
        r = AashtoSlabShearCheck(
            vu_n=0.0, b_mm=1000.0, h_mm=200.0, cover_mm=20.0, fc_mpa=28.0,
        ).check()
        self.assertEqual(r.ratio, float("inf"))


class Torsion(unittest.TestCase):
    """Viga 350×600, r = 40, d = 540, a = 60, V_u = 250 kN, T_u = 45 kN·m."""

    def setUp(self):
        self.r = AashtoBeamShearTorsionDesign(
            vu_n=250e3, b_mm=350.0, h_mm=600.0, cover_mm=40.0, fc_mpa=28.0,
            fyt_mpa=420.0, stirrup_diameter_mm=9.52, stirrup_area_mm2=71.0,
            stirrup_legs=2, d_mm=540.0, a_mm=60.0,
            mu_nmm=300e6, as_long_mm2=1420.0,
            torsion_enabled=True, tu_nmm=45e6, fy_long_mpa=420.0,
        ).design()

    def test_section_properties(self):
        # A_cp = 350·600 = 210000 ; p_c = 1900
        # x₁ = 350 − 80 − 9.52 = 260.48 ; y₁ = 600 − 80 − 9.52 = 510.48
        self.assertAlmostEqual(self.r.acp_mm2, 210000.0)
        self.assertAlmostEqual(self.r.pcp_mm, 1900.0)
        self.assertAlmostEqual(self.r.aoh_mm2, 260.48 * 510.48, places=3)
        self.assertAlmostEqual(self.r.ph_mm, 1541.92, places=3)
        self.assertAlmostEqual(self.r.ao_mm2, 0.85 * 260.48 * 510.48, places=3)

    def test_cracking_torsion(self):
        # T_cr = 0.125·√28·(210000²/1900) = 15.35 kN·m
        self.assertAlmostEqual(
            t_cracking_nmm(28.0, 1.0, 210000.0, 1900.0) / 1e6, 15.3523, places=3
        )
        self.assertAlmostEqual(self.r.t_cr_knm, 15.3523, places=3)

    def test_the_threshold_is_a_quarter_of_the_cracking_torsion(self):
        # §5.7.2.1: se desprecia si T_u ≤ 0.25·φ·T_cr
        self.assertAlmostEqual(self.r.t_th_knm, 0.25 * self.r.t_cr_knm)
        self.assertAlmostEqual(
            self.r.phi_t_th_knm, PHI_SHEAR * 0.25 * self.r.t_cr_knm
        )
        self.assertEqual(self.r.torsion_regime, "DISEÑO")

    def test_small_torsion_is_neglected(self):
        chica = AashtoBeamShearTorsionDesign(
            vu_n=250e3, b_mm=350.0, h_mm=600.0, cover_mm=40.0, fc_mpa=28.0,
            fyt_mpa=420.0, stirrup_diameter_mm=9.52, stirrup_area_mm2=71.0,
            d_mm=540.0, a_mm=60.0, torsion_enabled=True, tu_nmm=3e6,
        ).design()
        self.assertEqual(chica.torsion_regime, "DESPRECIABLE")

    def test_equivalent_shear_for_a_solid_section(self):
        # V_u,eq = √(V_u² + (0.9·p_h·T_u/(2·A_o))²) = 372.6 kN
        esperado = equivalent_shear_n(250e3, 45e6, self.r.ph_mm, self.r.ao_mm2)
        self.assertAlmostEqual(esperado / 1000.0, 372.584, places=2)
        self.assertAlmostEqual(self.r.vu_equivalent_kn, 372.584, places=2)

    def test_the_section_limit_uses_the_equivalent_shear(self):
        # V_u,eq/(φ·b·d_v) = 372584/(0.9·350·510) = 2.319 ≤ 0.25·f'c = 7.0
        self.assertAlmostEqual(self.r.stress_demand_mpa, 2.3192, places=3)
        self.assertAlmostEqual(self.r.stress_limit_mpa, 7.0)
        self.assertTrue(self.r.section_ok)

    def test_transverse_reinforcement_for_torsion(self):
        # A_t/s = (T_u/φ)/(2·A_o·f_yt·cot θ) = 5e7/(2·113024·420) = 0.52665
        self.assertAlmostEqual(self.r.at_s_required, 0.526646, places=5)
        # (A_v + 2A_t)/s
        self.assertAlmostEqual(
            self.r.avt_s_required,
            self.r.av_s_required + 2 * self.r.at_s_required, places=9,
        )

    def test_adopted_spacing_and_provided_capacity(self):
        # A_b/s ≥ A_t/s + (A_v/s)/n → s = 71/0.80906 = 87.76 → 85 mm
        self.assertAlmostEqual(self.r.s_combined_required_mm, 87.756, places=2)
        self.assertAlmostEqual(self.r.s_adopted_mm, 85.0)
        # T_n = 2·A_o·A_b·f_yt·cot θ/s = 79.30 kN·m
        self.assertAlmostEqual(self.r.tn_provided_knm, 79.303, places=2)
        self.assertAlmostEqual(self.r.phi_tn_knm, 71.373, places=2)
        self.assertGreater(self.r.torsion_ratio, 1.0)

    def test_combined_longitudinal_requirement(self):
        # M_u/(φ_f·d_v) + cot θ·√[(V_u/φ_v − 0.5·V_s)² + (0.45·p_h·T_u/(2·A_o·φ))²]
        #   = 653595 + 182560 = 836155 N
        self.assertTrue(self.r.long_check_applies)
        self.assertAlmostEqual(self.r.long_demand_n, 836155.0, delta=10.0)
        self.assertFalse(self.r.long_reinf_ok)
        self.assertGreater(self.r.al_required_mm2, 0.0)

    def test_aashto_has_no_separate_minimum_longitudinal_steel(self):
        self.assertEqual(self.r.al_min_mm2, 0.0)

    def test_without_torsion_it_matches_the_plain_shear_design(self):
        comun = dict(
            vu_n=250e3, b_mm=350.0, h_mm=600.0, cover_mm=40.0, fc_mpa=28.0,
            fyt_mpa=420.0, stirrup_diameter_mm=9.52, stirrup_area_mm2=71.0,
            stirrup_legs=2, d_mm=540.0, a_mm=60.0,
        )
        con = AashtoBeamShearTorsionDesign(**comun).design()
        sin = AashtoBeamShearDesign(**comun).design()
        self.assertFalse(con.torsion_active)
        self.assertAlmostEqual(con.s_adopted_mm, sin.s_adopted_mm)
        self.assertAlmostEqual(con.phi_vn_kn, sin.phi_vn_kn)

    def test_compatibility_torsion_warns_that_aashto_does_not_redistribute(self):
        r = AashtoBeamShearTorsionDesign(
            vu_n=250e3, b_mm=350.0, h_mm=600.0, cover_mm=40.0, fc_mpa=28.0,
            fyt_mpa=420.0, stirrup_diameter_mm=9.52, stirrup_area_mm2=71.0,
            d_mm=540.0, a_mm=60.0, torsion_enabled=True, tu_nmm=45e6,
            torsion_type="COMPATIBILIDAD",
        ).design()
        self.assertFalse(r.redistributed)
        self.assertAlmostEqual(r.tu_design_knm, r.tu_knm)
        self.assertTrue(any("compatibilidad" in w.lower() for w in r.warnings))


class ContrasteEntreNormas(unittest.TestCase):
    """El sentido de las diferencias ACI ↔ AASHTO, como documentación viva."""

    def test_aashto_uses_a_higher_resistance_factor_for_shear(self):
        from core.shear import PHI_SHEAR as PHI_ACI
        self.assertAlmostEqual(PHI_ACI, 0.75)
        self.assertAlmostEqual(PHI_SHEAR, 0.90)

    def test_for_the_same_beam_the_concrete_contribution_is_comparable(self):
        # ACI con estribos: V_c = 0.17·√f'c·b·d
        # AASHTO simplificado: V_c = 0.166·√f'c·b·d_v
        # Los coeficientes casi coinciden; la diferencia real está en d vs d_v
        # y en φ, no en la fórmula.
        from core.shear import vc_one_way
        d, dv = 440.955, 415.896
        aci = vc_one_way(28.0, 1.0, 300.0, d)
        aashto = vc_nominal(28.0, 1.0, 300.0, dv)
        self.assertAlmostEqual(aashto / aci, (0.166 * dv) / (0.17 * d), places=6)
        self.assertLess(aashto, aci)          # d_v < d en esta sección
        self.assertGreater(PHI_SHEAR * aashto, 0.75 * aci)   # pero φ compensa

    def test_aashto_minimum_reinforcement_is_not_an_area_rule(self):
        from core.flexion import BeamSection
        comun = dict(
            mu_nmm=100e6, b_mm=300.0, h_mm=500.0, cover_mm=40.0,
            fc_mpa=28.0, fy_mpa=420.0, reinforcement=viga_3n6(),
        )
        aci = BeamSection(**comun).design()
        aashto = AashtoBeamSection(**comun).design()
        # ACI: A_s,min = max(0.25√f'c/f_y, 1.4/f_y)·b·d, un área directa.
        esperado_aci = max(
            0.25 * math.sqrt(28.0) / 420.0, 1.4 / 420.0
        ) * 300.0 * aci.d_mm / 100.0
        self.assertAlmostEqual(aci.as_min_cm2, esperado_aci, places=4)
        # AASHTO: el área sale de exigir M_r ≥ min(1.33·M_u, M_cr).
        self.assertNotAlmostEqual(aashto.as_min_cm2, aci.as_min_cm2, places=2)
        self.assertGreater(aashto.mcr_knm, 0.0)


if __name__ == "__main__":
    unittest.main()

"""Momento negativo: acero en la cara superior, compresión en la inferior.

Sección de referencia (la misma de `test_tsection.py`):

    b_w = 300 mm, h = 600 mm, recubrimiento 40 mm, estribo #3,
    f'c = 28 MPa, f_y = 420 MPa, 4 #8 (A_s = 2026.8 mm²), d = 537.78 mm
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
# Estudios recientes en un .ini temporal: los tests no tocan la configuración real.
os.environ.setdefault('BEAMCALC_SETTINGS', os.path.join(os.environ.get('TEMP', '.'), 'beamcalc-tests.ini'))

import unittest

from core.aashto.flexion import AashtoBeamSection
from core.aashto.shear import AashtoBeamShearDesign
from core.flexion import BeamSection
from core.section_geometry import RebarLayer, ReinforcementConfig, SectionShape

SECCION = dict(mu_nmm=300e6, b_mm=300.0, h_mm=600.0, cover_mm=40.0,
               fc_mpa=28.0, fy_mpa=420.0)
T_ANCHA = dict(section_shape=SectionShape.T, bf_mm=1200.0, hf_mm=100.0)


def armado():
    return ReinforcementConfig([RebarLayer(4, 25.4, 506.7)], stirrup_diameter_mm=9.52)


def aci(**extra):
    return BeamSection(**SECCION, reinforcement=armado(), **extra).design()


def aashto(**extra):
    return AashtoBeamSection(**SECCION, reinforcement=armado(), **extra).design()


class FlexionACI(unittest.TestCase):

    def test_a_rectangular_section_does_not_care_about_the_sign(self):
        # Rectangular y simétrica: invertir el momento sólo cambia de cara.
        pos, neg = aci(), aci(negative_moment=True)
        for campo in ("d_mm", "a_mm", "jd_mm", "phi_mn_knm", "as_required_cm2",
                      "as_min_cm2", "as_max_cm2", "status"):
            self.assertEqual(getattr(pos, campo), getattr(neg, campo), campo)
        self.assertTrue(neg.negative_moment)

    def test_a_t_in_negative_moment_resists_like_its_web(self):
        # Ala traccionada: compresión en el alma, rectangular de 300 mm.
        #   a = 2026.8·420/(23.8·300) = 119.2 mm ; φM_n = 366.3 kN·m
        rect, neg = aci(), aci(negative_moment=True, **T_ANCHA)
        self.assertAlmostEqual(neg.a_mm, rect.a_mm)
        self.assertAlmostEqual(neg.phi_mn_knm, rect.phi_mn_knm)
        self.assertFalse(neg.flanged_behaviour)
        self.assertLess(neg.phi_mn_knm, aci(**T_ANCHA).phi_mn_knm)
        # La geometría real se conserva para el dibujo y la torsión.
        self.assertIs(neg.section_shape, SectionShape.T)
        self.assertEqual(neg.bf_mm, 1200.0)

    def test_minimum_steel_in_a_continuous_beam_uses_the_web(self):
        neg = aci(negative_moment=True, **T_ANCHA)
        self.assertAlmostEqual(neg.as_min_cm2, aci().as_min_cm2)
        self.assertEqual(neg.as_min_width_mm, 300.0)

    def test_minimum_steel_in_a_cantilever_uses_min_bf_2bw(self):
        # §9.6.1.2: isostático con ala en tracción → min(1200, 600) = 600 mm,
        # el doble de b_w, así que A_s,mín se duplica: 2 · 5.38 = 10.76 cm².
        iso = aci(negative_moment=True, statically_determinate=True, **T_ANCHA)
        self.assertEqual(iso.as_min_width_mm, 600.0)
        self.assertAlmostEqual(iso.as_min_cm2, 2 * aci().as_min_cm2)

    def test_a_narrow_flange_limits_the_cantilever_width(self):
        # min(b_f = 450, 2·b_w = 600) = 450 mm
        iso = aci(negative_moment=True, statically_determinate=True,
                  section_shape=SectionShape.T, bf_mm=450.0, hf_mm=100.0)
        self.assertEqual(iso.as_min_width_mm, 450.0)

    def test_the_determinate_flag_is_ignored_in_positive_moment(self):
        self.assertEqual(aci(statically_determinate=True, **T_ANCHA).as_min_width_mm,
                         300.0)


class FlexionAASHTO(unittest.TestCase):

    def test_the_cracking_moment_uses_the_top_fiber(self):
        # S_sup = I_g / y_sup = 9225·10⁶ / 216.67 = 42.58·10⁶ mm³
        #   M_cr = 0.67 · 1.6 · 3.2807 · 42.577e6 = 149.7 kN·m
        neg = aashto(negative_moment=True, **T_ANCHA)
        self.assertAlmostEqual(neg.sc_mm3 / 1e6, 42.577, places=2)
        self.assertAlmostEqual(neg.mcr_knm, 149.74, places=1)

    def test_resistance_is_the_web_in_negative_moment(self):
        self.assertAlmostEqual(
            aashto(negative_moment=True, **T_ANCHA).phi_mn_knm,
            aashto().phi_mn_knm)

    def test_dv_uses_a_over_two_in_negative_moment(self):
        comun = dict(vu_n=180e3, b_mm=300.0, h_mm=600.0, cover_mm=40.0,
                     fc_mpa=28.0, fyt_mpa=420.0, stirrup_diameter_mm=9.52,
                     stirrup_area_mm2=71.0, stirrup_legs=2, lam=1.0,
                     d_mm=537.78, a_mm=40.0, **T_ANCHA)
        # d_e − a/2 = 517.8 > 0.9·d_e = 484.0: manda el brazo, y en negativo
        # se escribe con a/2 (compresión en el alma) y no con ȳ del ala.
        neg = AashtoBeamShearDesign(**comun, negative_moment=True).design()
        pos = AashtoBeamShearDesign(**comun).design()
        self.assertEqual(neg.dv_governing, "d_e − a/2")
        self.assertEqual(pos.dv_governing, "d_e − ȳ")


class Memoria(unittest.TestCase):

    def test_the_report_says_negative_and_uses_the_web(self):
        from core.design_code import DesignCode, beam_shear_design, flexure_design
        from core.project import ProjectInfo
        from core.report import generate_beam_report
        from core.units import UnitSystem
        f = flexure_design(DesignCode.ACI_318_19, reinforcement=armado(), **SECCION,
                           negative_moment=True, statically_determinate=True,
                           **T_ANCHA)
        v = beam_shear_design(
            DesignCode.ACI_318_19, vu_n=180e3, b_mm=300.0, h_mm=600.0,
            cover_mm=40.0, fc_mpa=28.0, fyt_mpa=420.0, stirrup_diameter_mm=9.52,
            stirrup_area_mm2=71.0, stirrup_legs=2, lam=1.0, d_mm=f.d_mm,
            section_shape=SectionShape.T, bf_mm=1200.0, hf_mm=100.0)
        html = generate_beam_report(flexion=f, shear=v, unit_system=UnitSystem.SI,
                                    info=ProjectInfo())
        self.assertIn("M_u^-", html)
        self.assertIn("ala traccionada", html)
        self.assertIn("§24.3.4", html)
        self.assertIn("menor entre $b_f$ y $2b_w$", html)
        # La derivación es la rectangular: nada del cálculo por partes.
        self.assertNotIn("A_{sf}", html)


class Interfaz(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from ui.main_window import MainWindow
        self.w = MainWindow()
        self.w.show()
        self.app.processEvents()
        self.addCleanup(self.w.close)
        self.p = self.w.beam_flex_inputs

    def test_only_the_beam_has_a_sign_selector(self):
        self.assertIsNotNone(self.p.sign_combo)
        self.assertIsNone(self.w.slab_flex_inputs.sign_combo)

    def test_the_sign_reaches_flexure_and_shear(self):
        self.p.sign_combo.setCurrentIndex(self.p.sign_combo.findData(True))
        self.app.processEvents()
        self.assertTrue(self.w.beam_flex_results.result.negative_moment)

    def test_the_cantilever_box_shows_only_when_it_matters(self):
        chk = self.p.determinate_check
        self.assertTrue(chk.isHidden())
        self.p.sign_combo.setCurrentIndex(self.p.sign_combo.findData(True))
        self.assertTrue(chk.isHidden())            # rectangular: no aplica
        self.p.shape_combo.setCurrentIndex(self.p.shape_combo.findData(SectionShape.T))
        self.assertFalse(chk.isHidden())

    def test_the_sign_survives_save_and_unit_change(self):
        from core.units import UnitSystem
        self.p.sign_combo.setCurrentIndex(self.p.sign_combo.findData(True))
        estado = self.p.get_state()
        self.assertTrue(estado["negative_moment"])
        self.w.unit_combo.setCurrentIndex(self.w.unit_combo.findData(UnitSystem.ENGLISH))
        self.app.processEvents()
        self.assertTrue(self.w.beam_flex_inputs.negative_moment())

    def test_an_older_study_opens_as_positive(self):
        self.p.sign_combo.setCurrentIndex(self.p.sign_combo.findData(True))
        estado = self.p.get_state()
        del estado["negative_moment"]
        self.p.set_state(estado)
        self.assertFalse(self.p.negative_moment())


if __name__ == "__main__":
    unittest.main()

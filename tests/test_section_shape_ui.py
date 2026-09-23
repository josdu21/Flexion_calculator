"""El selector de sección en la ventana real.

Comprueba que elegir T o L muestra los campos del ala, recalcula los cuatro
análisis, no toca a la losa —que siempre es una franja rectangular—, sobrevive
a un cambio de unidades y de normativa, y viaja en el archivo del estudio.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
# Estudios recientes en un .ini temporal: los tests no tocan la configuración real.
os.environ.setdefault('BEAMCALC_SETTINGS', os.path.join(os.environ.get('TEMP', '.'), 'beamcalc-tests.ini'))

from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from PyQt6.QtWidgets import QApplication

from core.design_code import DesignCode
from core.project import load_study
from core.section_geometry import SectionShape
from core.units import UnitSystem
from ui.main_window import MainWindow


class SelectorDeSeccion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.dialog_patch = patch(
            'ui.main_window.QMessageBox.critical',
            side_effect=lambda *args: self.fail(str(args[-1])),
        )
        self.dialog_patch.start()
        self.addCleanup(self.dialog_patch.stop)
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()
        self.addCleanup(self.window.close)
        self.panel = self.window.beam_flex_inputs

    def elegir(self, forma: SectionShape, bf=None, hf=None):
        combo = self.panel.shape_combo
        combo.setCurrentIndex(combo.findData(forma))
        if bf is not None:
            self.panel.bf_spinbox.setValue(bf)
        if hf is not None:
            self.panel.hf_spinbox.setValue(hf)
        self.app.processEvents()

    # ------------------------------------------------------------

    def test_the_beam_starts_rectangular(self):
        self.assertIs(self.panel.section_shape(), SectionShape.RECTANGULAR)
        self.assertIs(
            self.window.beam_flex_results.result.section_shape,
            SectionShape.RECTANGULAR,
        )

    def test_the_slab_has_no_section_selector(self):
        # La losa es una franja rectangular de 1 m: ofrecerle formas con ala
        # sería ofrecer algo que la aplicación no calcula.
        self.assertIsNone(self.window.slab_flex_inputs.shape_combo)
        self.assertIsNone(self.window.slab_flex_inputs.bf_spinbox)

    def test_the_flange_fields_appear_only_with_a_flange(self):
        # El campo vive dentro de su stepper: se mira si es visible respecto
        # del panel de geometría, que es lo que ve quien usa la pestaña.
        geo = self.panel.geometry
        self.assertFalse(self.panel.bf_spinbox.isVisibleTo(geo))
        self.elegir(SectionShape.T)
        self.assertTrue(self.panel.bf_spinbox.isVisibleTo(geo))
        self.assertTrue(self.panel.hf_spinbox.isVisibleTo(geo))
        self.elegir(SectionShape.RECTANGULAR)
        self.assertFalse(self.panel.hf_spinbox.isVisibleTo(geo))

    def test_the_width_label_says_web_when_there_is_a_flange(self):
        self.assertNotIn("alma", self.panel.b_label.text())
        self.elegir(SectionShape.T)
        self.assertIn("alma", self.panel.b_label.text())

    def test_choosing_a_t_recalculates_flexure(self):
        antes = self.window.beam_flex_results.result.phi_mn_knm
        self.elegir(SectionShape.T, bf=120.0, hf=15.0)   # cm
        despues = self.window.beam_flex_results.result
        self.assertIs(despues.section_shape, SectionShape.T)
        self.assertGreater(despues.phi_mn_knm, antes)

    def test_the_shear_tab_learns_the_shape_from_flexure(self):
        self.elegir(SectionShape.T, bf=120.0, hf=15.0)
        self.assertIs(self.window.beam_shear_inputs.section_shape, SectionShape.T)
        self.assertIn("alma", self.window.beam_shear_inputs.shape_note.text())

    def test_the_flange_reaches_torsion(self):
        self.window.beam_shear_inputs.torsion_group.setChecked(True)
        self.app.processEvents()
        rect = self.window.beam_shear_results.result.acp_mm2
        self.elegir(SectionShape.T, bf=120.0, hf=15.0)
        con_ala = self.window.beam_shear_results.result.acp_mm2
        self.assertGreater(con_ala, rect)

    def test_the_slab_is_untouched_by_the_beam_shape(self):
        antes = self.window.slab_flex_results.result.phi_mn_knm
        self.elegir(SectionShape.T, bf=120.0, hf=15.0)
        self.assertAlmostEqual(
            self.window.slab_flex_results.result.phi_mn_knm, antes
        )

    def test_the_shape_survives_a_unit_change(self):
        self.elegir(SectionShape.T, bf=120.0, hf=15.0)
        capacidad = self.window.beam_flex_results.result.phi_mn_knm
        combo = self.window.unit_combo
        combo.setCurrentIndex(combo.findData(UnitSystem.ENGLISH))
        self.app.processEvents()
        self.assertIs(self.window.beam_flex_inputs.section_shape(), SectionShape.T)
        # 120 cm y 15 cm convertidos a pulgadas, redondeo de la caja aparte.
        self.assertAlmostEqual(
            self.window.beam_flex_inputs.bf_spinbox.value(), 47.24, places=1
        )
        # La capacidad se mantiene salvo por el redondeo de las cajas al
        # reexpresar cada dato en la unidad nueva, que ya ocurría antes de que
        # hubiera secciones con ala. Lo que importa acá es que el ala no se
        # pierde: sin ella la capacidad caería mucho más que un 2 %.
        self.assertAlmostEqual(
            self.window.beam_flex_results.result.phi_mn_knm, capacidad,
            delta=capacidad * 0.02,
        )

    def test_the_shape_survives_a_code_change(self):
        self.elegir(SectionShape.T, bf=120.0, hf=15.0)
        combo = self.window.code_combo
        combo.setCurrentIndex(combo.findData(DesignCode.AASHTO_LRFD_2020))
        self.app.processEvents()
        resultado = self.window.beam_flex_results.result
        self.assertIs(resultado.section_shape, SectionShape.T)
        # Y el M_cr de AASHTO usa el módulo de sección de la T, no b·h²/6.
        self.assertGreater(
            resultado.sc_mm3,
            resultado.b_mm * resultado.h_mm ** 2 / 6.0,
        )

    def test_the_shape_makes_a_round_trip_through_the_study_file(self):
        carpeta = Path(tempfile.gettempdir()) / f'seccion-{uuid4().hex}'
        carpeta.mkdir()
        self.addCleanup(shutil.rmtree, carpeta, True)
        destino = carpeta / 'estudio.json'

        self.elegir(SectionShape.L, bf=90.0, hf=12.0)
        with patch('ui.main_window.QFileDialog.getSaveFileName',
                   return_value=(str(destino), '')):
            self.window._save_study()

        estudio = load_study(destino)
        self.assertEqual(
            estudio.panels['viga_flexion']['section_shape'], 'L'
        )

        self.elegir(SectionShape.RECTANGULAR)
        with patch('ui.main_window.QFileDialog.getOpenFileName',
                   return_value=(str(destino), '')):
            self.window._open_study()
        self.app.processEvents()
        self.assertIs(self.window.beam_flex_inputs.section_shape(), SectionShape.L)
        self.assertAlmostEqual(self.window.beam_flex_inputs.bf_spinbox.value(), 90.0)

    def test_a_file_without_a_shape_opens_as_rectangular(self):
        # Los estudios guardados antes de la v3 no traen forma: eran todos
        # rectangulares, y abrirlos no debe dejar puesta la forma anterior.
        self.elegir(SectionShape.T, bf=120.0, hf=15.0)
        estado = self.window.beam_flex_inputs.get_state()
        del estado['section_shape']
        self.window.beam_flex_inputs.set_state(estado)
        self.app.processEvents()
        self.assertIs(
            self.window.beam_flex_inputs.section_shape(), SectionShape.RECTANGULAR
        )


if __name__ == '__main__':
    unittest.main()

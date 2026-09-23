"""Pantalla de inicio y pestaña de geometría compartida."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
# Estudios recientes en un .ini temporal: los tests no tocan la configuración real.
os.environ.setdefault('BEAMCALC_SETTINGS', os.path.join(os.environ.get('TEMP', '.'), 'beamcalc-tests.ini'))

import unittest

from PyQt6.QtWidgets import QApplication

from core.section_geometry import SectionShape
from ui.main_window import PAGE_HOME, PAGE_WORKSPACE, TAB_GEOMETRY, MainWindow


class Inicio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.w = MainWindow()
        self.w.show()
        self.app.processEvents()
        self.addCleanup(self.w.close)

    def test_the_app_starts_on_the_home_screen(self):
        self.assertEqual(self.w.pages.currentIndex(), PAGE_HOME)

    def test_each_card_opens_its_own_workspace(self):
        self.w.beam_card.click()
        self.assertEqual(self.w.pages.currentIndex(), PAGE_WORKSPACE)
        self.assertIs(self.w.element_stack.currentWidget(), self.w.beam_tabs)
        self.assertIn("Viga", self.w.context_label.text())
        self.w.home_button.click()
        self.assertEqual(self.w.pages.currentIndex(), PAGE_HOME)
        self.w.slab_card.click()
        self.assertIs(self.w.element_stack.currentWidget(), self.w.slab_tabs)
        self.assertIn("Losa", self.w.context_label.text())

    def test_the_workspace_opens_on_the_geometry_tab(self):
        self.w.beam_card.click()
        self.assertEqual(self.w.beam_tabs.currentIndex(), TAB_GEOMETRY)

    def test_project_fields_feed_the_report_title_block(self):
        self.w.project_edit.setText("Puente Norte")
        self.w.beam_name_edit.setText("V-12")
        self.assertEqual(self.w.project_info.project, "Puente Norte")
        self.assertEqual(self.w.project_info.beam_name, "V-12")
        self.w.beam_card.click()
        self.assertIn("V-12", self.w.element_title.text())
        self.assertIn("Puente Norte", self.w.context_label.text())


class Geometria(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.w = MainWindow()
        self.w.show()
        self.addCleanup(self.w.close)

    def test_flexure_and_shear_read_the_same_geometry(self):
        # Un solo campo: no hay copias que sincronizar.
        self.assertIs(self.w.beam_flex_inputs.h_spinbox,
                      self.w.beam_shear_inputs.h_spinbox)
        self.assertIs(self.w.beam_flex_inputs.h_spinbox,
                      self.w.beam_geometry.h_spinbox)

    def test_editing_geometry_recalculates_both_analyses(self):
        self.w.beam_geometry.h_spinbox.setValue(70.0)   # cm
        self.assertAlmostEqual(self.w.beam_flex_results.result.h_mm, 700.0)
        self.assertAlmostEqual(self.w.beam_shear_results.result.h_mm, 700.0)

    def test_the_analysis_forms_no_longer_repeat_the_geometry(self):
        # La altura vive en la pestaña de geometría, no en la de flexión.
        g = self.w.beam_geometry
        self.assertFalse(self.w.beam_flex_inputs.isAncestorOf(g.h_spinbox))
        self.assertFalse(self.w.beam_shear_inputs.isAncestorOf(g.h_spinbox))
        self.assertTrue(g.isAncestorOf(g.h_spinbox))

    def test_the_shape_selector_lives_in_geometry(self):
        g = self.w.beam_geometry
        g.shape_combo.setCurrentIndex(g.shape_combo.findData(SectionShape.T))
        self.assertIs(self.w.beam_flex_results.result.section_shape, SectionShape.T)
        self.assertIsNone(self.w.slab_geometry.shape_combo)


if __name__ == "__main__":
    unittest.main()


class InicioYRecientes(unittest.TestCase):
    """Normativa segmentada y lista de estudios recientes del inicio."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        import shutil
        import tempfile
        from pathlib import Path
        from uuid import uuid4
        from PyQt6.QtCore import QSettings
        from ui.home_widgets import RecentStudies

        self.carpeta = Path(tempfile.gettempdir()) / f"recientes-{uuid4().hex}"
        self.carpeta.mkdir()
        self.addCleanup(shutil.rmtree, self.carpeta, True)
        self.w = MainWindow()
        # Registro propio y vacío para cada prueba.
        self.w.recent_studies = RecentStudies(QSettings(
            str(self.carpeta / "config.ini"), QSettings.Format.IniFormat))
        self.w._refresh_recent()
        self.w.show()
        self.addCleanup(self.w.close)

    def _guardar(self, nombre):
        from unittest.mock import patch
        ruta = str(self.carpeta / nombre)
        with patch('ui.main_window.QFileDialog.getSaveFileName',
                   return_value=(ruta, '')):
            self.w._save_study()
        return ruta

    def test_the_code_selector_drives_the_code(self):
        from core.design_code import DesignCode
        aashto = [b for b in self.w.code_selector.buttons() if "AASHTO" in b.text()][0]
        aashto.click()
        self.assertEqual(self.w.current_code, DesignCode.AASHTO_LRFD_2020)
        # Y a la inversa: un cambio desde el combo (p. ej. al abrir) se refleja.
        self.w.code_combo.setCurrentIndex(
            self.w.code_combo.findData(DesignCode.ACI_318_19))
        self.assertEqual(self.w.code_selector.value(), DesignCode.ACI_318_19)

    def test_the_list_starts_empty_with_a_hint(self):
        self.assertTrue(self.w.recent_table.isHidden())
        self.assertFalse(self.w.recent_empty.isHidden())

    def test_saving_adds_the_study_on_top(self):
        self.w.project_edit.setText("Edificio Norte")
        self._guardar("a.json")
        self.w.project_edit.setText("Nave industrial")
        self._guardar("b.json")
        tabla = self.w.recent_table
        self.assertEqual(tabla.rowCount(), 2)
        self.assertEqual(tabla.item(0, 0).text(), "Nave industrial")
        self.assertEqual(tabla.item(0, 2).text(), "ACI 318-19")
        self.assertEqual(tabla.item(0, 3).text(), "Hoy")
        self.assertIn("Viga V-1", tabla.item(0, 1).text())

    def test_saving_the_same_file_twice_does_not_duplicate_it(self):
        self._guardar("a.json")
        self._guardar("a.json")
        self.assertEqual(self.w.recent_table.rowCount(), 1)

    def test_activating_a_row_opens_that_study(self):
        self.w.project_edit.setText("Puente Arroyo Seco")
        ruta = self._guardar("puente.json")
        self.w.project_edit.setText("Otro")
        self.w._on_recent_activated(self.w.recent_table.item(0, 0))
        self.assertEqual(self.w.project_info.project, "Puente Arroyo Seco")
        self.assertEqual(self.w.current_path, ruta)

    def test_a_deleted_file_disappears_from_the_list(self):
        import os
        ruta = self._guardar("borrar.json")
        os.remove(ruta)
        self.w._refresh_recent()
        self.assertEqual(self.w.recent_table.rowCount(), 0)

    def test_relative_dates(self):
        from datetime import date
        from ui.home_widgets import relative_date
        hoy = date(2026, 9, 23)
        self.assertEqual(relative_date("2026-09-23T10:00:00", hoy), "Hoy")
        self.assertEqual(relative_date("2026-09-22T10:00:00", hoy), "Ayer")
        self.assertEqual(relative_date("2026-09-18T10:00:00", hoy), "18 sep")
        self.assertEqual(relative_date("2025-01-05T10:00:00", hoy), "5 ene 2025")


class PestañaGeometria(unittest.TestCase):
    """Mosaicos de forma, franja de propiedades y cabecera del elemento."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.w = MainWindow()
        self.w.show()
        self.addCleanup(self.w.close)
        self.w.beam_card.click()
        self.g = self.w.beam_geometry

    def _t_80x12(self):
        self.g.shape_buttons[SectionShape.T].click()
        self.g.bf_spinbox.setValue(80.0)
        self.g.hf_spinbox.setValue(12.0)

    def test_the_tiles_choose_the_shape(self):
        self.g.shape_buttons[SectionShape.L].click()
        self.assertIs(self.g.section_shape(), SectionShape.L)
        self.assertIs(self.w.beam_flex_results.result.section_shape, SectionShape.L)

    def test_the_header_tag_follows_the_shape(self):
        self.assertEqual(self.w.shape_tag.text(), "Rectangular")
        self.g.shape_buttons[SectionShape.T].click()
        self.assertEqual(self.w.shape_tag.text(), "Sección T")

    def test_the_properties_strip_matches_a_hand_calculation(self):
        # T de b_f = 80, h_f = 12 sobre alma 30 × 50 (cm):
        #   A_g = 80·12 + 30·38 = 2 100 cm²
        #   ȳ   = (960·6 + 1140·31)/2100 = 19,6 cm
        #   E_c = 4700·√28 = 24 870 MPa (ACI 318-19 §19.2.2.1)
        self._t_80x12()
        texto = lambda k: self.g._props[k].text()
        self.assertTrue(texto("ag").startswith("2.100"))
        self.assertTrue(texto("yc").startswith("19,6"))
        self.assertTrue(texto("ec").startswith("24.870"))
        self.assertEqual(texto("b1"), "0,850")

    def test_ec_follows_the_design_code(self):
        from core.design_code import DesignCode
        self.w.code_combo.setCurrentIndex(
            self.w.code_combo.findData(DesignCode.AASHTO_LRFD_2020))
        # AASHTO §5.4.2.4: 4800·√28 = 25 399 MPa
        self.assertTrue(self.g._props["ec"].text().startswith("25.399"))

    def test_continue_goes_to_flexure(self):
        from ui.main_window import TAB_FLEXURE
        self.g.continue_requested.emit()
        self.assertEqual(self.w.beam_tabs.currentIndex(), TAB_FLEXURE)

    def test_the_stepper_buttons_change_the_value(self):
        antes = self.g.h_spinbox.value()
        self.g.h_spinbox.stepUp()
        self.assertGreater(self.g.h_spinbox.value(), antes)

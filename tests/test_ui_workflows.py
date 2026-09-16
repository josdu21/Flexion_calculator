"""Regresiones de los flujos de escritorio; ejecutar con unittest discover."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QTabWidget, QScrollArea

from core.flexion import BeamSection
from core.shear import SlabShearCheck
from core.torsion import BeamShearTorsionDesign
from core.units import UnitSystem
from ui.main_window import MainWindow


class InterfaceWorkflows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')
        # El backend offscreen de Qt en Windows no busca las fuentes del sistema.
        for name in ('segoeui.ttf', 'seguisb.ttf', 'seguisym.ttf', 'consola.ttf'):
            font = Path('C:/Windows/Fonts') / name
            if font.exists():
                QFontDatabase.addApplicationFont(str(font))

    def setUp(self):
        self.dialog_patch = patch('ui.main_window.QMessageBox.critical', side_effect=lambda *args: self.fail(str(args[-1])))
        self.dialog_patch.start()
        self.addCleanup(self.dialog_patch.stop)
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_navigation_and_calculations_in_every_unit_system(self):
        w = self.window
        self.assertEqual(len(w.findChildren(QTabWidget)), 1)
        contexts = ((True, True), (True, False), (False, True), (False, False))
        analyses = (
            (w.beam_flex_inputs, w.beam_flex_results, lambda v: BeamSection(**v).design()),
            (w.beam_shear_inputs, w.beam_shear_results, lambda v: BeamShearTorsionDesign(**v).design()),
            (w.slab_flex_inputs, w.slab_flex_results, lambda v: BeamSection(**v).design()),
            (w.slab_shear_inputs, w.slab_shear_results, lambda v: SlabShearCheck(**v).check()),
        )
        for system in UnitSystem:
            w.unit_combo.setCurrentIndex(w.unit_combo.findData(system))
            for index, (inputs, results, calculate) in enumerate(analyses):
                w.tabs.setCurrentIndex(index)
                self.app.processEvents()
                self.assertEqual(w._active_context(), contexts[index])
                self.assertEqual(results.result, calculate(inputs.get_values()))
                self.assertIn(w.tabs.tabText(index), w.report_button.toolTip())
            # Las conexiones se renuevan después de reconstruir los campos.
            w.beam_flex_inputs.h_spinbox.setValue(25)
            self.assertEqual(w.beam_shear_inputs.h_spinbox.value(), 25)

    def test_shared_section_is_bidirectional_and_elements_stay_independent(self):
        w = self.window
        slab_height = w.slab_flex_inputs.h_spinbox.value()
        w.beam_flex_inputs.h_spinbox.setValue(62)
        self.assertEqual(w.beam_shear_inputs.h_spinbox.value(), 62)
        self.assertEqual(w.beam_shear_results.result.h_mm, 620)
        w.beam_shear_inputs.fc_spinbox.setValue(35)
        self.assertEqual(w.beam_flex_inputs.fc_spinbox.value(), 35)
        self.assertEqual(w.beam_flex_results.result.fc_mpa, 35)
        self.assertEqual(w.slab_flex_inputs.h_spinbox.value(), slab_height)
        w.slab_shear_inputs.h_spinbox.setValue(22)
        self.assertEqual(w.slab_flex_inputs.h_spinbox.value(), 22)
        self.assertEqual(w.beam_flex_inputs.h_spinbox.value(), 62)

    def test_reinforcement_and_torsion_recalculate_automatically(self):
        w = self.window
        previous = w.beam_flex_results.result.as_provided_cm2
        w.beam_flex_inputs.layer_bar_spins[0].setValue(5)
        self.assertGreater(w.beam_flex_results.result.as_provided_cm2, previous)
        w.tabs.setCurrentIndex(1)
        inputs, results = w.beam_shear_inputs, w.beam_shear_results
        self.assertTrue(inputs.torsion_options.isHidden())
        self.assertTrue(results.torsion_details.isHidden())
        inputs.torsion_group.setChecked(True)
        self.assertFalse(inputs.torsion_options.isHidden())
        self.assertTrue(results.result.torsion_active)
        self.assertFalse(results.torsion_details.isHidden())
        inputs.torsion_type_combo.setCurrentIndex(1)
        self.assertEqual(results.result.torsion_type, 'COMPATIBILIDAD')
        inputs.torsion_group.setChecked(False)
        self.assertFalse(results.result.torsion_active)
        self.assertTrue(results.torsion_details.isHidden())

    def test_details_are_keyboard_accessible(self):
        details = self.window.beam_flex_results.details
        self.assertTrue(details.content.isHidden())
        details.toggle.setFocus()
        QTest.keyClick(details.toggle, Qt.Key.Key_Space)
        self.assertFalse(details.content.isHidden())
        QTest.keyClick(details.toggle, Qt.Key.Key_Space)
        self.assertTrue(details.content.isHidden())

    def test_torsion_can_be_found_and_enabled_without_scrolling(self):
        w = self.window
        w.resize(960, 640)
        w.tabs.setCurrentIndex(1)
        for system in UnitSystem:
            w.unit_combo.setCurrentIndex(w.unit_combo.findData(system))
            inputs = w.beam_shear_inputs
            inputs.torsion_group.setChecked(False)
            inputs.form_scroll.verticalScrollBar().setValue(0)
            for _ in range(4):
                self.app.processEvents()
            group = inputs.torsion_group
            viewport = inputs.form_scroll.viewport()
            position = group.mapTo(viewport, QPoint(0, 0))
            self.assertGreaterEqual(position.y(), 0)
            self.assertLess(position.y() + group.height(), viewport.height())
            self.assertFalse(inputs.torsion_hint.isHidden())
            group.setFocus()
            QTest.keyClick(group, Qt.Key.Key_Space)
            self.app.processEvents()
            self.assertTrue(group.isChecked())
            self.assertTrue(inputs.tu_spinbox.isVisible())
            self.assertTrue(inputs.tu_spinbox.isEnabled())
            self.assertTrue(w.beam_shear_results.result.torsion_active)
            self.assertTrue(inputs.torsion_hint.isHidden())

    def test_small_window_keeps_expanded_forms_accessible(self):
        w = self.window
        w.resize(960, 640)
        w.beam_shear_inputs.torsion_group.setChecked(True)
        for results in (w.beam_flex_results, w.slab_flex_results,
                        w.beam_shear_results, w.slab_shear_results):
            results.details.toggle.setChecked(True)
        w.beam_shear_results.torsion_details.toggle.setChecked(True)
        for index in range(4):
            w.tabs.setCurrentIndex(index)
            for _ in range(4):
                self.app.processEvents()
            self.assertEqual(w.width(), 960)
            for scroll in w.tabs.currentWidget().findChildren(QScrollArea):
                self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
                self.assertLessEqual(scroll.widget().minimumSizeHint().width(),
                                     scroll.viewport().width())

    def test_export_uses_active_analysis_and_cancel_does_nothing(self):
        w = self.window
        # TemporaryDirectory usa modo 0700, que en algunos entornos aislados de
        # Windows produce una ACL inaccesible para el mismo proceso de prueba.
        folder = Path(tempfile.gettempdir()) / f'beam-calculator-{uuid4().hex}'
        folder.mkdir()
        try:
            for index in range(4):
                w.tabs.setCurrentIndex(index)
                destination = folder / f'report_{index}.html'
                with patch('ui.main_window.QFileDialog.getSaveFileName', return_value=(str(destination), '')), \
                     patch('ui.main_window.webbrowser.open') as browser:
                    w._export_report()
                self.assertTrue(destination.exists())
                self.assertIn('<html', destination.read_text(encoding='utf-8').lower())
                browser.assert_called_once()
            with patch('ui.main_window.QFileDialog.getSaveFileName', return_value=('', '')), \
                 patch('ui.main_window.webbrowser.open') as browser:
                w._export_report()
                browser.assert_not_called()
            self.assertEqual(len(list(folder.iterdir())), 4)
        finally:
            shutil.rmtree(folder)


if __name__ == '__main__':
    unittest.main()

"""Guardado y apertura del estudio, y metadatos del cajetín en la memoria."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from PyQt6.QtWidgets import QApplication

from core.project import ProjectInfo, Study, StudyFileError, load_study, save_study
from core.units import UnitSystem
from ui.main_window import MainWindow


class StudyFile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = Path(tempfile.gettempdir()) / f'estudio-{uuid4().hex}'
        self.folder.mkdir()
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.window = MainWindow()
        self.addCleanup(self.window.deleteLater)
        self.addCleanup(self.window.close)

    def _save_to(self, path):
        with patch('ui.main_window.QFileDialog.getSaveFileName',
                   return_value=(str(path), '')):
            self.window._save_study()

    def _open_from(self, path):
        with patch('ui.main_window.QFileDialog.getOpenFileName',
                   return_value=(str(path), '')):
            self.window._open_study()

    def test_round_trip_restores_every_panel(self):
        w = self.window
        w.project_info = ProjectInfo(
            project="Edificio Centro", designer="JMD", reviewer="ACI",
            revision="Rev. B", notes="Viga de borde", beam_name="V-201",
            slab_name="L-105")
        w.beam_flex_inputs.h_spinbox.setValue(62)
        w.beam_flex_inputs.layers_spin.setValue(2)
        w.beam_flex_inputs.layer_bar_spins[1].setValue(3)
        w.beam_shear_inputs.torsion_group.setChecked(True)
        w.beam_shear_inputs.vu_spinbox.setValue(210)
        w.slab_flex_inputs.h_spinbox.setValue(22)
        w.slab_shear_inputs.vu_spinbox.setValue(55)
        self.app.processEvents()

        esperado = {k: p.get_state() for k, p in w._panels().items()}
        destino = self.folder / "estudio.json"
        self._save_to(destino)
        self.assertTrue(destino.exists())

        # Se ensucia todo antes de reabrir, para que el archivo sea la fuente.
        w.project_info = ProjectInfo()
        w.beam_flex_inputs.h_spinbox.setValue(40)
        w.beam_flex_inputs.layers_spin.setValue(1)
        w.beam_shear_inputs.torsion_group.setChecked(False)
        w.slab_flex_inputs.h_spinbox.setValue(15)
        self.app.processEvents()

        self._open_from(destino)
        self.app.processEvents()

        self.assertEqual({k: p.get_state() for k, p in w._panels().items()}, esperado)
        self.assertEqual(w.project_info.project, "Edificio Centro")
        self.assertEqual(w.project_info.reviewer, "ACI")
        self.assertEqual(w.project_info.beam_name, "V-201")
        self.assertTrue(w.beam_shear_inputs.torsion_group.isChecked())
        self.assertIn("estudio.json", w.windowTitle())

    def test_study_saved_in_one_unit_system_opens_in_another(self):
        w = self.window
        w.beam_flex_inputs.h_spinbox.setValue(60)
        self.app.processEvents()
        altura_si = w.beam_flex_inputs.get_state()["h_mm"]

        destino = self.folder / "si.json"
        self._save_to(destino)

        w.unit_combo.setCurrentIndex(w.unit_combo.findData(UnitSystem.ENGLISH))
        self.app.processEvents()
        self._open_from(destino)
        self.app.processEvents()

        # Abrir restaura el sistema de unidades guardado y la geometría real.
        self.assertEqual(w.current_unit_system, UnitSystem.SI)
        self.assertAlmostEqual(w.beam_flex_inputs.get_state()["h_mm"], altura_si, places=3)

    def test_metadata_reaches_the_report(self):
        w = self.window
        w.project_info = ProjectInfo(
            project="Puente Río", designer="J. Duarte", reviewer="M. Pérez",
            revision="Rev. 02", notes="Revisar anclajes", beam_name="VP-3")
        destino = self.folder / "memoria.html"
        with patch('ui.main_window.QFileDialog.getSaveFileName',
                   return_value=(str(destino), '')), \
             patch('ui.main_window.webbrowser.open'):
            w.tabs.setCurrentIndex(0)
            w._export_report()
        html = destino.read_text(encoding='utf-8')
        for texto in ("Puente Río", "J. Duarte", "M. Pérez", "Rev. 02",
                      "Revisar anclajes", "VP-3"):
            self.assertIn(texto, html, f'falta "{texto}" en el cajetín')

    def test_free_text_is_escaped_in_the_report(self):
        w = self.window
        w.project_info = ProjectInfo(project='Obra <script>alert(1)</script>')
        destino = self.folder / "escape.html"
        with patch('ui.main_window.QFileDialog.getSaveFileName',
                   return_value=(str(destino), '')), \
             patch('ui.main_window.webbrowser.open'):
            w._export_report()
        html = destino.read_text(encoding='utf-8')
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_opening_a_foreign_file_reports_an_error(self):
        ajeno = self.folder / "otro.json"
        ajeno.write_text('{"algo": 1}', encoding='utf-8')
        with self.assertRaises(StudyFileError):
            load_study(ajeno)

        with patch('ui.main_window.QFileDialog.getOpenFileName',
                   return_value=(str(ajeno), '')), \
             patch('ui.main_window.QMessageBox.critical') as box:
            self.window._open_study()
        box.assert_called_once()

    def test_unknown_fields_in_the_file_are_ignored(self):
        destino = self.folder / "futuro.json"
        save_study(destino, Study(info=ProjectInfo(project="X")))
        import json
        data = json.loads(destino.read_text(encoding='utf-8'))
        data["cajetin"]["campo_nuevo"] = "algo"
        destino.write_text(json.dumps(data), encoding='utf-8')
        self.assertEqual(load_study(destino).info.project, "X")


if __name__ == '__main__':
    unittest.main()

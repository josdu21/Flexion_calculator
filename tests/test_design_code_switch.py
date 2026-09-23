"""El selector de normativa cambia de norma sin que se mezclen las dos.

Comprueba en la ventana real que elegir una norma recalcula los cuatro
análisis con su motor, que la memoria exportada queda rotulada con esa norma,
y que los campos propios de AASHTO aparecen sólo cuando corresponde.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
# Estudios recientes en un .ini temporal: los tests no tocan la configuración real.
os.environ.setdefault('BEAMCALC_SETTINGS', os.path.join(os.environ.get('TEMP', '.'), 'beamcalc-tests.ini'))

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import QApplication

from core.design_code import DesignCode, code_of, spec
from core.project import load_study
from core.units import UnitSystem
from ui.main_window import MainWindow


class SelectorDeNormativa(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')
        for name in ('segoeui.ttf', 'seguisb.ttf', 'seguisym.ttf', 'consola.ttf'):
            font = Path('C:/Windows/Fonts') / name
            if font.exists():
                QFontDatabase.addApplicationFont(str(font))

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

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def _elegir(self, code: DesignCode):
        w = self.window
        w.code_combo.setCurrentIndex(w.code_combo.findData(code))
        self.app.processEvents()

    def test_the_app_starts_on_aci(self):
        self.assertEqual(self.window.current_code, DesignCode.ACI_318_19)

    def test_every_code_recalculates_the_four_analyses(self):
        w = self.window
        analisis = (
            (w.beam_flex_results, w._beam_flex_design),
            (w.beam_shear_results, w._beam_shear_design),
            (w.slab_flex_results, w._slab_flex_design),
            (w.slab_shear_results, w._slab_shear_check),
        )
        for code in DesignCode:
            with self.subTest(code=code.value):
                self._elegir(code)
                self.assertEqual(w.current_code, code)
                for panel, calcular in analisis:
                    resultado = calcular()
                    # El panel muestra lo mismo que devuelve el motor...
                    self.assertEqual(panel.result, resultado)
                    # ...y ese resultado viene del motor de la norma elegida.
                    self.assertEqual(code_of(resultado), code)

    def test_switching_codes_actually_changes_the_numbers(self):
        w = self.window
        self._elegir(DesignCode.ACI_318_19)
        aci = w._slab_shear_check()
        self._elegir(DesignCode.AASHTO_LRFD_2020)
        aashto = w._slab_shear_check()
        # Fórmulas de V_c distintas: no puede dar lo mismo por accidente.
        self.assertNotAlmostEqual(aci.vc_kn, aashto.vc_kn, places=1)
        self.assertNotAlmostEqual(aci.phi_vc_kn, aashto.phi_vc_kn, places=1)

    def test_switching_back_restores_the_original_numbers(self):
        # Cambiar de norma y volver no debe dejar residuos de la otra.
        w = self.window
        antes = w._beam_flex_design()
        self._elegir(DesignCode.AASHTO_LRFD_2020)
        self._elegir(DesignCode.ACI_318_19)
        despues = w._beam_flex_design()
        self.assertEqual(antes, despues)

    def test_aashto_only_fields_appear_only_under_aashto(self):
        # Se pregunta por isHidden() y no por isVisible(): estos grupos viven
        # dentro de pestañas inactivas y de secciones plegables, así que
        # isVisible() mide el ancestro, no si el grupo se escondió a propósito.
        w = self.window
        grupos = (w.beam_flex_inputs.aashto_group,
                  w.slab_flex_inputs.aashto_group,
                  w.beam_flex_results.aashto_group,
                  w.beam_shear_results.aashto_group,
                  w.slab_shear_results.aashto_group)

        self._elegir(DesignCode.ACI_318_19)
        for grupo in grupos:
            self.assertTrue(grupo.isHidden())

        self._elegir(DesignCode.AASHTO_LRFD_2020)
        for grupo in grupos:
            self.assertFalse(grupo.isHidden())

        # Los paneles de cortante no ganan campos de entrada: el procedimiento
        # simplificado de §5.7.3.4.1 no pide ningún dato nuevo.
        for panel in (w.beam_shear_inputs, w.slab_shear_inputs):
            self.assertFalse(hasattr(panel, "aashto_group"))

    def test_the_shear_panel_relabels_the_depth_it_uses(self):
        # ACI usa d; AASHTO usa d_v. Mostrar el rótulo equivocado invitaría a
        # comparar dos números que no son la misma magnitud.
        w = self.window
        self._elegir(DesignCode.ACI_318_19)
        self.assertIn("d efectivo", w.beam_shear_results.d_caption.text())
        self._elegir(DesignCode.AASHTO_LRFD_2020)
        self.assertIn("dv", w.beam_shear_results.d_caption.text())

    def test_the_code_survives_a_unit_change(self):
        w = self.window
        self._elegir(DesignCode.AASHTO_LRFD_2020)
        w.beam_flex_inputs.ms_spinbox.setValue(120.0)
        self.app.processEvents()

        w.unit_combo.setCurrentIndex(w.unit_combo.findData(UnitSystem.MKS))
        self.app.processEvents()

        self.assertEqual(w.current_code, DesignCode.AASHTO_LRFD_2020)
        self.assertFalse(w.beam_flex_inputs.aashto_group.isHidden())
        self.assertEqual(
            code_of(w._beam_flex_design()), DesignCode.AASHTO_LRFD_2020
        )
        # 120 kN·m expresados en tonf·m; el dato no se pierde al reconstruir.
        self.assertAlmostEqual(
            w.beam_flex_inputs.ms_spinbox.value(), 120.0 / 9.80665, places=2
        )

    def test_the_exported_report_names_the_active_code(self):
        w = self.window
        for code in DesignCode:
            with self.subTest(code=code.value):
                self._elegir(code)
                for indice in (0, 2):     # viga y losa
                    w.select_analysis(indice)
                    with tempfile.TemporaryDirectory() as tmp:
                        destino = Path(tmp) / "memoria.html"
                        with patch(
                            'ui.main_window.QFileDialog.getSaveFileName',
                            return_value=(str(destino), ''),
                        ), patch('ui.main_window.webbrowser.open'):
                            w._export_report()
                        html = destino.read_text(encoding='utf-8')
                    self.assertIn(
                        f'<span class="label">Norma:</span><span>'
                        f'{spec(code).label}</span>',
                        html,
                    )
                    self.assertIn(spec(code).full_name, html)
                    # Y no puede colarse la otra norma en el cajetín.
                    otra = next(c for c in DesignCode if c is not code)
                    self.assertNotIn(
                        f'<span class="label">Norma:</span><span>'
                        f'{spec(otra).label}</span>',
                        html,
                    )

    def test_the_code_round_trips_through_the_study_file(self):
        w = self.window
        self._elegir(DesignCode.AASHTO_LRFD_2020)
        w.beam_flex_inputs.ms_spinbox.setValue(95.0)
        w.beam_flex_inputs.exposure_combo.setCurrentIndex(1)   # clase 2
        self.app.processEvents()

        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "estudio.json"
            with patch('ui.main_window.QFileDialog.getSaveFileName',
                       return_value=(str(destino), '')):
                w._save_study()
            self.assertEqual(
                load_study(destino).code, DesignCode.AASHTO_LRFD_2020
            )

            # Volver a ACI y reabrir debe devolver la norma guardada.
            self._elegir(DesignCode.ACI_318_19)
            with patch('ui.main_window.QFileDialog.getOpenFileName',
                       return_value=(str(destino), '')):
                w._open_study()
            self.app.processEvents()

        self.assertEqual(w.current_code, DesignCode.AASHTO_LRFD_2020)
        self.assertEqual(
            w.code_combo.currentData(), DesignCode.AASHTO_LRFD_2020
        )
        self.assertAlmostEqual(w.beam_flex_inputs.ms_spinbox.value(), 95.0)
        self.assertEqual(w.beam_flex_inputs.exposure_combo.currentData(), 2)


if __name__ == "__main__":
    unittest.main()

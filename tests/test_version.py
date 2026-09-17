"""La versión se declara en dos lugares; estas pruebas impiden que diverjan."""
import re
import unittest
from pathlib import Path

from core.version import APP_NAME, __version__

RAIZ = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


class Version(unittest.TestCase):
    def test_is_semantic(self):
        self.assertRegex(__version__, SEMVER)

    def test_build_file_matches_the_python_source(self):
        # packaging/version.txt la leen el .bat y el .iss, que no corren Python.
        texto = (RAIZ / "packaging" / "version.txt").read_text(encoding="utf-8")
        self.assertEqual(
            texto.strip(), __version__,
            "packaging/version.txt quedó desincronizado de core/version.py; "
            "usá packaging/bump_version.py para subir la versión.",
        )

    def test_changelog_documents_the_current_version(self):
        texto = (RAIZ / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn(
            f"## [{__version__}]", texto,
            f"Falta la entrada de la versión {__version__} en CHANGELOG.md.",
        )

    def test_installer_carries_the_app_name_and_a_fixed_appid(self):
        iss = (RAIZ / "packaging" / "installer.iss").read_text(encoding="utf-8")
        self.assertIn(f'#define AppName "{APP_NAME}"', iss)
        # El AppId es lo que enlaza una versión con la siguiente al actualizar.
        appid = re.search(r"^AppId=\{\{([0-9A-F-]{36})\}", iss, re.M)
        self.assertIsNotNone(appid, "El instalador no declara un AppId fijo.")
        # La comprobación de downgrade mira esa misma clave del registro.
        self.assertIn(appid.group(1), iss)

    def test_the_report_records_the_version_that_produced_it(self):
        # Trazabilidad: una memoria impresa debe decir con qué versión se calculó.
        from core.flexion import BeamSection
        from core.shear import SlabShearCheck
        from core.report import generate_slab_report
        from core.units import UnitSystem

        flexion = BeamSection(mu_nmm=25e6, b_mm=1000.0, h_mm=150.0, cover_mm=20.0,
                              fc_mpa=28.0, fy_mpa=420.0).design()
        cortante = SlabShearCheck(vu_n=30e3, b_mm=1000.0, h_mm=150.0,
                                  cover_mm=20.0, fc_mpa=28.0).check()
        html = generate_slab_report(flexion, cortante, UnitSystem.SI)
        self.assertIn(f"{APP_NAME} v{__version__}", html)

    def test_the_icon_exists_and_covers_the_usual_sizes(self):
        icono = RAIZ / "assets" / "icon.ico"
        self.assertTrue(icono.is_file(), "Falta assets/icon.ico")
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow no está instalado")
        with Image.open(icono) as im:
            tamanos = {s[0] for s in im.info.get("sizes", [])}
        for esperado in (16, 32, 48, 256):
            self.assertIn(esperado, tamanos, f"El ícono no trae {esperado}px")


if __name__ == "__main__":
    unittest.main()

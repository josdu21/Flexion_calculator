"""El registro de normas despacha al motor correcto y no pierde datos.

Las listas de claves de `core/design_code.py` están escritas a mano para que se
lean; estas pruebas son las que impiden que se desincronicen de las firmas
reales de los motores.
"""
import inspect
import unittest

from core.design_code import (
    SPECS,
    DesignCode,
    beam_shear_design,
    code_of,
    flexure_design,
    slab_shear_check,
    spec,
)


def _parametros(cls) -> set:
    firma = inspect.signature(cls.__init__)
    return {n for n in firma.parameters if n != "self"}


def _obligatorios(cls) -> set:
    firma = inspect.signature(cls.__init__)
    return {
        n for n, p in firma.parameters.items()
        if n != "self" and p.default is inspect.Parameter.empty
    }


# Datos de una viga y una losa, en el superconjunto que producen los paneles.
VIGA_FLEXION = dict(
    mu_nmm=150e6, b_mm=300.0, h_mm=500.0, cover_mm=40.0,
    fc_mpa=28.0, fy_mpa=420.0, db_assumed_mm=19.05,
    bar_spec="A615", exposure_class=1, ms_nmm=95e6, lam=1.0,
)
VIGA_CORTANTE = dict(
    vu_n=200e3, b_mm=300.0, h_mm=500.0, cover_mm=40.0, fc_mpa=28.0,
    fyt_mpa=420.0, stirrup_diameter_mm=9.52, stirrup_area_mm2=71.0,
    stirrup_legs=2, db_long_assumed_mm=19.05, lam=1.0, d_mm=440.0,
    torsion_enabled=False, tu_nmm=0.0, fy_long_mpa=420.0,
    torsion_type="EQUILIBRIO",
    a_mm=50.0, mu_nmm=150e6, as_long_mm2=852.0,
)
LOSA_CORTANTE = dict(
    vu_n=60e3, b_mm=1000.0, h_mm=200.0, cover_mm=20.0, fc_mpa=28.0,
    db_long_assumed_mm=12.7, lam=1.0, as_long_mm2=650.0, a_mm=15.0,
)


class ClavesDeclaradas(unittest.TestCase):
    """Cada clave declarada tiene que existir en el constructor del motor."""

    def test_the_declared_keys_exist_in_every_engine(self):
        for code, s in SPECS.items():
            for cls, keys, que in (
                (s.flexure_cls, s.flexure_keys, "flexión"),
                (s.beam_shear_cls, s.beam_shear_keys, "cortante de viga"),
                (s.slab_shear_cls, s.slab_shear_keys, "cortante de losa"),
            ):
                sobrantes = keys - _parametros(cls)
                self.assertFalse(
                    sobrantes,
                    f"{code.value} ({que}): {cls.__name__} no acepta {sobrantes}",
                )

    def test_no_required_parameter_is_left_out(self):
        # Si un motor gana un parámetro obligatorio y nadie actualiza la lista,
        # el despacho reventaría en runtime: que falle acá en su lugar.
        for code, s in SPECS.items():
            for cls, keys, que in (
                (s.flexure_cls, s.flexure_keys, "flexión"),
                (s.beam_shear_cls, s.beam_shear_keys, "cortante de viga"),
                (s.slab_shear_cls, s.slab_shear_keys, "cortante de losa"),
            ):
                faltantes = _obligatorios(cls) - keys
                self.assertFalse(
                    faltantes,
                    f"{code.value} ({que}): falta declarar {faltantes}",
                )

    def test_every_code_declares_a_distinct_label(self):
        etiquetas = [s.label for s in SPECS.values()]
        self.assertEqual(len(etiquetas), len(set(etiquetas)))


class Despacho(unittest.TestCase):
    """El despacho produce un resultado de la norma pedida, en las dos."""

    def test_each_code_gets_its_own_engine(self):
        for code in DesignCode:
            with self.subTest(code=code.value):
                flexion = flexure_design(code, **VIGA_FLEXION)
                cortante = beam_shear_design(code, **VIGA_CORTANTE)
                losa = slab_shear_check(code, **LOSA_CORTANTE)
                for resultado in (flexion, cortante, losa):
                    self.assertEqual(code_of(resultado), code)
                    self.assertNotEqual(resultado.status, "ERROR")

    def test_extra_keys_do_not_reach_the_aci_engines(self):
        # Los paneles emiten el superconjunto; el constructor de ACI no acepta
        # bar_spec/exposure_class/ms_nmm y daría TypeError si el filtro fallara.
        propias_de_aashto = {"bar_spec", "exposure_class", "ms_nmm"}
        self.assertTrue(propias_de_aashto <= set(VIGA_FLEXION))
        resultado = flexure_design(DesignCode.ACI_318_19, **VIGA_FLEXION)
        self.assertNotEqual(resultado.status, "ERROR")

    def test_an_unknown_code_falls_back_instead_of_crashing(self):
        self.assertEqual(spec(None).code, DesignCode.ACI_318_19)


class ResultadosComparables(unittest.TestCase):
    """Los dos juegos de resultados exponen los mismos campos comunes.

    Es lo que permite que un solo panel de resultados sirva a las dos normas.
    """

    CAMPOS_FLEXION = {
        "b_mm", "h_mm", "cover_mm", "d_mm", "fc_mpa", "fy_mpa", "beta_1",
        "as_required_cm2", "as_min_cm2", "as_max_cm2", "as_provided_cm2",
        "rho_provided", "a_mm", "c_mm", "jd_mm", "compression_kn", "tension_kn",
        "phi_mn_knm", "mu_demand_knm", "status", "warnings", "reinforcement",
        "layer_y_positions_mm", "horizontal_spacing_mm", "vertical_spacing_mm",
    }
    CAMPOS_CORTANTE = {
        "b_mm", "h_mm", "d_mm", "fc_mpa", "vu_kn", "vc_kn", "phi_vc_kn",
        "s_adopted_mm", "s_max_mm", "vs_provided_kn", "phi_vn_kn",
        "regime", "status", "warnings",
    }
    CAMPOS_LOSA = {
        "b_mm", "h_mm", "d_mm", "fc_mpa", "vu_kn", "vc_kn", "phi_vc_kn",
        "ratio", "status", "warnings",
    }

    def test_both_codes_expose_the_shared_fields(self):
        for code in DesignCode:
            with self.subTest(code=code.value):
                for resultado, esperados in (
                    (flexure_design(code, **VIGA_FLEXION), self.CAMPOS_FLEXION),
                    (beam_shear_design(code, **VIGA_CORTANTE), self.CAMPOS_CORTANTE),
                    (slab_shear_check(code, **LOSA_CORTANTE), self.CAMPOS_LOSA),
                ):
                    faltantes = esperados - set(vars(resultado))
                    self.assertFalse(
                        faltantes,
                        f"{type(resultado).__name__} no expone {faltantes}",
                    )


if __name__ == "__main__":
    unittest.main()

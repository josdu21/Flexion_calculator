"""Identidad y versión de la aplicación (fuente de verdad en tiempo de ejecución).

Sigue versionado semántico (https://semver.org):

- **mayor**: cambia un resultado de ingeniería o rompe archivos guardados;
  obliga a re-revisar lo calculado con versiones anteriores.
- **menor**: funciones nuevas que no alteran resultados previos.
- **parche**: correcciones que no cambian ningún número de salida.

`packaging/version.txt` repite este valor para el build y el instalador, que
no ejecutan Python. `packaging/bump_version.py` actualiza ambos a la vez y
`tests/test_version.py` falla si se desincronizan.
"""

APP_NAME = "Beam Calculator"
APP_TAGLINE = "Diseño de refuerzo — ACI 318-19 y AASHTO LRFD 2020"
PUBLISHER = "Jose Manuel Duarte"

__version__ = "2.1.0"

# packaging/

Archivos para distribución, build de ejecutables e instalación local.

## Para el usuario final (Linux)

| Archivo | Para qué sirve |
|---|---|
| `ejecutar.sh` | Lanzador. Detecta si PyQt6 está instalado; si no, ofrece instalarlo y arranca la GUI. |
| `instalar.sh` | Instala PyQt6 desde el gestor de paquetes del sistema (pacman/apt/yum). |

Uso:
```bash
./packaging/instalar.sh   # solo una vez
./packaging/ejecutar.sh   # cada vez que quieras abrir la app
```

## Para build de Windows (Nuitka + instalador)

| Archivo | Para qué sirve |
|---|---|
| `build_nuitka.bat` | Script de Windows: instala dependencias y genera `distro\BeamCalculator\BeamCalculator.exe` (carpeta standalone con Nuitka). |
| `installer.iss` | Script de Inno Setup: empaqueta esa carpeta en `BeamCalculator-Setup-<version>.exe`. |
| `version.txt` | Versión de la app (una línea, ej. `1.0.0`), usada por ambos scripts. |

Requiere **Inno Setup** instalado aparte (no es un paquete de pip):
descargalo de https://jrsoftware.org/isdl.php o instalalo con
`choco install innosetup`.

Uso en Windows (con Python ya instalado):
```cmd
packaging\build_nuitka.bat
iscc packaging\installer.iss
```

El instalador queda en `distro\BeamCalculator-Setup-<version>.exe`. Al
ejecutarlo, la app se instala en Program Files con acceso desde el menú
Inicio (y, opcionalmente, un ícono en el escritorio), con desinstalador
registrado en "Aplicaciones".

Si más adelante agregas un ícono en `assets\icon.ico`, ambos scripts lo
toman automáticamente en el siguiente build — no hace falta editarlos.

## Build automático (CI)

El workflow `.github/workflows/build-release.yml` corre en cada push de un
tag `v*` y genera el `.exe` para Windows automáticamente, publicándolo
en la sección Releases del repo.

Para crear una release:
```bash
git tag v1.0.0
git push --tags
```

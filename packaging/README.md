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

## Para build de Windows .exe

| Archivo | Para qué sirve |
|---|---|
| `flexion_calculator.spec` | Configuración de PyInstaller (incluye exclusiones para reducir tamaño). |
| `build.bat` | Script de Windows: instala dependencias y genera `dist\FlexionCalculator.exe`. |

Uso en Windows (con Python ya instalado):
```cmd
packaging\build.bat
```

El binario portable queda en `dist\FlexionCalculator.exe` (~80 MB).
Copialo a cualquier máquina Windows y ejecutalo — no requiere instalación.

## Build automático (CI)

El workflow `.github/workflows/build-release.yml` corre en cada push de un
tag `v*` y genera el `.exe` para Windows automáticamente, publicándolo
en la sección Releases del repo.

Para crear una release:
```bash
git tag v1.0.0
git push --tags
```

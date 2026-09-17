; Inno Setup script para Beam Calculator
; Compilar con: iscc packaging\installer.iss
; Requiere el build standalone de Nuitka en distro\BeamCalculator
; (correr packaging\build_nuitka.bat primero).

#define VersionFile FileOpen("version.txt")
#define AppVersion Trim(FileRead(VersionFile))
#expr FileClose(VersionFile)

#define AppName "Beam Calculator"
#define ExeName "BeamCalculator.exe"

[Setup]
; AppId fijo: es lo que enlaza una versión con la siguiente. NO cambiarlo nunca,
; o cada versión se instalaría por separado en vez de actualizar la anterior.
AppId={{8E6A1F3C-5B92-4D27-9C41-7A0E3D5B8F64}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Jose Manuel Duarte
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\BeamCalculator
DefaultGroupName={#AppName}
OutputBaseFilename=BeamCalculator-Setup-{#AppVersion}
OutputDir=..\distro
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#ExeName}
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
; Actualización en sitio: reusa la carpeta de la versión instalada y no vuelve
; a preguntar el destino.
UsePreviousAppDir=yes
UsePreviousTasks=yes
#if FileExists("..\assets\icon.ico")
SetupIconFile=..\assets\icon.ico
#endif

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\distro\BeamCalculator\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#ExeName}"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#ExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#ExeName}"; Description: "Ejecutar {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
// Debe coincidir con el AppId de [Setup]. Si alguna vez se cambia uno, cambiar
// el otro: es la clave del registro donde Inno Setup anota la versión instalada.
const
  ClaveDesinstalar =
    'Software\Microsoft\Windows\CurrentVersion\Uninstall\' +
    '{8E6A1F3C-5B92-4D27-9C41-7A0E3D5B8F64}_is1';

function EsDowngrade(): Boolean;
var
  Instalada: String;
begin
  Result := False;
  if RegQueryStringValue(HKA, ClaveDesinstalar, 'DisplayVersion', Instalada) then
    Result := CompareStr(Instalada, '{#AppVersion}') > 0;
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if EsDowngrade() then
    Result := MsgBox(
      'Ya hay instalada una versión más reciente de {#AppName}.' + #13#10 +
      '¿Instalar de todos modos la versión {#AppVersion}?',
      mbConfirmation, MB_YESNO) = IDYES;
end;

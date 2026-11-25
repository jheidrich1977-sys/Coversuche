; Bauanleitung für das Setup-Programm (Inno Setup).
; Wird automatisch von GitHub gebaut – siehe .github/workflows/windows-build.yml
;
; Das Setup
;   * installiert Coversuche (ohne Administratorrechte nur für den aktuellen
;     Benutzer, wahlweise für alle Benutzer),
;   * legt einen Startmenü-Eintrag (und auf Wunsch ein Desktop-Symbol) an,
;   * trägt auf Wunsch das Explorer-Kontextmenü ein,
;   * lässt sich unter "Einstellungen > Apps" wieder sauber entfernen.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6E2B8C4A-3F1D-4C7E-9B52-C0E5A1D7F3B9}
AppName=Coversuche
AppVersion={#AppVersion}
AppPublisher=Coversuche
DefaultDirName={autopf}\Coversuche
DefaultGroupName=Coversuche
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=Coversuche-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\Coversuche.exe
ChangesAssociations=yes

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "kontextmenue"; Description: "Coversuche ins Explorer-Kontextmenü (Rechtsklick) eintragen"; GroupDescription: "Zusätzliche Funktionen:"
Name: "desktopicon"; Description: "Symbol auf dem Desktop anlegen"; GroupDescription: "Zusätzliche Funktionen:"; Flags: unchecked

[Files]
Source: "..\dist\Coversuche\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Coversuche"; Filename: "{app}\Coversuche.exe"
Name: "{autodesktop}\Coversuche"; Filename: "{app}\Coversuche.exe"; Tasks: desktopicon

[Registry]
; ---- Rechtsklick auf eine MP3-Datei: Untermenü "Coversuche" ----
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.mp3\shell\Coversuche"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Coversuche"; Tasks: kontextmenue; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.mp3\shell\Coversuche"; ValueType: string; ValueName: "SubCommands"; ValueData: ""; Tasks: kontextmenue
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.mp3\shell\Coversuche"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\Coversuche.exe"",0"; Tasks: kontextmenue
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.mp3\shell\Coversuche"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: kontextmenue
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.mp3\shell\Coversuche\shell\1cover"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Cover suchen"; Tasks: kontextmenue
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.mp3\shell\Coversuche\shell\1cover"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: kontextmenue
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.mp3\shell\Coversuche\shell\1cover\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Coversuche.exe"" --cover ""%1"""; Tasks: kontextmenue
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.mp3\shell\Coversuche\shell\2tag"; ValueType: string; ValueName: "MUIVerb"; ValueData: "ID3-Tag bearbeiten"; Tasks: kontextmenue
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.mp3\shell\Coversuche\shell\2tag"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: kontextmenue
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.mp3\shell\Coversuche\shell\2tag\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Coversuche.exe"" --tag ""%1"""; Tasks: kontextmenue
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.mp3\shell\Coversuche\shell\3umbenennen"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Dateinamen aus ID3-Tag erstellen"; Tasks: kontextmenue
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.mp3\shell\Coversuche\shell\3umbenennen"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: kontextmenue
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.mp3\shell\Coversuche\shell\3umbenennen\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Coversuche.exe"" --umbenennen ""%1"""; Tasks: kontextmenue

; ---- Rechtsklick auf einen Ordner: gleiches Untermenü für alle MP3s darin ----
Root: HKA; Subkey: "Software\Classes\Directory\shell\Coversuche"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Coversuche"; Tasks: kontextmenue; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Directory\shell\Coversuche"; ValueType: string; ValueName: "SubCommands"; ValueData: ""; Tasks: kontextmenue
Root: HKA; Subkey: "Software\Classes\Directory\shell\Coversuche"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\Coversuche.exe"",0"; Tasks: kontextmenue
Root: HKA; Subkey: "Software\Classes\Directory\shell\Coversuche\shell\1cover"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Cover für alle MP3s suchen"; Tasks: kontextmenue
Root: HKA; Subkey: "Software\Classes\Directory\shell\Coversuche\shell\1cover\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Coversuche.exe"" --cover ""%1"""; Tasks: kontextmenue
Root: HKA; Subkey: "Software\Classes\Directory\shell\Coversuche\shell\2tag"; ValueType: string; ValueName: "MUIVerb"; ValueData: "ID3-Tag aller MP3s bearbeiten"; Tasks: kontextmenue
Root: HKA; Subkey: "Software\Classes\Directory\shell\Coversuche\shell\2tag\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Coversuche.exe"" --tag ""%1"""; Tasks: kontextmenue
Root: HKA; Subkey: "Software\Classes\Directory\shell\Coversuche\shell\3umbenennen"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Alle MP3s nach ID3-Tag umbenennen"; Tasks: kontextmenue
Root: HKA; Subkey: "Software\Classes\Directory\shell\Coversuche\shell\3umbenennen\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Coversuche.exe"" --umbenennen ""%1"""; Tasks: kontextmenue

[Run]
Filename: "{app}\Coversuche.exe"; Description: "Coversuche jetzt starten"; Flags: nowait postinstall skipifsilent

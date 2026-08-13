; Inno Setup script for "Abdul Sattar Woods"
; Build:  & "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" AbdulSattarWoods.iss
; Output: installer\AbdulSattarWoods-Setup.exe
;
; Installs PER-USER into %LOCALAPPDATA%\Programs\Abdul Sattar Woods so the
; app can write its data (storage/, .env, logs, backups) next to the exe
; without admin rights. No UAC prompt.
;
; The product name is defined once below; keep it in sync with config.APP_NAME's
; default and AbdulSattarWoods.spec (APP_NAME).

#define AppName "Abdul Sattar Woods"
#define AppVersion "0.3.0"
#define AppExe "Abdul Sattar Woods.exe"
#define Publisher "Abdul Sattar Woods"

[Setup]
; AppId is the STABLE upgrade identity — kept unchanged so an existing install
; upgrades in place (keeping the user's .env + backups).
AppId={{8F2A6C14-3B7E-4D9A-9C1F-2E5B7A0D4C61}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#Publisher}
DefaultDirName={localappdata}\Programs\{#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer
OutputBaseFilename=AbdulSattarWoods-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
; The whole PyInstaller folder build (exe + _internal + .env.example + readme).
; Exclude any runtime data (created next to the exe at first run) and a real
; .env so we never ship a developer's database or settings.
Source: "dist\Abdul Sattar Woods\*"; DestDir: "{app}"; Excludes: "storage,storage\*,.env"; Flags: recursesubdirs createallsubdirs ignoreversion
; One-click speed-up: adds a Windows Defender exclusion so the app isn't
; re-scanned on every launch (the main cause of slow start-up).
Source: "speed-up.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{userprograms}\Speed up {#AppName}"; Filename: "{app}\speed-up.bat"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
; Offer the speed-up right after install (it self-elevates for the one Defender
; setting it changes). Recommended, but the user can untick it.
Filename: "{app}\speed-up.bat"; Description: "Make the app open faster (recommended)"; Flags: postinstall skipifsilent runasoriginaluser
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove app data created at runtime so uninstall leaves nothing behind.
Type: filesandordirs; Name: "{app}\storage"

; Script generated for Inno Setup Compiler
; Electoral Roll Check — Offline Windows App for Fuzzy Hindi Voter-List Matching

#define MyAppName "Electoral Roll Check"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "ECI UP BLO Tools"
#define MyAppExeName "ElectoralRollCheck.exe"

[Setup]
AppId={{57EFBFE0-1529-42E7-855F-4D54244E5149}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\ElectoralRollCheck
DisableProgramGroupPage=yes
OutputBaseFilename=ElectoralRollCheck_Setup_v1.0.0
OutputDir=..\installer_output
SetupIconFile=..\voter_match\data\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\ElectoralRollCheck\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\voter_match\data\icon.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\voter_match\data\icon.ico"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

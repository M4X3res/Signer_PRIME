
#define AppName "Signer"
#define AppVersion "2.0.0"
#define Publisher "M4X3Corp"

[Setup]
AppId={{420594D9-8CDA-4304-BC0C-D0ADBE9C8DF3}}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\Signer
DefaultGroupName=Signer
OutputDir=Output
OutputBaseFilename=SignerInstaller
WizardStyle=modern
PrivilegesRequired=admin
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=assets\ico.ico
WizardImageFile=assets\wizard.bmp
WizardSmallImageFile=assets\wizard-small.bmp

; Включаем страницу выбора папки установки
DisableDirPage=no
UsePreviousAppDir=yes
DisableProgramGroupPage=yes

ExtraDiskSpaceRequired=4300000000

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: desktopicon; Description: "Создать ярлык на рабочем столе"

[Components]
Name: "core"; Description: "Signer"; Flags: fixed
Name: "cuda"; Description: "NVIDIA CUDA Toolkit"
Name: "ffmpeg"; Description: "FFmpeg"
Name: "klite"; Description: "K-Lite Codec Pack"

[Files]
Source: "7z.exe"; DestDir: "{tmp}"; Flags: dontcopy
Source: "7z.dll"; DestDir: "{tmp}"; Flags: dontcopy

[Icons]
Name: "{group}\Signer"; Filename: "{app}\Signer.exe"
Name: "{autodesktop}\Signer"; Filename: "{app}\Signer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Signer.exe"; Flags: postinstall nowait skipifsilent

[Code]
// Остальной код установки (скачивание GitHub Release, прогресс, скорость,
// распаковка и установка компонентов) остаётся без изменений.
// Эта версия включает страницу выбора папки установки.

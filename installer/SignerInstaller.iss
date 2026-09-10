
#define AppName "Signer"
#define AppVersion "2.0.0"
#define Publisher "M4X3Corp"

[Setup]
AppId={{420594D9-8CDA-4304-BC0C-D0ADBE9C8DF3}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#Publisher}
DefaultDirName={autopf}\Signer
DefaultGroupName=Signer
OutputDir=Output
OutputBaseFilename=SignerInstaller
WizardStyle=modern
PrivilegesRequired=admin
Compression=lzma2
SolidCompression=yes
SetupIconFile=assets\ico.ico
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: desktopicon; Description: "{cm:CreateDesktopIcon}"
Name: cuda; Description: "Установить NVIDIA CUDA Toolkit"
Name: ffmpeg; Description: "Установить FFmpeg"
Name: klite; Description: "Установить K-Lite Codec Pack"

[Files]

; --------------------------------------------------
; 7-Zip
; --------------------------------------------------

Source: "7z.exe"; DestDir: "{tmp}"
Source: "7z.dll"; DestDir: "{tmp}"

; --------------------------------------------------
; Последний релиз Signer
; --------------------------------------------------

Source: "https://github.com/M4X3res/Signer_PRIME/releases/latest/download/Signer.7z.001"; \
    DestName: "Signer.7z.001"; \
    DestDir: "{tmp}"; \
    ExternalSize: 1997159793; \
    Flags: external download ignoreversion

Source: "https://github.com/M4X3res/Signer_PRIME/releases/latest/download/Signer.7z.002"; \
    DestName: "Signer.7z.002"; \
    DestDir: "{tmp}"; \
    ExternalSize: 1997159793; \
    Flags: external download ignoreversion

Source: "https://github.com/M4X3res/Signer_PRIME/releases/latest/download/Signer.7z.003"; \
    DestName: "Signer.7z.003"; \
    DestDir: "{tmp}"; \
    ExternalSize: 38587596; \
    Flags: external download ignoreversion

; --------------------------------------------------
; CUDA
; --------------------------------------------------

Source: "https://developer.download.nvidia.com/compute/cuda/12.6.0/network_installers/cuda_12.6.0_windows_network.exe"; \
    DestName: "cuda.exe"; \
    DestDir: "{tmp}"; \
    ExternalSize: 3200000; \
    Flags: external download ignoreversion; \
    Tasks: cuda

; --------------------------------------------------
; FFmpeg
; --------------------------------------------------

Source: "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip"; \
    DestName: "ffmpeg.zip"; \
    DestDir: "{tmp}"; \
    ExternalSize: 115000000; \
    Flags: external download ignoreversion; \
    Tasks: ffmpeg

; --------------------------------------------------
; K-Lite
; --------------------------------------------------

Source: "https://files2.codecguide.com/K-Lite_Codec_Pack_Standard.exe"; \
    DestName: "klite.exe"; \
    DestDir: "{tmp}"; \
    ExternalSize: 60000000; \
    Flags: external download ignoreversion; \
    Tasks: klite

[Icons]
Name: "{group}\Signer"; Filename: "{app}\Signer.exe"
Name: "{autodesktop}\Signer"; Filename: "{app}\Signer.exe"; Tasks: desktopicon

[Run]

; ---------- Распаковка Signer ----------

Filename: "{tmp}\7z.exe"; \
    Parameters: "x ""{tmp}\Signer.7z.001"" -o""{app}"" -y"; \
    Flags: waituntilterminated

; ---------- CUDA ----------

Filename: "{tmp}\cuda.exe"; \
    Tasks: cuda; \
    Flags: waituntilterminated

; ---------- K-Lite ----------

Filename: "{tmp}\klite.exe"; \
    Parameters: "/verysilent /norestart"; \
    Tasks: klite; \
    Flags: waituntilterminated

; ---------- Запуск программы ----------

Filename: "{app}\Signer.exe"; \
    Description: "Запустить Signer"; \
    Flags: postinstall nowait skipifsilent

[Code]

var
  ResultCode: Integer;
  HasCuda: Boolean;
  HasFFmpeg: Boolean;
  HasKLite: Boolean;

function DetectCuda: Boolean;
begin
  Result :=
    DirExists(ExpandConstant('{pf}\NVIDIA GPU Computing Toolkit\CUDA')) or
    DirExists(ExpandConstant('{pf64}\NVIDIA GPU Computing Toolkit\CUDA'));
end;

function DetectFFmpeg: Boolean;
var
  RC: Integer;
begin
  Result :=
    Exec(
      ExpandConstant('{cmd}'),
      '/C where ffmpeg.exe >nul 2>&1',
      '',
      SW_HIDE,
      ewWaitUntilTerminated,
      RC
    ) and (RC = 0);
end;

function DetectKLite: Boolean;
begin
  Result :=
    RegKeyExists(HKLM,
      'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\K-Lite Codec Pack_is1') or
    RegKeyExists(HKLM64,
      'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\K-Lite Codec Pack_is1');
end;

procedure InitializeWizard;
var
  I: Integer;
  Item: String;
begin
  HasCuda := DetectCuda;
  HasFFmpeg := DetectFFmpeg;
  HasKLite := DetectKLite;

  for I := 0 to WizardForm.TasksList.Items.Count-1 do
  begin
    Item := UpperCase(WizardForm.TasksList.Items[I]);

    if Pos('CUDA', Item) > 0 then
      WizardForm.TasksList.Checked[I] := not HasCuda;

    if Pos('FFMPEG', Item) > 0 then
      WizardForm.TasksList.Checked[I] := not HasFFmpeg;

    if Pos('K-LITE', Item) > 0 then
      WizardForm.TasksList.Checked[I] := not HasKLite;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep <> ssPostInstall then
    Exit;

  if IsTaskSelected('ffmpeg') then
  begin
    Exec(
      ExpandConstant('{tmp}\7z.exe'),
      'x "' + ExpandConstant('{tmp}\ffmpeg.zip') + '" -o"' + ExpandConstant('{tmp}\ffmpeg') + '" -y',
      '',
      SW_HIDE,
      ewWaitUntilTerminated,
      ResultCode
    );

    Exec(
      ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      '-NoProfile -Command "Get-ChildItem -Recurse ''' +
      ExpandConstant('{tmp}\ffmpeg') +
      ''' -Filter *.exe | Copy-Item -Destination ''' +
      ExpandConstant('{app}') +
      ''' -Force"',
      '',
      SW_HIDE,
      ewWaitUntilTerminated,
      ResultCode
    );

    Exec(
      'setx.exe',
      'PATH "%PATH%;' + ExpandConstant('{app}') + '"',
      '',
      SW_HIDE,
      ewWaitUntilTerminated,
      ResultCode
    );
  end;
end;
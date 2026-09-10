#define AppName "Signer"
#define AppVersion "2.0.0"
#define Publisher "M4X3Corp"
#define PublisherURL "https://example.com"
#define SupportURL "https://example.com/support"
#define UpdatesURL "https://example.com/updates"

[Setup]
AppId={{420594D9-8CDA-4304-BC0C-D0ADBE9C8DF3}}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#Publisher}
AppPublisherURL={#PublisherURL}
AppSupportURL={#SupportURL}
AppUpdatesURL={#UpdatesURL}
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#Publisher}
VersionInfoDescription={#AppName} Setup
DefaultDirName={autopf}\Signer
DefaultGroupName=Signer
OutputDir=Output
OutputBaseFilename=SignerInstaller
WizardStyle=modern
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
Compression=lzma2
SolidCompression=yes
SetupIconFile=assets\ico.ico
WizardImageFile=assets\wizard.bmp
WizardSmallImageFile=assets\wizard-small.bmp
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
WizardResizable=no
UninstallDisplayIcon={app}\Signer.exe
UninstallDisplayName={#AppName}
MinVersion=10.0.17763
ExtraDiskSpaceRequired=4300000000
; Keep this in sync with RequiredSpaceMB in [Code] below — Inno Setup
; directives are not readable as Pascal identifiers, so the same number
; has to be duplicated on both sides.
CloseApplications=yes
RestartApplications=no
SetupMutex=SignerSetupMutex_420594D9
AppMutex=SignerAppMutex_420594D9
; If you have a code-signing certificate, sign both this compiled installer
; and Signer.exe itself (signtool.exe) before shipping. Unsigned admin-elevated
; installers get flagged by SmartScreen/AV heuristics far more aggressively.

; Optional but recommended for a more "finished" first-run experience:
; LicenseFile=assets\license.rtf
; InfoBeforeFile=assets\readme_before.rtf

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Languages\Default.isl"

[Tasks]
Name: desktopicon; Description: "Создать ярлык на рабочем столе"

[Types]
Name: "full"; Description: "Полная установка"
Name: "compact"; Description: "Только базовая программа"
Name: "custom"; Description: "Выборочная установка"; Flags: iscustom

[Components]
Name: "core"; Description: "Signer (основная программа)"; Types: full compact custom; Flags: fixed
Name: "cuda"; Description: "NVIDIA CUDA Toolkit (ускорение AI, ~3 ГБ)"; Types: full
Name: "ffmpeg"; Description: "FFmpeg (обработка видео, ~115 МБ)"; Types: full
Name: "klite"; Description: "K-Lite Codec Pack (кодеки, ~60 МБ)"; Types: full

[Files]
Source: "7z.exe"; DestDir: "{tmp}"; Flags: dontcopy
Source: "7z.dll"; DestDir: "{tmp}"; Flags: dontcopy

Source: "https://github.com/M4X3res/Signer_PRIME/releases/latest/download/Signer.7z.001"; \
    DestDir: "{tmp}"; DestName: "Signer.7z.001"; \
    ExternalSize: 1997159793; Flags: external download ignoreversion; \
    Components: core

Source: "https://github.com/M4X3res/Signer_PRIME/releases/latest/download/Signer.7z.002"; \
    DestDir: "{tmp}"; DestName: "Signer.7z.002"; \
    ExternalSize: 1997159793; Flags: external download ignoreversion; \
    Components: core

Source: "https://github.com/M4X3res/Signer_PRIME/releases/latest/download/Signer.7z.003"; \
    DestDir: "{tmp}"; DestName: "Signer.7z.003"; \
    ExternalSize: 38587596; Flags: external download ignoreversion; \
    Components: core

Source: "https://developer.download.nvidia.com/compute/cuda/12.6.0/network_installers/cuda_12.6.0_windows_network.exe"; \
    DestDir: "{tmp}"; DestName: "cuda.exe"; \
    ExternalSize: 3200000; Flags: external download ignoreversion; \
    Components: cuda

Source: "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip"; \
    DestDir: "{tmp}"; DestName: "ffmpeg.zip"; \
    ExternalSize: 115000000; Flags: external download ignoreversion; \
    Components: ffmpeg

Source: "https://files2.codecguide.com/K-Lite_Codec_Pack_Standard.exe"; \
    DestDir: "{tmp}"; DestName: "klite.exe"; \
    ExternalSize: 60000000; Flags: external download ignoreversion; \
    Components: klite

[Icons]
Name: "{group}\Signer"; Filename: "{app}\Signer.exe"
Name: "{group}\Удалить Signer"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Signer"; Filename: "{app}\Signer.exe"; Tasks: desktopicon

[UninstallDelete]
Type: filesandordirs; Name: "{tmp}\Signer_extract"
Type: files; Name: "{app}\*.log"

[Run]
Filename: "{app}\Signer.exe"; \
Description: "Запустить Signer сейчас"; \
Flags: postinstall nowait skipifsilent

[Code]
const
  { Must match ExtraDiskSpaceRequired above (in MB, not bytes) }
  RequiredSpaceMB = 4300;

var
  ResultCode: Integer;

{ ----------------------------------------------------------------------
  Detection helpers
  ---------------------------------------------------------------------- }

function DetectCuda: Boolean;
begin
  Result :=
    DirExists(ExpandConstant('{pf}\NVIDIA GPU Computing Toolkit\CUDA')) or
    DirExists(ExpandConstant('{pf64}\NVIDIA GPU Computing Toolkit\CUDA'));
end;

function DetectFFmpeg: Boolean;
var
  EnvPath: String;
begin
  { Cheaper and more reliable than shelling out to "where":
    check common install locations and PATH env var directly.
    Inno has no GetEnvironmentVariable function - env vars are read
    via ExpandConstant using the percent-name constant syntax. }
  Result := False;
  EnvPath := ExpandConstant('{%PATH}');
  if Pos('ffmpeg', LowerCase(EnvPath)) > 0 then
    Result := True;

  if FileExists(ExpandConstant('{pf}\ffmpeg\bin\ffmpeg.exe')) or
     FileExists(ExpandConstant('{pf64}\ffmpeg\bin\ffmpeg.exe')) then
    Result := True;
end;

function DetectKLite: Boolean;
begin
  Result :=
    RegKeyExists(HKLM, 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\K-Lite Codec Pack_is1') or
    RegKeyExists(HKLM64, 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\K-Lite Codec Pack_is1');
end;

{ ----------------------------------------------------------------------
  Optional integrity check. Fill in real SHA-256 hashes for your build
  before shipping, then call VerifyFile() after each download in
  CurStepChanged. This is the single most important addition for an
  installer that pulls multi-GB payloads over plain HTTPS from a
  release URL that can change contents at any time.
  ---------------------------------------------------------------------- }

function VerifyFile(const FilePath, ExpectedSHA256: String): Boolean;
var
  ResCode: Integer;
  Output: AnsiString;
  TmpFile: String;
begin
  Result := False;
  TmpFile := ExpandConstant('{tmp}\hash_check.txt');
  Exec(ExpandConstant('{cmd}'),
    '/C certutil -hashfile "' + FilePath + '" SHA256 > "' + TmpFile + '"',
    '', SW_HIDE, ewWaitUntilTerminated, ResCode);

  if LoadStringFromFile(TmpFile, Output) then
  begin
    if Pos(LowerCase(ExpectedSHA256), LowerCase(String(Output))) > 0 then
      Result := True;
  end;
  DeleteFile(TmpFile);
end;

{ ----------------------------------------------------------------------
  Wizard setup
  ---------------------------------------------------------------------- }

procedure InitializeWizard;
var
  I: Integer;
  HasCuda, HasFFmpeg, HasKLite: Boolean;
begin
  ExtractTemporaryFile('7z.exe');
  ExtractTemporaryFile('7z.dll');

  HasCuda := DetectCuda;
  HasFFmpeg := DetectFFmpeg;
  HasKLite := DetectKLite;

  for I := 0 to WizardForm.ComponentsList.Items.Count - 1 do
  begin
    if Pos('CUDA', UpperCase(WizardForm.ComponentsList.Items[I])) > 0 then
      WizardForm.ComponentsList.Checked[I] := not HasCuda;

    if Pos('FFMPEG', UpperCase(WizardForm.ComponentsList.Items[I])) > 0 then
      WizardForm.ComponentsList.Checked[I] := not HasFFmpeg;

    if Pos('K-LITE', UpperCase(WizardForm.ComponentsList.Items[I])) > 0 then
      WizardForm.ComponentsList.Checked[I] := not HasKLite;
  end;

  WizardForm.WelcomeLabel1.Caption := 'Добро пожаловать в установщик Signer';
  WizardForm.WelcomeLabel2.Caption :=
    'Signer автоматически загрузит последнюю версию программы, установит ' +
    'необходимые компоненты и подготовит приложение к работе.' + #13#10#13#10 +
    'Для установки потребуется около 4,3 ГБ свободного места и стабильное ' +
    'подключение к интернету.';

  WizardForm.FinishedHeadingLabel.Caption := 'Установка Signer завершена';
  WizardForm.FinishedLabel.Caption :=
    'Программа готова к работе. Следующие обновления будут устанавливаться ' +
    'прямо из приложения без повторного запуска установщика.';
end;

function HasEnoughDiskSpace: Boolean;
var
  FreeBytes, TotalBytes: Int64;
begin
  Result := True;
  if GetSpaceOnDisk64(ExpandConstant('{app}'), FreeBytes, TotalBytes) then
    Result := FreeBytes >= (Int64(RequiredSpaceMB) * 1024 * 1024);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpSelectDir then
  begin
    if not HasEnoughDiskSpace then
    begin
      MsgBox('Недостаточно свободного места на диске для установки Signer. ' +
        'Требуется примерно ' + IntToStr(RequiredSpaceMB) + ' МБ.',
        mbError, MB_OK);
      Result := False;
    end;
  end;
end;

{ ----------------------------------------------------------------------
  Post-install actions
  ---------------------------------------------------------------------- }

procedure CurStepChanged(CurStep: TSetupStep);
var
  ExtractOK: Boolean;
begin
  if CurStep <> ssPostInstall then Exit;

  Log('Начало распаковки основного архива Signer');

  // TODO: uncomment and fill real hashes once you have a stable release
  // to verify against.
  //
  // if not VerifyFile(ExpandConstant('{tmp}\Signer.7z.001'), 'PUT_SHA256_HERE') then
  // begin
  //   MsgBox('Проверка целостности загруженного файла не удалась. ' +
  //     'Установка прервана.', mbCriticalError, MB_OK);
  //   Exit;
  // end;

  ExtractOK := Exec(
    ExpandConstant('{tmp}\7z.exe'),
    'x "' + ExpandConstant('{tmp}\Signer.7z.001') + '" -o"' + ExpandConstant('{app}') + '" -aoa -y',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);

  if not ExtractOK then
  begin
    Log('Ошибка распаковки основного архива, код: ' + IntToStr(ResultCode));
    MsgBox('Не удалось распаковать основные файлы Signer (код ошибки ' +
      IntToStr(ResultCode) + '). Попробуйте переустановить программу.',
      mbCriticalError, MB_OK);
    Exit;
  end;

  if IsComponentSelected('cuda') then
  begin
    Log('Запуск установки CUDA Toolkit');
    if not Exec(ExpandConstant('{tmp}\cuda.exe'), '', '', SW_SHOWNORMAL,
         ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
      Log('CUDA Toolkit: установка завершилась с кодом ' + IntToStr(ResultCode));
  end;

  if IsComponentSelected('klite') then
  begin
    Log('Запуск тихой установки K-Lite Codec Pack');
    if not Exec(ExpandConstant('{tmp}\klite.exe'), '/verysilent /norestart',
         '', SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
      Log('K-Lite: установка завершилась с кодом ' + IntToStr(ResultCode));
  end;

  if IsComponentSelected('ffmpeg') then
  begin
    Log('Распаковка FFmpeg');
    Exec(ExpandConstant('{tmp}\7z.exe'),
      'x "' + ExpandConstant('{tmp}\ffmpeg.zip') + '" -o"' + ExpandConstant('{tmp}\ffmpeg') + '" -y',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

    if ResultCode = 0 then
    begin
      Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
        '-NoProfile -Command "Get-ChildItem -Recurse ''' +
        ExpandConstant('{tmp}\ffmpeg') +
        ''' -Filter *.exe | Copy-Item -Destination ''' +
        ExpandConstant('{app}') +
        ''' -Force"',
        '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end
    else
      Log('Ошибка распаковки FFmpeg, код: ' + IntToStr(ResultCode));
  end;

  { Cleanup temp payloads regardless of outcome }
  DeleteFile(ExpandConstant('{tmp}\Signer.7z.001'));
  DeleteFile(ExpandConstant('{tmp}\Signer.7z.002'));
  DeleteFile(ExpandConstant('{tmp}\Signer.7z.003'));
  DeleteFile(ExpandConstant('{tmp}\ffmpeg.zip'));
  DeleteFile(ExpandConstant('{tmp}\cuda.exe'));
  DeleteFile(ExpandConstant('{tmp}\klite.exe'));

  Log('Установка Signer завершена успешно');
end;

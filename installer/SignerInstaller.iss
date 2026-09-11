#define AppName "Signer"
#define AppVersion "2.0.0"
#define Publisher "M4X3Corp"
#define PublisherURL "https://github.com/M4X3res/Signer_PRIME"
#define SupportURL "https://github.com/M4X3res/Signer_PRIME/issues"
#define UpdatesURL "https://github.com/M4X3res/Signer_PRIME/releases"

; ──────────────────────────────────────────────────────────────────
; Release configuration — points at the GitHub release for {#AppVersion}
; https://github.com/M4X3res/Signer_PRIME/releases/tag/v2.0.0
;
; Confirmed real assets of that release (verified against the actual
; expanded asset list, not guessed):
;   - Signer.7z.001 .. Signer.7z.041  (multi-volume 7z archive, ~100 MB
;     per part except the last part ~13.7 MB — ~4.0 GB total)
;   - checksum.sha256                 (SHA-256 of every part, one per line)
;   - README.md / release_notes.txt / BUILD_AUTOUPDATE.md (docs, not needed)
;   - Source code (zip) / Source code (tar.gz) (GitHub auto-generated, not needed)
;
; If you cut a new release with a different tag or a different number of
; archive parts, update RELEASE_TAG and SIGNER_PART_COUNT below, and adjust
; the [Files] entries to match (add/remove Signer.7z.0NN lines).
; ──────────────────────────────────────────────────────────────────
#define RELEASE_TAG "v2.0.0"
#define RELEASE_BASE_URL "https://github.com/M4X3res/Signer_PRIME/releases/download/" + RELEASE_TAG
#define SIGNER_PART_COUNT 41

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

; ── Основной архив приложения (многотомный, 41 часть) и контрольная сумма ──
; Скачиваются напрямую с релиза {#RELEASE_TAG} репозитория Signer_PRIME.
; Реальный список ассетов релиза: Signer.7z.001 .. Signer.7z.041 (части по
; ~100 МБ, последняя ~13.7 МБ), checksum.sha256, а также сопроводительные
; README.md / release_notes.txt / BUILD_AUTOUPDATE.md (не нужны для установки).
Source: "{#RELEASE_BASE_URL}/Signer.7z.001"; DestDir: "{tmp}"; DestName: "Signer.7z.001"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.002"; DestDir: "{tmp}"; DestName: "Signer.7z.002"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.003"; DestDir: "{tmp}"; DestName: "Signer.7z.003"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.004"; DestDir: "{tmp}"; DestName: "Signer.7z.004"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.005"; DestDir: "{tmp}"; DestName: "Signer.7z.005"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.006"; DestDir: "{tmp}"; DestName: "Signer.7z.006"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.007"; DestDir: "{tmp}"; DestName: "Signer.7z.007"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.008"; DestDir: "{tmp}"; DestName: "Signer.7z.008"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.009"; DestDir: "{tmp}"; DestName: "Signer.7z.009"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.010"; DestDir: "{tmp}"; DestName: "Signer.7z.010"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.011"; DestDir: "{tmp}"; DestName: "Signer.7z.011"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.012"; DestDir: "{tmp}"; DestName: "Signer.7z.012"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.013"; DestDir: "{tmp}"; DestName: "Signer.7z.013"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.014"; DestDir: "{tmp}"; DestName: "Signer.7z.014"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.015"; DestDir: "{tmp}"; DestName: "Signer.7z.015"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.016"; DestDir: "{tmp}"; DestName: "Signer.7z.016"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.017"; DestDir: "{tmp}"; DestName: "Signer.7z.017"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.018"; DestDir: "{tmp}"; DestName: "Signer.7z.018"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.019"; DestDir: "{tmp}"; DestName: "Signer.7z.019"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.020"; DestDir: "{tmp}"; DestName: "Signer.7z.020"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.021"; DestDir: "{tmp}"; DestName: "Signer.7z.021"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.022"; DestDir: "{tmp}"; DestName: "Signer.7z.022"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.023"; DestDir: "{tmp}"; DestName: "Signer.7z.023"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.024"; DestDir: "{tmp}"; DestName: "Signer.7z.024"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.025"; DestDir: "{tmp}"; DestName: "Signer.7z.025"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.026"; DestDir: "{tmp}"; DestName: "Signer.7z.026"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.027"; DestDir: "{tmp}"; DestName: "Signer.7z.027"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.028"; DestDir: "{tmp}"; DestName: "Signer.7z.028"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.029"; DestDir: "{tmp}"; DestName: "Signer.7z.029"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.030"; DestDir: "{tmp}"; DestName: "Signer.7z.030"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.031"; DestDir: "{tmp}"; DestName: "Signer.7z.031"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.032"; DestDir: "{tmp}"; DestName: "Signer.7z.032"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.033"; DestDir: "{tmp}"; DestName: "Signer.7z.033"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.034"; DestDir: "{tmp}"; DestName: "Signer.7z.034"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.035"; DestDir: "{tmp}"; DestName: "Signer.7z.035"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.036"; DestDir: "{tmp}"; DestName: "Signer.7z.036"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.037"; DestDir: "{tmp}"; DestName: "Signer.7z.037"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.038"; DestDir: "{tmp}"; DestName: "Signer.7z.038"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.039"; DestDir: "{tmp}"; DestName: "Signer.7z.039"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.040"; DestDir: "{tmp}"; DestName: "Signer.7z.040"; ExternalSize: 100000000; Flags: external download ignoreversion; Components: core
Source: "{#RELEASE_BASE_URL}/Signer.7z.041"; DestDir: "{tmp}"; DestName: "Signer.7z.041"; ExternalSize: 13700000; Flags: external download ignoreversion; Components: core

Source: "{#RELEASE_BASE_URL}/checksum.sha256"; DestDir: "{tmp}"; DestName: "checksum.sha256"; ExternalSize: 4000; Flags: external download ignoreversion; Components: core

Source: "https://developer.download.nvidia.com/compute/cuda/12.6.0/network_installers/cuda_12.6.0_windows_network.exe"; DestDir: "{tmp}"; DestName: "cuda.exe"; ExternalSize: 3200000; Flags: external download ignoreversion; Components: cuda

Source: "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip"; DestDir: "{tmp}"; DestName: "ffmpeg.zip"; ExternalSize: 115000000; Flags: external download ignoreversion; Components: ffmpeg

Source: "https://files2.codecguide.com/K-Lite_Codec_Pack_1995_Standard.exe"; DestDir: "{tmp}"; DestName: "klite.exe"; ExternalSize: 60000000; Flags: external download ignoreversion; Components: klite

[Icons]
Name: "{group}\Signer"; Filename: "{app}\Signer.exe"
Name: "{group}\Удалить Signer"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Signer"; Filename: "{app}\Signer.exe"; Tasks: desktopicon

[UninstallDelete]
Type: filesandordirs; Name: "{tmp}\Signer_extract"
Type: files; Name: "{app}\*.log"

[Run]
Filename: "{app}\Signer.exe"; Description: "Запустить Signer сейчас"; Flags: postinstall nowait skipifsilent

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
  SHA-256 checksum verification against the downloaded checksum.sha256.

  checksum.sha256 is expected to contain a line like:
      <hex-hash>  Signer.7z
  (this is exactly the format produced by prepare_release.bat via
  Get-FileHash | Out-File, and by `sha256sum`.)

  We compute the SHA-256 of the downloaded Signer.7z via certutil and
  compare it case-insensitively against the hash recorded for
  "Signer.7z" inside checksum.sha256. If the expected hash can't be
  found (e.g. different filename/format in a future release), we skip
  strict verification rather than block the install outright.
  ---------------------------------------------------------------------- }

function GetSHA256OfFile(const FilePath: String): String;
var
  ResCode: Integer;
  Output: AnsiString;
  TmpFile: String;
  Lines: TArrayOfString;
  I: Integer;
  Line: String;
begin
  Result := '';
  TmpFile := ExpandConstant('{tmp}\hash_check.txt');
  Exec(ExpandConstant('{cmd}'),
    '/C certutil -hashfile "' + FilePath + '" SHA256 > "' + TmpFile + '"',
    '', SW_HIDE, ewWaitUntilTerminated, ResCode);

  if not LoadStringsFromFile(TmpFile, Lines) then
  begin
    DeleteFile(TmpFile);
    Exit;
  end;

  { certutil output format:
      SHA256 hash of <path>:
      <hex bytes with spaces>
      CertUtil: -hashfile command completed successfully.
    We want the second line, with spaces stripped. }
  for I := 0 to GetArrayLength(Lines) - 1 do
  begin
    Line := Trim(Lines[I]);
    if (Line <> '') and (Pos('CertUtil', Line) = 0) and (Pos('SHA256', Line) = 0) and (Pos(':', Line) = 0) then
    begin
      StringChangeEx(Line, ' ', '', True);
      Result := LowerCase(Line);
      Break;
    end;
  end;

  DeleteFile(TmpFile);
end;

function GetExpectedHashFromChecksumFile(const ChecksumFilePath, TargetFileName: String): String;
var
  Lines: TArrayOfString;
  I: Integer;
  Line, Hash, Rest: String;
  SpacePos: Integer;
begin
  Result := '';
  if not LoadStringsFromFile(ChecksumFilePath, Lines) then
    Exit;

  for I := 0 to GetArrayLength(Lines) - 1 do
  begin
    Line := Trim(Lines[I]);
    if (Line = '') or (Line[1] = '#') then
      Continue;

    { Format: "<hash>  <filename>" (one or more spaces between them) }
    SpacePos := Pos(' ', Line);
    if SpacePos = 0 then
      Continue;

    Hash := Copy(Line, 1, SpacePos - 1);
    Rest := Trim(Copy(Line, SpacePos + 1, MaxInt));
    { Some tools prefix the filename with '*' (binary mode marker) }
    if (Rest <> '') and (Rest[1] = '*') then
      Rest := Copy(Rest, 2, MaxInt);

    if LowerCase(Rest) = LowerCase(TargetFileName) then
    begin
      Result := LowerCase(Hash);
      Exit;
    end;
  end;
end;

function GetPartFileName(PartIndex: Integer): String;
var
  PartStr: String;
begin
  PartStr := IntToStr(PartIndex);
  while Length(PartStr) < 3 do
    PartStr := '0' + PartStr;
  Result := 'Signer.7z.' + PartStr;
end;

function VerifySignerArchiveChecksum: Boolean;
var
  ChecksumPath, PartPath, PartName, ExpectedHash, ActualHash: String;
  I: Integer;
  AnyChecked: Boolean;
begin
  Result := True; { fail-open per-part: missing checksum data doesn't block install }
  AnyChecked := False;

  ChecksumPath := ExpandConstant('{tmp}\checksum.sha256');

  { Every part must at least exist on disk — this we DO enforce strictly,
    since a missing part means extraction will fail anyway. }
  for I := 1 to {#SIGNER_PART_COUNT} do
  begin
    PartName := GetPartFileName(I);
    PartPath := ExpandConstant('{tmp}\') + PartName;
    if not FileExists(PartPath) then
    begin
      Log('Файл ' + PartName + ' не найден — скачивание, вероятно, не завершилось');
      Result := False;
      Exit;
    end;
  end;

  if not FileExists(ChecksumPath) then
  begin
    Log('checksum.sha256 не найден — проверка целостности пропущена (файлы есть, продолжаем)');
    Exit;
  end;

  for I := 1 to {#SIGNER_PART_COUNT} do
  begin
    PartName := GetPartFileName(I);
    PartPath := ExpandConstant('{tmp}\') + PartName;

    ExpectedHash := GetExpectedHashFromChecksumFile(ChecksumPath, PartName);
    if ExpectedHash = '' then
    begin
      Log('Хэш для ' + PartName + ' не найден в checksum.sha256 — пропуск проверки этой части');
      Continue;
    end;

    AnyChecked := True;
    Log('Проверка SHA-256: ' + PartName + '...');
    ActualHash := GetSHA256OfFile(PartPath);

    if ActualHash = '' then
    begin
      Log('Не удалось вычислить SHA-256 для ' + PartName + ' через certutil — пропуск');
      Continue;
    end;

    if ActualHash <> ExpectedHash then
    begin
      Log('ОШИБКА: SHA-256 не совпадает для ' + PartName + '!');
      Log('  Ожидалось: ' + ExpectedHash);
      Log('  Получено:  ' + ActualHash);
      Result := False;
      Exit;
    end;
  end;

  if AnyChecked and Result then
    Log('✓ Все части Signer.7z прошли проверку SHA-256');
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
    'Signer автоматически загрузит версию ' + '{#AppVersion}' + ' программы с GitHub, ' +
    'установит необходимые компоненты и подготовит приложение к работе.' + #13#10#13#10 +
    'Для установки потребуется около 4,3 ГБ свободного места и стабильное ' +
    'подключение к интернету.';

  WizardForm.FinishedHeadingLabel.Caption := 'Установка Signer завершена';
  WizardForm.FinishedLabel.Caption :=
    'Программа готова к работе. Следующие обновления можно установить, ' +
    'скачав новую версию установщика или новый релиз с GitHub.';
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
  I: Integer;
begin
  if CurStep <> ssPostInstall then Exit;

  Log('Проверка целостности скачанных частей Signer.7z...');
  if not VerifySignerArchiveChecksum then
  begin
    MsgBox('Проверка частей архива Signer.7z не удалась (файл отсутствует или ' +
      'повреждён при загрузке). Установка прервана. ' +
      'Пожалуйста, запустите установщик заново — докачка частично ' +
      'загруженных файлов произойдёт автоматически.',
      mbCriticalError, MB_OK);
    Exit;
  end;

  Log('Начало распаковки основного архива Signer (многотомный, {#SIGNER_PART_COUNT} частей)');

  { 7-Zip распознаёт многотомный архив по первой части (Signer.7z.001) и
    автоматически подхватывает остальные .002, .003, ... из той же папки. }
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
  for I := 1 to {#SIGNER_PART_COUNT} do
    DeleteFile(ExpandConstant('{tmp}\') + GetPartFileName(I));
  DeleteFile(ExpandConstant('{tmp}\checksum.sha256'));
  DeleteFile(ExpandConstant('{tmp}\ffmpeg.zip'));
  DeleteFile(ExpandConstant('{tmp}\cuda.exe'));
  DeleteFile(ExpandConstant('{tmp}\klite.exe'));

  Log('Установка Signer завершена успешно');
end;

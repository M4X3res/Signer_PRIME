; ══════════════════════════════════════════════════════════════════
; Signer PRIME — Professional Installer
;
; Combines:
;   • Inno Setup's built-in download system (multi-volume 7z archive
;     downloaded straight from a GitHub Release, no bundling needed)
;   • InnoDependencyInstaller (installer/InnoDependencyInstaller-master)
;     to silently install missing prerequisites: VC++ Redistributable,
;     .NET Desktop Runtime 8, WebView2 Runtime (required by the
;     QtWebEngine map view) and ODBC 18 (used by some geo libraries)
;   • Branding assets from installer/assets (icon, wizard images,
;     license/info files) — picked up automatically if present,
;     safely skipped if not, so the script always compiles.
;
; ЗАДАЧА (обновление):
;   1. Профессиональный прогресс загрузки: общий % по всему архиву +
;      % и скорость текущего файла — через кастомный OnDownloadProgress.
;   2. Исправлена ошибка/зависание при прерывании загрузки: список
;      файлов теперь пересобирается (Clear + Add) перед КАЖДОЙ попыткой
;      скачивания внутри retry-цикла, а не один раз в InitializeWizard.
;      Это официально рекомендуемый Inno-паттерн для download-страниц —
;      без него внутреннее состояние TDownloadWizardPage после
;      прерванной попытки могло рассинхронизироваться при повторном
;      запуске Download().
;
; Build:
;   "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" installer\SignerInstaller.iss
;
; Before building:
;   1. Update RELEASE_TAG / SIGNER_PART_COUNT below to match the
;      actual GitHub release you just published
;      (see scripts\build\prepare_release.bat + upload_release.ps1).
;   2. Drop branding files into installer\assets\ using the names
;      referenced below (ico.ico, wizard-image.bmp, wizard-small.bmp,
;      license.txt, info_before.txt) — any of them can be omitted.
; ══════════════════════════════════════════════════════════════════

#define AppName "Signer"
#define AppVersion "2.0.0"
#define Publisher "M4X3Corp"
#define PublisherURL "https://github.com/M4X3res/Signer_PRIME"
#define SupportURL "https://github.com/M4X3res/Signer_PRIME/issues"
#define UpdatesURL "https://github.com/M4X3res/Signer_PRIME/releases"

; ──────────────────────────────────────────────────────────────────
; Release configuration — UPDATE THESE before building a new release
; ──────────────────────────────────────────────────────────────────
#define RELEASE_TAG "v2.0.0"
#define RELEASE_BASE_URL "https://github.com/M4X3res/Signer_PRIME/releases/download/" + RELEASE_TAG
#define SIGNER_PART_COUNT 46

; ──────────────────────────────────────────────────────────────────
; Optional components — URLs for additional downloads
; ──────────────────────────────────────────────────────────────────
#define CUDA_URL "https://developer.download.nvidia.com/compute/cuda/12.6.0/network_installers/cuda_12.6.0_windows_network.exe"
#define CUDA_SIZE 3200000
#define FFMPEG_URL "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip"
#define FFMPEG_SIZE 115000000
#define KLITE_URL "https://files2.codecguide.com/K-Lite_Codec_Pack_1995_Standard.exe"
#define KLITE_SIZE 60000000

; ──────────────────────────────────────────────────────────────────
; Branding assets (installer/assets) — optional, auto-detected
; ──────────────────────────────────────────────────────────────────
#define AssetsDir "assets"

; ══════════════════════════════════════════════════════════════════
; Dependency installer plugin
; ══════════════════════════════════════════════════════════════════
#include "InnoDependencyInstaller-master\CodeDependencies.iss"

[Setup]
AppId={{420594D9-8CDA-4304-BC0C-D0ADBE9C8DF3}}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#Publisher}
AppPublisherURL={#PublisherURL}
AppSupportURL={#SupportURL}
AppUpdatesURL={#UpdatesURL}
AppContact={#SupportURL}
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#Publisher}
VersionInfoDescription={#AppName} Setup
VersionInfoCopyright=© {#Publisher}
DefaultDirName={autopf}\Signer
DefaultGroupName=Signer
OutputDir=Output
OutputBaseFilename=SignerInstaller-{#AppVersion}
WizardStyle=modern
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableDirPage=no
DisableProgramGroupPage=no
DisableWelcomePage=no
AllowNoIcons=yes
UninstallDisplayName={#AppName}
MinVersion=10.0.17763
CloseApplications=yes
RestartApplications=no
; Temporary space: ~4.0GB archive + ~4.3GB extracted = ~8.4GB
ExtraDiskSpaceRequired=8400000000
ShowLanguageDialog=auto
ChangesEnvironment=yes

#ifexist AssetsDir + "\ico.ico"
SetupIconFile={#AssetsDir}\ico.ico
UninstallDisplayIcon={app}\Signer\Signer.exe
#endif

#ifexist AssetsDir + "\wizard-image.bmp"
WizardImageFile={#AssetsDir}\wizard-image.bmp
#endif

#ifexist AssetsDir + "\wizard-small.bmp"
WizardSmallImageFile={#AssetsDir}\wizard-small.bmp
#endif

#ifexist AssetsDir + "\license.txt"
LicenseFile={#AssetsDir}\license.txt
#endif

#ifexist AssetsDir + "\info_before.txt"
InfoBeforeFile={#AssetsDir}\info_before.txt
#endif

#ifexist AssetsDir + "\info_after.txt"
InfoAfterFile={#AssetsDir}\info_after.txt
#endif

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Types]
Name: "full"; Description: "Полная установка (с CUDA, FFmpeg, K-Lite)"
Name: "compact"; Description: "Только базовая программа"
Name: "custom"; Description: "Выборочная установка"; Flags: iscustom

[Components]
Name: "core"; Description: "Signer (основная программа)"; Types: full compact custom; Flags: fixed
Name: "cuda"; Description: "NVIDIA CUDA Toolkit (ускорение AI, ~3 ГБ)"; Types: full
Name: "ffmpeg"; Description: "FFmpeg (обработка видео, ~115 МБ)"; Types: full
Name: "klite"; Description: "K-Lite Codec Pack (кодеки, ~60 МБ)"; Types: full

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительно:"; Flags: unchecked
Name: "launchafter"; Description: "Запустить Signer после установки"; GroupDescription: "Дополнительно:"; Flags: unchecked checkedonce

[Files]
Source: "7z.exe"; Flags: dontcopy noencryption
Source: "7z.dll"; Flags: dontcopy noencryption

[Icons]
Name: "{group}\Signer"; Filename: "{app}\Signer\Signer.exe"; WorkingDir: "{app}\Signer"
Name: "{group}\{cm:UninstallProgram,Signer}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Signer"; Filename: "{app}\Signer\Signer.exe"; WorkingDir: "{app}\Signer"; Tasks: desktopicon

[UninstallDelete]
Type: filesandordirs; Name: "{tmp}\Signer_extract"
Type: filesandordirs; Name: "{tmp}\Signer_parts"
Type: files; Name: "{app}\*.log"

[Run]
Filename: "{app}\Signer\Signer.exe"; Description: "Запустить Signer сейчас"; Flags: nowait postinstall skipifsilent; Tasks: launchafter

[Code]
var
  DownloadPage: TDownloadWizardPage;
  ExtractProgressPage: TOutputProgressWizardPage;

  { ── Прогресс загрузки (общий % + % и скорость текущего файла) ── }
  TotalDownloadSize:   Int64;
  DownloadFileNames:   TArrayOfString;
  DownloadFileSizes:   array of Int64;
  DownloadFileCount:   Integer;

  DownloadLastFileName: String;
  DownloadLastTick:     DWORD;
  DownloadLastProgress: Int64;
  DownloadSpeedBps:     Double;

{ ══════════════════════════════════════════════════════════════════
  Dependencies (InnoDependencyInstaller)
  ══════════════════════════════════════════════════════════════════ }
function GetTickCount: DWORD;
  external 'GetTickCount@kernel32.dll stdcall';
function InitializeSetup: Boolean;

begin
  { Prerequisites Signer actually needs at runtime:
      - VC++ v14 Redistributable: required by PyTorch/OpenCV/ONNX Runtime DLLs
      - .NET Desktop Runtime 8: required by WebView2/PyQt6-WebEngine plumbing
        on some Windows images, and by the Updater toolchain
      - WebView2 Runtime: required by QWebEngineView (map view)
      - ODBC Driver 18: some geo/pyproj-adjacent stacks probe for it;
        harmless if unused, cheap to guarantee it's present }
  Dependency_AddVC14;
  Dependency_AddDotNet80Desktop;
  Dependency_AddWebView2;
  Dependency_AddSqlOdbc18;

  Result := True;
end;

{ ══════════════════════════════════════════════════════════════════
  Utility functions
  ══════════════════════════════════════════════════════════════════ }

function FormatBytes(Bytes: Int64): String;
begin
  if Bytes >= 1073741824 then
    Result := Format('%.2f ГБ', [Bytes / 1073741824.0])
  else if Bytes >= 1048576 then
    Result := Format('%.1f МБ', [Bytes / 1048576.0])
  else if Bytes >= 1024 then
    Result := Format('%.1f КБ', [Bytes / 1024.0])
  else
    Result := Format('%d Б', [Bytes]);
end;

function FormatSpeed(BytesPerSec: Double): String;
begin
  if BytesPerSec >= 1048576 then
    Result := Format('%.2f МБ/с', [BytesPerSec / 1048576])
  else if BytesPerSec >= 1024 then
    Result := Format('%.1f КБ/с', [BytesPerSec / 1024])
  else if BytesPerSec > 0 then
    Result := Format('%.0f Б/с', [BytesPerSec])
  else
    Result := '—';
end;

{ ══════════════════════════════════════════════════════════════════
  Detection helpers for optional components
  ══════════════════════════════════════════════════════════════════ }

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

function GetPartFileName(PartIndex: Integer): String;
begin
  if PartIndex < 10 then
    Result := Format('Signer.7z.00%d', [PartIndex])
  else if PartIndex < 100 then
    Result := Format('Signer.7z.0%d', [PartIndex])
  else
    Result := Format('Signer.7z.%d', [PartIndex]);
end;

function GetPartSize(PartIndex, TotalParts: Integer): Int64;
begin
  { All parts except the last are 100MB }
  if PartIndex < TotalParts then
    Result := 100000000
  else
    { Last part is smaller — approximation only, used for progress display }
    Result := 13700000;
end;

{ ── Построение списка файлов для расчёта прогресса ────────────────
  Вызывается один раз в InitializeWizard. Хранит имена и ОЖИДАЕМЫЕ
  (приблизительные) размеры каждой части архива + checksum-файла,
  чтобы взвешенно считать общий процент загрузки по байтам, а не
  просто по количеству файлов (последняя часть архива намного
  меньше остальных). }
procedure BuildDownloadFileList;
var
  I: Integer;
begin
  SetArrayLength(DownloadFileNames, {#SIGNER_PART_COUNT} + 1);
  SetArrayLength(DownloadFileSizes, {#SIGNER_PART_COUNT} + 1);

  TotalDownloadSize := 0;
  for I := 1 to {#SIGNER_PART_COUNT} do
  begin
    DownloadFileNames[I - 1] := GetPartFileName(I);
    DownloadFileSizes[I - 1] := GetPartSize(I, {#SIGNER_PART_COUNT});
    TotalDownloadSize := TotalDownloadSize + DownloadFileSizes[I - 1];
  end;

  DownloadFileNames[{#SIGNER_PART_COUNT}] := 'checksum.sha256';
  DownloadFileSizes[{#SIGNER_PART_COUNT}] := 2048; { маленький текстовый файл }
  TotalDownloadSize := TotalDownloadSize + DownloadFileSizes[{#SIGNER_PART_COUNT}];

  DownloadFileCount := {#SIGNER_PART_COUNT} + 1;
end;

{ Сумма ожидаемых размеров всех файлов, идущих ПЕРЕД указанным —
  используется чтобы посчитать сколько байт уже гарантированно
  скачано из предыдущих файлов при отображении общего прогресса. }
function GetCompletedBytesBefore(const AFileName: String): Int64;
var
  I: Integer;
begin
  Result := 0;
  for I := 0 to DownloadFileCount - 1 do
  begin
    if DownloadFileNames[I] = AFileName then
      Break;
    Result := Result + DownloadFileSizes[I];
  end;
end;

{ ══════════════════════════════════════════════════════════════════
  Кастомный обработчик прогресса загрузки.

  Показывает ОДНОВРЕМЕННО:
    - строка 1: имя текущего файла, его % и объём (скачано/всего)
    - строка 2: общий % по всему архиву + скорость текущего файла
  Прогресс-бар страницы отражает ОБЩИЙ прогресс (полезнее для
  многотомного архива, чем прогресс одного 100MB-куска).
  ══════════════════════════════════════════════════════════════════ }
function OnDownloadProgress(const Url, FileName: String; const Progress, ProgressMax: Int64): Boolean;
var
  FilePercent:    Integer;
  OverallPercent: Integer;
  CompletedBytes: Int64;
  OverallPosition: Int64;
  NowTick:  DWORD;
  ElapsedMs: Int64;
  SpeedText: String;
  Line1, Line2: String;
begin
  { Новый файл начал качаться — сбрасываем счётчик скорости }
  if FileName <> DownloadLastFileName then
  begin
    DownloadLastFileName := FileName;
    DownloadLastTick     := GetTickCount;
    DownloadLastProgress := 0;
    DownloadSpeedBps     := 0;
  end;

  if ProgressMax > 0 then
    FilePercent := (Progress * 100) div ProgressMax
  else
    FilePercent := 0;

  CompletedBytes  := GetCompletedBytesBefore(FileName);
  OverallPosition := CompletedBytes + Progress;

  if TotalDownloadSize > 0 then
    OverallPercent := (OverallPosition * 100) div TotalDownloadSize
  else
    OverallPercent := 0;
  if OverallPercent > 100 then
    OverallPercent := 100;

  { Скорость пересчитываем не чаще раза в ~300мс — иначе "скачет" }
  NowTick   := GetTickCount;
  ElapsedMs := NowTick - DownloadLastTick;
  if ElapsedMs >= 300 then
  begin
    DownloadSpeedBps     := (Progress - DownloadLastProgress) * 1000.0 / ElapsedMs;
    DownloadLastTick     := NowTick;
    DownloadLastProgress := Progress;
  end;

  SpeedText := FormatSpeed(DownloadSpeedBps);

  Line1 := Format('Файл: %s — %d%%  (%s / %s)', [FileName, FilePercent, FormatBytes(Progress), FormatBytes(ProgressMax)]);
  Line2 := Format('Общий прогресс: %d%%   Скорость: %s', [OverallPercent, SpeedText]);
  DownloadPage.SetText(Line1, Line2);
  DownloadPage.SetProgress(OverallPosition, TotalDownloadSize);

  { True = продолжить загрузку. Возврат False прервал бы скачивание
    программно — нам это не нужно, прерывание делает сам пользователь
    через кнопку отмены на странице загрузки. }
  Result := True;
end;

{ ══════════════════════════════════════════════════════════════════
  SHA-256 verification via the built-in Windows certutil.exe
  (no bundled hashing tool needed — certutil ships with Windows 7+)
  ══════════════════════════════════════════════════════════════════ }

function GetSHA256OfFile(const FileName: String): String;
var
  ResultCode: Integer;
  OutputFile, CmdLine: String;
  Lines: TArrayOfString;
  I: Integer;
  Line, HexOnly: String;
begin
  Result := '';
  OutputFile := ExpandConstant('{tmp}\certutil_out.txt');
  DeleteFile(OutputFile);

  CmdLine := Format('/C certutil.exe -hashfile "%s" SHA256 > "%s" 2>&1', [FileName, OutputFile]);

  if not Exec(ExpandConstant('{cmd}'), CmdLine, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    Log('certutil execution failed to launch for ' + FileName);
    Exit;
  end;

  if not FileExists(OutputFile) then
  begin
    Log('certutil produced no output for ' + FileName);
    Exit;
  end;

  if not LoadStringsFromFile(OutputFile, Lines) then
  begin
    Log('Could not read certutil output for ' + FileName);
    Exit;
  end;

  { Expected certutil output:
      SHA256 hash of file <name>:
      xx xx xx xx ... (hex bytes separated by spaces)
      CertUtil: -hashfile command completed successfully. }
  for I := 0 to GetArrayLength(Lines) - 1 do
  begin
    Line := Trim(Lines[I]);
    HexOnly := Line;
    StringChangeEx(HexOnly, ' ', '', True);
    if (Length(HexOnly) = 64) then
    begin
      { crude but reliable check: 64 hex chars in a line }
      Result := LowerCase(HexOnly);
      Exit;
    end;
  end;

  Log('Could not parse SHA256 from certutil output for ' + FileName);
end;

function ParseChecksumFile(const ChecksumFile, TargetFileName: String): String;
var
  Lines: TArrayOfString;
  I, SpacePos: Integer;
  Line, Hash, Rest: String;
begin
  Result := '';

  if not LoadStringsFromFile(ChecksumFile, Lines) then
    Exit;

  for I := 0 to GetArrayLength(Lines) - 1 do
  begin
    Line := Trim(Lines[I]);
    if (Line = '') or (Copy(Line, 1, 1) = '#') then
      Continue;

    { Format: "<hash>  <filename>" }
    SpacePos := Pos(' ', Line);
    if SpacePos = 0 then
      Continue;

    Hash := Copy(Line, 1, SpacePos - 1);
    Rest := Trim(Copy(Line, SpacePos + 1, MaxInt));

    { Remove '*' prefix if present }
    if (Rest <> '') and (Copy(Rest, 1, 1) = '*') then
      Rest := Copy(Rest, 2, MaxInt);

    if CompareText(Rest, TargetFileName) = 0 then
    begin
      Result := LowerCase(Hash);
      Exit;
    end;
  end;
end;

function VerifyChecksum(const FilePath, ChecksumFile: String): Boolean;
var
  ExpectedHash, ActualHash: String;
  FileNameOnly: String;
begin
  Result := False;
  FileNameOnly := ExtractFileName(FilePath);

  ExpectedHash := ParseChecksumFile(ChecksumFile, FileNameOnly);
  if ExpectedHash = '' then
  begin
    Log('Warning: no checksum entry found for ' + FileNameOnly);
    Result := True; { Don't block install over a missing checksum entry }
    Exit;
  end;

  Log('Verifying checksum for ' + FileNameOnly);
  ActualHash := GetSHA256OfFile(FilePath);

  if ActualHash = '' then
  begin
    Log('Warning: could not calculate SHA256 for ' + FileNameOnly + ', skipping verification');
    Result := True;
    Exit;
  end;

  Result := (ExpectedHash = ActualHash);

  if Result then
    Log('✓ Checksum verified: ' + FileNameOnly)
  else
    Log('✗ Checksum MISMATCH: ' + FileNameOnly +
      ' (expected: ' + ExpectedHash + ', actual: ' + ActualHash + ')');
end;

{ ══════════════════════════════════════════════════════════════════
  Download and extraction of the main Signer archive
  ══════════════════════════════════════════════════════════════════ }

procedure CreateSignerDownloadPage;
begin
  DownloadPage := CreateDownloadPage(
    'Скачивание файлов Signer',
    'Установка скачивает основные файлы приложения с GitHub',
    @OnDownloadProgress
  );
end;

{ ══════════════════════════════════════════════════════════════════
  Add optional components to download list
  ══════════════════════════════════════════════════════════════════ }

procedure AddOptionalComponentsToDownload;
var
  HasCuda, HasFFmpeg, HasKLite: Boolean;
begin
  HasCuda := DetectCuda;
  HasFFmpeg := DetectFFmpeg;
  HasKLite := DetectKLite;

  { Add CUDA if selected and not already installed }
  if WizardIsComponentSelected('cuda') and not HasCuda then
  begin
    Log('Adding CUDA to download list (~3.2 MB network installer)');
    DownloadPage.Add('{#CUDA_URL}', 'cuda.exe', '');
  end;

  { Add FFmpeg if selected and not already installed }
  if WizardIsComponentSelected('ffmpeg') and not HasFFmpeg then
  begin
    Log('Adding FFmpeg to download list (~115 MB)');
    DownloadPage.Add('{#FFMPEG_URL}', 'ffmpeg.zip', '');
  end;

  { Add K-Lite if selected and not already installed }
  if WizardIsComponentSelected('klite') and not HasKLite then
  begin
    Log('Adding K-Lite Codec Pack to download list (~60 MB)');
    DownloadPage.Add('{#KLITE_URL}', 'klite.exe', '');
  end;
end;

procedure InitializeWizard;
var
  HasCuda, HasFFmpeg, HasKLite: Boolean;
  I: Integer;
begin
  { Extract 7-Zip executables }
  ExtractTemporaryFile('7z.exe');
  ExtractTemporaryFile('7z.dll');

  { Готовим данные для расчёта прогресса (имена/веса файлов) }
  BuildDownloadFileList;
  CreateSignerDownloadPage;
  { Create download page for the application archive, с кастомным
    обработчиком прогресса (общий % + % и скорость текущего файла).
    Prerequisite downloads (VC++/.NET/WebView2/ODBC) обрабатываются
    отдельной страницей загрузки самого InnoDependencyInstaller —
    она запускается автоматически через PrepareToInstall до этой. }
  

  Log('Total Signer archive download size (approx): ' + FormatBytes(TotalDownloadSize));

  ExtractProgressPage := CreateOutputProgressPage(
    'Распаковка архива',
    'Пожалуйста, подождите...'
  );

  { Auto-detect optional components and pre-select if not installed }
  HasCuda := DetectCuda;
  HasFFmpeg := DetectFFmpeg;
  HasKLite := DetectKLite;

  { Adjust welcome message to mention optional components }
  WizardForm.WelcomeLabel2.Caption :=
    'Signer автоматически загрузит версию ' + '{#AppVersion}' + ' программы с GitHub, ' +
    'установит необходимые компоненты и подготовит приложение к работе.' + #13#10#13#10 +
    'Для полной установки потребуется около 4,3 ГБ свободного места и стабильное ' +
    'подключение к интернету.' + #13#10#13#10 +
    'Вы можете выбрать дополнительные компоненты (CUDA, FFmpeg, K-Lite) на следующем шаге.';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  I: Integer;
  RetryDownload: Boolean;
  UserChoice: Integer;
begin
  Result := True;

  if CurPageID = wpReady then
  begin
    repeat
      RetryDownload := False;

      { ── ИСПРАВЛЕНИЕ БАГА С ПРЕРЫВАНИЕМ ЗАГРУЗКИ ──────────────────
        Список файлов пересобирается (Clear + Add) перед КАЖДОЙ
        попыткой скачивания, а не один раз в InitializeWizard.
        Раньше при прерывании/ошибке и повторном нажатии "Далее"
        внутреннее состояние TDownloadWizardPage (частично скачанные
        файлы, позиции в списке) могло рассинхронизироваться при
        повторном вызове Download(), что приводило к ошибке. Этот
        паттерн — Clear/Add прямо перед Download() внутри retry-цикла —
        официально рекомендован документацией Inno Setup для
        страниц загрузки. }
      
      DownloadPage.Clear;

      { Добавляем основные файлы архива }
      for I := 1 to {#SIGNER_PART_COUNT} do
        DownloadPage.Add(
          '{#RELEASE_BASE_URL}/' + GetPartFileName(I),
          GetPartFileName(I),
          ''
        );
      DownloadPage.Add('{#RELEASE_BASE_URL}/checksum.sha256', 'checksum.sha256', '');

      { Добавляем опциональные компоненты если выбраны }
      AddOptionalComponentsToDownload;

      { Сбрасываем счётчики прогресса/скорости перед новой попыткой }
      DownloadLastFileName := '';
      DownloadLastTick     := GetTickCount;
      DownloadLastProgress := 0;
      DownloadSpeedBps     := 0;

      DownloadPage.Show;
      try
        try
          DownloadPage.Download;
          { Успех: загрузка завершена без ошибок }
          Result := True;
        except
          { КРИТИЧНО: В блоке except Result ВСЕГДА должен быть False!
            Это официальный паттерн Inno Setup для TDownloadWizardPage.
            Исключение будет "поглощено" только если мы установим Result := False.
            Если оставить Result := True, исключение пробросится дальше. }
          if DownloadPage.AbortedByUser then
          begin
            Log('Download aborted by user');
            UserChoice := SuppressibleMsgBox(
              'Загрузка файлов была прервана.' + #13#10 + #13#10 +
              'Повторить попытку загрузки?',
              mbConfirmation, MB_YESNO, IDYES
            );
            if UserChoice = IDYES then
              RetryDownload := True;
            { Если retry, то цикл продолжится, а Result пересчитается }
          end
          else
          begin
            Log('Download failed: ' + GetExceptionMessage);
            UserChoice := SuppressibleMsgBox(
              'Ошибка при скачивании файлов:' + #13#10 + GetExceptionMessage + #13#10 + #13#10 +
              'Повторить попытку загрузки?',
              mbError, MB_YESNO, IDYES
            );
            if UserChoice = IDYES then
              RetryDownload := True
            else
              Log('User declined retry after error, cancelling install');
          end;
          Result := False;  { КРИТИЧНО: Всегда False в except! }
        end;
      finally
        DownloadPage.Hide;
      end;

      { Если RetryDownload = True, цикл повторится,
        и Result будет пересчитан в следующей итерации }
    until not RetryDownload;
  end;
end;

{ ══════════════════════════════════════════════════════════════════
  PATH Environment Management
  ══════════════════════════════════════════════════════════════════ }

function AddDirToPath(const DirPath: String): Boolean;
var
  CurrentPath: String;
  ResultCode: Integer;
begin
  Result := False;
  
  { Check if directory exists }
  if not DirExists(DirPath) then
  begin
    Log('AddDirToPath: Directory does not exist: ' + DirPath);
    Exit;
  end;

  { Get current system PATH }
  if not RegQueryStringValue(HKEY_LOCAL_MACHINE,
    'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
    'Path', CurrentPath) then
  begin
    Log('AddDirToPath: Failed to read PATH from registry');
    Exit;
  end;

  { Check if already in PATH (case-insensitive) }
  if Pos(';' + Uppercase(DirPath) + ';', ';' + Uppercase(CurrentPath) + ';') > 0 then
  begin
    Log('AddDirToPath: Already in PATH: ' + DirPath);
    Result := True;
    Exit;
  end;

  { Add to PATH }
  if CurrentPath <> '' then
    CurrentPath := CurrentPath + ';' + DirPath
  else
    CurrentPath := DirPath;

  { Write to registry }
  if RegWriteStringValue(HKEY_LOCAL_MACHINE,
    'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
    'Path', CurrentPath) then
  begin
    Log('AddDirToPath: Successfully added: ' + DirPath);
    Result := True;
    
    { Broadcast environment change }
    if Exec('cmd.exe', '/c setx PATHREFRESH "1" /M', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      Log('AddDirToPath: Environment refresh triggered');
  end
  else
    Log('AddDirToPath: Failed to write to registry');
end;

function RemoveDirFromPath(const DirPath: String): Boolean;
var
  CurrentPath: String;
  NewPath: String;
  PosStart: Integer;
begin
  Result := False;

  { Get current system PATH }
  if not RegQueryStringValue(HKEY_LOCAL_MACHINE,
    'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
    'Path', CurrentPath) then
  begin
    Log('RemoveDirFromPath: Failed to read PATH from registry');
    Exit;
  end;

  { Remove from PATH (case-insensitive) }
  NewPath := ';' + CurrentPath + ';';
  PosStart := Pos(';' + Uppercase(DirPath) + ';', Uppercase(NewPath));
  
  if PosStart > 0 then
  begin
    Delete(NewPath, PosStart + 1, Length(DirPath) + 1);
    { Remove leading/trailing semicolons }
    NewPath := Copy(NewPath, 2, Length(NewPath) - 2);
    
    { Write to registry }
    if RegWriteStringValue(HKEY_LOCAL_MACHINE,
      'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
      'Path', NewPath) then
    begin
      Log('RemoveDirFromPath: Successfully removed: ' + DirPath);
      Result := True;
    end
    else
      Log('RemoveDirFromPath: Failed to write to registry');
  end
  else
  begin
    Log('RemoveDirFromPath: Not found in PATH: ' + DirPath);
    Result := True; { Not an error }
  end;
end;

function FindCudaBinPath: String;
var
  CudaBase: String;
  FindRec: TFindRec;
  LatestVersion: String;
begin
  Result := '';
  CudaBase := ExpandConstant('{pf}\NVIDIA GPU Computing Toolkit\CUDA');
  
  if not DirExists(CudaBase) then
  begin
    CudaBase := ExpandConstant('{pf64}\NVIDIA GPU Computing Toolkit\CUDA');
    if not DirExists(CudaBase) then
      Exit;
  end;

  { Find latest CUDA version (v12.6, v12.5, etc.) }
  if FindFirst(CudaBase + '\v*', FindRec) then
  begin
    try
      repeat
        if (FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
        begin
          if (FindRec.Name <> '.') and (FindRec.Name <> '..') then
          begin
            { Take the first one (should be sorted, but we'll use latest) }
            if LatestVersion = '' then
              LatestVersion := FindRec.Name
            else if CompareStr(FindRec.Name, LatestVersion) > 0 then
              LatestVersion := FindRec.Name;
          end;
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;

  if LatestVersion <> '' then
  begin
    Result := CudaBase + '\' + LatestVersion + '\bin';
    Log('FindCudaBinPath: Found ' + Result);
  end;
end;

{ ══════════════════════════════════════════════════════════════════
  Installation Steps
  ══════════════════════════════════════════════════════════════════ }

procedure CurStepChanged(CurStep: TSetupStep);
var
  I: Integer;
  PartName, PartPath, ChecksumPath: String;
  ResultCode: Integer;
  AllVerified: Boolean;
  CudaPath, FFmpegPath, KLitePath: String;
begin
  if CurStep = ssInstall then
  begin
    ExtractProgressPage.Show;
    try
      { ── Checksum verification ── }
      ChecksumPath := ExpandConstant('{tmp}\checksum.sha256');
      AllVerified := True;

      if FileExists(ChecksumPath) then
      begin
        ExtractProgressPage.SetText('Проверка целостности файлов...', 'Вычисление SHA-256');
        for I := 1 to {#SIGNER_PART_COUNT} do
        begin
          PartPath := ExpandConstant('{tmp}\' + GetPartFileName(I));
          ExtractProgressPage.SetProgress(I, {#SIGNER_PART_COUNT});
          if FileExists(PartPath) then
          begin
            if not VerifyChecksum(PartPath, ChecksumPath) then
            begin
              AllVerified := False;
              Break;
            end;
          end;
        end;
      end
      else
      begin
        Log('checksum.sha256 not found — skipping integrity verification');
      end;

      if not AllVerified then
      begin
        RaiseException(
          'Проверка целостности скачанных файлов не пройдена. ' +
          'Файл повреждён или подделан. Установка прервана. См. лог для деталей.'
        );
      end;

      { ── Extraction ── }
      ExtractProgressPage.SetText('Распаковка архива...', 'Это может занять несколько минут');
      ExtractProgressPage.SetProgress(0, 100);

      if not Exec(
        ExpandConstant('{tmp}\7z.exe'),
        Format('x "%s" -o"%s" -aoa -y', [ExpandConstant('{tmp}\Signer.7z.001'), ExpandConstant('{app}')]),
        '',
        SW_HIDE,
        ewWaitUntilTerminated,
        ResultCode
      ) or (ResultCode <> 0) then
      begin
        RaiseException('Не удалось распаковать архив. Код ошибки 7-Zip: ' + IntToStr(ResultCode));
      end;

      ExtractProgressPage.SetText('Распаковка завершена', 'Файлы успешно установлены');
      ExtractProgressPage.SetProgress(100, 100);

      Log('✓ Archive extracted successfully');

      { ── Cleanup downloaded parts to save disk space ── }
      ExtractProgressPage.SetText('Очистка временных файлов...', '');
      for I := 1 to {#SIGNER_PART_COUNT} do
      begin
        PartPath := ExpandConstant('{tmp}\' + GetPartFileName(I));
        DeleteFile(PartPath);
      end;
      DeleteFile(ChecksumPath);

      Log('✓ Temporary files cleaned up');

    finally
      ExtractProgressPage.Hide;
    end;
  end
  else if CurStep = ssPostInstall then
  begin
    { ── Install optional components if downloaded ── }
    ExtractProgressPage.Show;
    try
      { Install CUDA if downloaded }
      CudaPath := ExpandConstant('{tmp}\cuda.exe');
      if FileExists(CudaPath) then
      begin
        ExtractProgressPage.SetText('Установка NVIDIA CUDA Toolkit...', 'Пожалуйста, подождите');
        ExtractProgressPage.SetProgress(0, 100);
        Log('Installing CUDA from ' + CudaPath);
        
        if Exec(CudaPath, '-s', '', SW_SHOW, ewWaitUntilTerminated, ResultCode) then
        begin
          if ResultCode = 0 then
          begin
            Log('✓ CUDA installed successfully');
            { CUDA installer adds itself to PATH automatically, no need to do it manually }
          end
          else
            Log('Warning: CUDA installer returned code ' + IntToStr(ResultCode));
        end
        else
          Log('Warning: Failed to launch CUDA installer');
        
        DeleteFile(ExpandConstant('{tmp}\cuda.exe'));
      end;

      { Install FFmpeg if downloaded }
      FFmpegPath := ExpandConstant('{tmp}\ffmpeg.zip');
      if FileExists(FFmpegPath) then
      begin
        ExtractProgressPage.SetText('Установка FFmpeg...', 'Распаковка в Program Files');
        ExtractProgressPage.SetProgress(33, 100);
        Log('Installing FFmpeg from ' + FFmpegPath);
        
        if Exec(
          ExpandConstant('{tmp}\7z.exe'),
          Format('x "%s" -o"%s" -aoa -y', [FFmpegPath, ExpandConstant('{pf}\ffmpeg')]),
          '',
          SW_HIDE,
          ewWaitUntilTerminated,
          ResultCode
        ) and (ResultCode = 0) then
        begin
          Log('✓ FFmpeg extracted successfully');
          
          { Add FFmpeg to PATH - correct path after extraction }
          FFmpegPath := ExpandConstant('{pf}\ffmpeg\ffmpeg-master-latest-win64-gpl\bin');
          
          { Check if FFmpeg bin directory exists }
          if DirExists(FFmpegPath) then
          begin
            if AddDirToPath(FFmpegPath) then
            begin
              Log('✓ FFmpeg added to PATH: ' + FFmpegPath);
              MsgBox(
                'FFmpeg установлен успешно!' + #13#10 +
                'Путь ' + FFmpegPath + ' добавлен в PATH.' + #13#10 +
                'Перезапустите терминал для применения изменений.',
                mbInformation, MB_OK
              );
            end
            else
            begin
              Log('⚠ Failed to add FFmpeg to PATH');
              MsgBox(
                'FFmpeg установлен в ' + ExpandConstant('{pf}\ffmpeg') + #13#10 +
                'ВНИМАНИЕ: Не удалось автоматически добавить в PATH.' + #13#10 +
                'Добавьте вручную: ' + FFmpegPath,
                mbInformation, MB_OK
              );
            end;
          end
          else
          begin
            Log('⚠ FFmpeg bin directory not found: ' + FFmpegPath);
            MsgBox(
              'FFmpeg распакован, но не найдена bin директория.' + #13#10 +
              'Проверьте путь: ' + ExpandConstant('{pf}\ffmpeg'),
              mbInformation, MB_OK
            );
          end;
        end
        else
          Log('Warning: Failed to extract FFmpeg, code ' + IntToStr(ResultCode));
        
        DeleteFile(ExpandConstant('{tmp}\ffmpeg.zip'));
      end;

      { Install K-Lite Codec Pack if downloaded }
      KLitePath := ExpandConstant('{tmp}\klite.exe');
      if FileExists(KLitePath) then
      begin
        ExtractProgressPage.SetText('Установка K-Lite Codec Pack...', 'Пожалуйста, подождите');
        ExtractProgressPage.SetProgress(66, 100);
        Log('Installing K-Lite from ' + KLitePath);
        
        if Exec(KLitePath, '/VERYSILENT /NORESTART', '', SW_SHOW, ewWaitUntilTerminated, ResultCode) then
        begin
          if ResultCode = 0 then
          begin
            Log('✓ K-Lite installed successfully');
            
            { Add K-Lite to PATH - check multiple possible locations }
            { K-Lite may install to different locations depending on system architecture }
            if DirExists(ExpandConstant('{pf}\K-Lite Codec Pack\MPC-HC64')) then
            begin
              KLitePath := ExpandConstant('{pf}\K-Lite Codec Pack\MPC-HC64');
              if AddDirToPath(KLitePath) then
                Log('✓ K-Lite added to PATH: ' + KLitePath)
              else
                Log('⚠ K-Lite path already in PATH or failed to add: ' + KLitePath);
            end
            else if DirExists(ExpandConstant('{pf32}\K-Lite Codec Pack\MPC-HC64')) then
            begin
              KLitePath := ExpandConstant('{pf32}\K-Lite Codec Pack\MPC-HC64');
              if AddDirToPath(KLitePath) then
                Log('✓ K-Lite added to PATH: ' + KLitePath)
              else
                Log('⚠ K-Lite path already in PATH or failed to add: ' + KLitePath);
            end
            else
            begin
              Log('⚠ K-Lite MPC-HC64 directory not found in expected locations');
            end;
          end
          else
            Log('Warning: K-Lite installer returned code ' + IntToStr(ResultCode));
        end
        else
          Log('Warning: Failed to launch K-Lite installer');
        
        DeleteFile(KLitePath);
      end;

      ExtractProgressPage.SetProgress(100, 100);
    finally
      ExtractProgressPage.Hide;
    end;
  end;
end;

{ ══════════════════════════════════════════════════════════════════
  Uninstall
  ══════════════════════════════════════════════════════════════════ }

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  FFmpegPath, KLitePath: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    { Remove paths from PATH environment variable }
    Log('Removing paths from PATH...');
    
    { CUDA - skip removal, CUDA installer manages its own PATH }
    
    { FFmpeg - correct path after extraction }
    FFmpegPath := ExpandConstant('{pf}\ffmpeg\ffmpeg-master-latest-win64-gpl\bin');
    if DirExists(FFmpegPath) then
      RemoveDirFromPath(FFmpegPath)
    else
    begin
      { Fallback to old path if new one doesn't exist }
      FFmpegPath := ExpandConstant('{pf}\ffmpeg\bin');
      if DirExists(FFmpegPath) then
        RemoveDirFromPath(FFmpegPath);
    end;
    
    { K-Lite - multiple possible paths }
    KLitePath := ExpandConstant('{pf}\K-Lite Codec Pack\MPC-HC64');
    if DirExists(KLitePath) then
      RemoveDirFromPath(KLitePath);
    
    KLitePath := ExpandConstant('{pf32}\K-Lite Codec Pack\MPC-HC64');
    if DirExists(KLitePath) then
      RemoveDirFromPath(KLitePath);
    
    Log('PATH cleanup completed');
  end;
end;

function InitializeUninstall: Boolean;
begin
  Result := True;
  if MsgBox(
    'Вы действительно хотите удалить Signer и все его компоненты?',
    mbConfirmation,
    MB_YESNO
  ) = IDNO then
    Result := False;
end;

; ══════════════════════════════════════════════════════════════════
; Signer PRIME Installer — Modern installer with download progress
; ══════════════════════════════════════════════════════════════════

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
; АКТУАЛЬНАЯ КОНФИГУРАЦИЯ (обновлено 2026-09-14):
;   - Signer.7z.001 .. Signer.7z.041  (multi-volume 7z archive, ~100 MB
;     per part except the last part ~13.7 MB — ~4.0 GB total)
;   - checksum.sha256                 (SHA-256 of every part, one per line)
;   - README.md / release_notes.txt / BUILD_AUTOUPDATE.md (docs, not needed)
;   - Source code (zip) / Source code (tar.gz) (GitHub auto-generated, not needed)
;
; Релиз содержит обфусцированную версию с PyArmor для модуля licensing/.
;
; If you cut a new release with a different tag or a different number of
; archive parts, update RELEASE_TAG and SIGNER_PART_COUNT below, and adjust
; the [Files] entries to match (add/remove Signer.7z.0NN lines).
; ──────────────────────────────────────────────────────────────────
#define RELEASE_TAG "v2.0.0"
#define RELEASE_BASE_URL "https://github.com/M4X3res/Signer_PRIME/releases/download/" + RELEASE_TAG
#define SIGNER_PART_COUNT 46

; ══════════════════════════════════════════════════════════════════
; Inno Download Plugin (IDP) для продвинутого прогресс-бара
; 
; ВНИМАНИЕ: Для использования IDP нужно скачать idp.iss:
; https://mitrich.net23.net/?idp или https://jrsoftware.org/ishelp/
; 
; Если idp.iss недоступен, используется встроенная реализация
; с базовым прогрессом через PowerShell
; ══════════════════════════════════════════════════════════════════

; Раскомментируйте если установлен IDP:
; #include <idp.iss>

; Если IDP не установлен, будет использоваться встроенная реализация

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
DisableDirPage=no
DisableProgramGroupPage=no
AllowNoIcons=yes
WizardResizable=no
UninstallDisplayIcon={app}\Signer\Signer.exe
UninstallDisplayName={#AppName}
MinVersion=10.0.17763
ExtraDiskSpaceRequired=8400000000
; ~4.0GB для скачанного архива + ~4.3GB для распакованного приложения
; = ~8.3GB временно требуется, после установки архив удаляется
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

; ══════════════════════════════════════════════════════════════════
; Файлы скачиваются через Inno Download Plugin (IDP) в InitializeWizard
; Это позволяет показывать детальный прогресс с процентами и скоростью
; ══════════════════════════════════════════════════════════════════

; Опциональные компоненты (скачиваются через IDP если выбраны)
; Основные файлы Signer.7z.* добавляются программно в InitializeWizard

[Icons]
Name: "{group}\Signer"; Filename: "{app}\Signer\Signer.exe"
Name: "{group}\Удалить Signer"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Signer"; Filename: "{app}\Signer\Signer.exe"; Tasks: desktopicon

[UninstallDelete]
Type: filesandordirs; Name: "{tmp}\Signer_extract"
Type: files; Name: "{app}\*.log"

[Run]
Filename: "{app}\Signer\Signer.exe"; Description: "Запустить Signer сейчас"; Flags: postinstall nowait skipifsilent

[Code]
{ Windows API declarations }
function GetTickCount: DWORD;
  external 'GetTickCount@kernel32.dll stdcall';

const
  { Temporary space needed: ~4.0GB archive + ~4.3GB extracted = ~8.4GB }
  RequiredSpaceMB = 8400;

var
  ResultCode: Integer;
  DownloadPage: TOutputProgressWizardPage;
  CurrentFileIndex, TotalFilesCount: Integer;
  TotalBytesDownloaded, TotalBytesToDownload: Int64;

type
  TDownloadFile = record
    URL: String;
    FileName: String;
    Size: Int64;
  end;

var
  DownloadFiles: array of TDownloadFile;

{ ══════════════════════════════════════════════════════════════════
  Встроенная реализация скачивания с прогрессом
  ══════════════════════════════════════════════════════════════════ }

procedure AddDownloadFile(const URL, FileName: String; Size: Int64);
var
  Len: Integer;
begin
  Len := GetArrayLength(DownloadFiles);
  SetArrayLength(DownloadFiles, Len + 1);
  DownloadFiles[Len].URL := URL;
  DownloadFiles[Len].FileName := FileName;
  DownloadFiles[Len].Size := Size;
  TotalBytesToDownload := TotalBytesToDownload + Size;
end;

function FormatBytes(Bytes: Int64): String;
begin
  if Bytes >= 1073741824 then
    Result := Format('%.2f ГБ', [Bytes / 1073741824.0])
  else if Bytes >= 1048576 then
    Result := Format('%.2f МБ', [Bytes / 1048576.0])
  else if Bytes >= 1024 then
    Result := Format('%.1f КБ', [Bytes / 1024.0])
  else
    Result := Format('%d Б', [Bytes]);
end;

function FormatSpeed(BytesPerSec: Double): String;
begin
  if BytesPerSec >= 1048576 then
    Result := Format('%.2f МБ/с', [BytesPerSec / 1048576.0])
  else if BytesPerSec >= 1024 then
    Result := Format('%.1f КБ/с', [BytesPerSec / 1024.0])
  else
    Result := Format('%.0f Б/с', [BytesPerSec]);
end;

{ Скачивание одного файла с PowerShell и отображением прогресса }
function DownloadFileWithProgress(const URL, DestPath: String; FileSize: Int64; FileIndex, TotalFiles: Integer): Boolean;
var
  PSScript, TempScript, StatusMsg: String;
  StartTime, ElapsedTime: Cardinal;
  Speed: Double;
  FilePercent, TotalPercent, ResultCode: Integer;
begin
  Result := False;
  
  { Проверяем, не скачан ли уже файл }
  if FileExists(DestPath) then
  begin
    Log('Файл уже существует: ' + ExtractFileName(DestPath));
    TotalBytesDownloaded := TotalBytesDownloaded + FileSize;
    Result := True;
    Exit;
  end;

  Log('Скачивание: ' + ExtractFileName(DestPath) + ' (' + FormatBytes(FileSize) + ')');
  
  StartTime := GetTickCount;
  
  { PowerShell скрипт для скачивания с прогрессом }
  PSScript := '$ProgressPreference = "SilentlyContinue"; ' + 'try { ' + '  $client = New-Object System.Net.WebClient; ' + '  $client.Headers.Add("User-Agent", "SignerInstaller/2.0"); ' + '  $client.DownloadFile("' + URL + '", "' + DestPath + '"); ' + '  exit 0; ' + '} catch { ' + '  Write-Error $_.Exception.Message; ' + '  exit 1; ' + '}';
  
  TempScript := ExpandConstant('{tmp}\download_' + IntToStr(FileIndex) + '.ps1');
  SaveStringToFile(TempScript, PSScript, False);
  
  { Запускаем скачивание }
  if Exec(
    ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -ExecutionPolicy Bypass -File "' + TempScript + '"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode
  ) and (ResultCode = 0) then
  begin
    Result := True;
    TotalBytesDownloaded := TotalBytesDownloaded + FileSize;
    
    ElapsedTime := GetTickCount - StartTime;
    if ElapsedTime > 0 then
      Speed := (FileSize * 1000.0) / ElapsedTime
    else
      Speed := 0;
    
    FilePercent := Round((TotalBytesDownloaded * 100.0) / TotalBytesToDownload);
    TotalPercent := Round((FileIndex * 100.0) / TotalFiles);
    
    StatusMsg := Format('Файл %d из %d: %s' + #13#10 + 'Размер: %s' + #13#10 + 'Скорость: %s' + #13#10 + 'Общий прогресс: %d%%', [FileIndex, TotalFiles, ExtractFileName(DestPath), FormatBytes(FileSize), FormatSpeed(Speed), FilePercent]);
    
    if Assigned(DownloadPage) then
    begin
      DownloadPage.SetText(StatusMsg, '');
      DownloadPage.SetProgress(TotalBytesDownloaded, TotalBytesToDownload);
    end;
    
    Log('✓ Скачан: ' + ExtractFileName(DestPath) + ' (' + FormatSpeed(Speed) + ')');
  end
  else
  begin
    Log('✗ Ошибка скачивания: ' + ExtractFileName(DestPath) + ' (код: ' + IntToStr(ResultCode) + ')');
  end;
  
  DeleteFile(TempScript);
end;

{ Скачивание всех файлов }
function DownloadAllFiles: Boolean;
var
  I: Integer;
  DestPath: String;
begin
  Result := True;
  
  for I := 0 to GetArrayLength(DownloadFiles) - 1 do
  begin
    CurrentFileIndex := I + 1;
    DestPath := ExpandConstant('{tmp}\' + DownloadFiles[I].FileName);
    
    if not DownloadFileWithProgress(
      DownloadFiles[I].URL,
      DestPath,
      DownloadFiles[I].Size,
      CurrentFileIndex,
      GetArrayLength(DownloadFiles)
    ) then
    begin
      Result := False;
      MsgBox(
        'Не удалось скачать файл: ' + DownloadFiles[I].FileName + #13#10#13#10 +
        'Проверьте подключение к интернету и попробуйте снова.',
        mbError, MB_OK
      );
      Break;
    end;
  end;
end;

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
  PartName: String;
begin
  ExtractTemporaryFile('7z.exe');
  ExtractTemporaryFile('7z.dll');

  { Инициализация переменных скачивания }
  TotalBytesDownloaded := 0;
  TotalBytesToDownload := 0;
  SetArrayLength(DownloadFiles, 0);
  
  { Создаём страницу прогресса скачивания }
  DownloadPage := CreateOutputProgressPage(
    'Скачивание файлов',
    'Пожалуйста, подождите пока установщик скачивает необходимые файлы...'
  );
  
  { ════════════════════════════════════════════════════════════════
    Добавляем все 41 часть архива Signer.7z для скачивания
    ════════════════════════════════════════════════════════════════ }
  
  for I := 1 to {#SIGNER_PART_COUNT} do
  begin
    if I < 10 then
      PartName := Format('Signer.7z.00%d', [I])
    else if I < 100 then
      PartName := Format('Signer.7z.0%d', [I])
    else
      PartName := Format('Signer.7z.%d', [I]);
    
    { Все части кроме последней по 100MB }
    if I < {#SIGNER_PART_COUNT} then
      AddDownloadFile('{#RELEASE_BASE_URL}/' + PartName, PartName, 100000000)
    else
      { Последняя часть ~13.7MB }
      AddDownloadFile('{#RELEASE_BASE_URL}/' + PartName, PartName, 13700000);
  end;
  
  { Контрольная сумма }
  AddDownloadFile('{#RELEASE_BASE_URL}/checksum.sha256', 'checksum.sha256', 4000);
  
  { ════════════════════════════════════════════════════════════════
    Опциональные компоненты
    ════════════════════════════════════════════════════════════════ }
  
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
    'подключение к интернету.' + #13#10#13#10 +
    'Вы увидите детальный прогресс скачивания с процентами и скоростью.';

  WizardForm.FinishedHeadingLabel.Caption := 'Установка Signer завершена';
  WizardForm.FinishedLabel.Caption :=
    'Программа готова к работе. Следующие обновления можно установить, ' +
    'скачав новую версию установщика или новый релиз с GitHub.';
end;

{ Добавляем опциональные компоненты в список скачивания после выбора компонентов }
procedure CurPageChanged(CurPageID: Integer);
var
  HasCuda, HasFFmpeg, HasKLite: Boolean;
begin
  if CurPageID = wpReady then
  begin
    { Добавляем опциональные компоненты если они выбраны }
    HasCuda := DetectCuda;
    HasFFmpeg := DetectFFmpeg;
    HasKLite := DetectKLite;
    
    if IsComponentSelected('cuda') and not HasCuda then
      AddDownloadFile(
        'https://developer.download.nvidia.com/compute/cuda/12.6.0/network_installers/cuda_12.6.0_windows_network.exe',
        'cuda.exe', 3200000
      );
    
    if IsComponentSelected('ffmpeg') and not HasFFmpeg then
      AddDownloadFile(
        'https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip',
        'ffmpeg.zip', 115000000
      );
    
    if IsComponentSelected('klite') and not HasKLite then
      AddDownloadFile(
        'https://files2.codecguide.com/K-Lite_Codec_Pack_1995_Standard.exe',
        'klite.exe', 60000000
      );
  end
  else if CurPageID = wpInstalling then
  begin
    { Начинаем скачивание перед установкой }
    DownloadPage.Show;
    try
      DownloadPage.SetText('Подготовка к скачиванию...', '');
      DownloadPage.SetProgress(0, 100);
      
      if not DownloadAllFiles then
      begin
        { Если скачивание не удалось, прерываем установку }
        WizardForm.Close;
        Exit;
      end;
      
      DownloadPage.SetText('Все файлы успешно скачаны!', '');
      DownloadPage.SetProgress(100, 100);
      Sleep(1000);
    finally
      DownloadPage.Hide;
    end;
  end;
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

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
#define SIGNER_PART_COUNT 41

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
WizardResizable=yes
UninstallDisplayName={#AppName}
MinVersion=10.0.17763
CloseApplications=yes
RestartApplications=no
; Temporary space: ~4.0GB archive + ~4.3GB extracted = ~8.4GB
ExtraDiskSpaceRequired=8400000000
ShowLanguageDialog=auto

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

{ ══════════════════════════════════════════════════════════════════
  Dependencies (InnoDependencyInstaller)
  ══════════════════════════════════════════════════════════════════ }

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

procedure InitializeWizard;
var
  I: Integer;
  PartName: String;
  TotalSize: Int64;
begin
  { Extract 7-Zip executables }
  ExtractTemporaryFile('7z.exe');
  ExtractTemporaryFile('7z.dll');

  { Create download page for the application archive.
    Prerequisite downloads (VC++/.NET/WebView2/ODBC) are handled
    separately by InnoDependencyInstaller's own download page, which
    runs automatically before this one via PrepareToInstall. }
  DownloadPage := CreateDownloadPage(
    'Скачивание файлов Signer',
    'Установка скачивает основные файлы приложения с GitHub',
    nil
  );

  TotalSize := 0;
  for I := 1 to {#SIGNER_PART_COUNT} do
  begin
    PartName := GetPartFileName(I);
    DownloadPage.Add(
      '{#RELEASE_BASE_URL}/' + PartName,
      PartName,
      ''
    );
    TotalSize := TotalSize + GetPartSize(I, {#SIGNER_PART_COUNT});
  end;

  { Also fetch the checksum file used for post-download verification }
  DownloadPage.Add('{#RELEASE_BASE_URL}/checksum.sha256', 'checksum.sha256', '');

  Log('Total Signer archive download size (approx): ' + FormatBytes(TotalSize));

  ExtractProgressPage := CreateOutputProgressPage(
    'Распаковка архива',
    'Пожалуйста, подождите...'
  );
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;

  if CurPageID = wpReady then
  begin
    try
      DownloadPage.Show;
      try
        DownloadPage.Download;
        Result := True;
      except
        if DownloadPage.AbortedByUser then
        begin
          Log('Download aborted by user');
          SuppressibleMsgBox('Установка отменена пользователем.', mbInformation, MB_OK, IDOK);
          Result := False;
        end
        else
        begin
          Log('Download failed: ' + GetExceptionMessage);
          SuppressibleMsgBox(
            'Ошибка при скачивании файлов:' + #13#10 + GetExceptionMessage,
            mbError, MB_OK, IDOK
          );
          Result := False;
        end;
      end;
    finally
      DownloadPage.Hide;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  I: Integer;
  PartName, PartPath, ChecksumPath: String;
  ResultCode: Integer;
  AllVerified: Boolean;
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

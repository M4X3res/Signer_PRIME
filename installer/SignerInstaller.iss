; ══════════════════════════════════════════════════════════════════
; Signer PRIME Professional Installer
; Uses Inno Setup's built-in download system with proper progress
; ══════════════════════════════════════════════════════════════════

#define AppName "Signer"
#define AppVersion "2.0.0"
#define Publisher "M4X3Corp"
#define PublisherURL "https://github.com/M4X3res/Signer_PRIME"
#define SupportURL "https://github.com/M4X3res/Signer_PRIME/issues"
#define UpdatesURL "https://github.com/M4X3res/Signer_PRIME/releases"

; ──────────────────────────────────────────────────────────────────
; Release configuration
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
OutputDir=installer\Output
OutputBaseFilename=SignerInstaller
WizardStyle=modern
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
Compression=lzma2
SolidCompression=yes
; SetupIconFile=assets\ico.ico
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableDirPage=no
DisableProgramGroupPage=no
AllowNoIcons=yes
WizardResizable=yes
UninstallDisplayIcon={app}\Signer\Signer.exe
UninstallDisplayName={#AppName}
MinVersion=10.0.17763
; Temporary space: ~4.0GB archive + ~4.3GB extracted = ~8.4GB
ExtraDiskSpaceRequired=8400000000

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительно:"; Flags: unchecked

[Files]
Source: "7z.exe"; Flags: dontcopy noencryption
Source: "7z.dll"; Flags: dontcopy noencryption

[Icons]
Name: "{group}\Signer"; Filename: "{app}\Signer\Signer.exe"
Name: "{group}\Удалить Signer"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Signer"; Filename: "{app}\Signer\Signer.exe"; Tasks: desktopicon

[UninstallDelete]
Type: filesandordirs; Name: "{tmp}\Signer_extract"
Type: filesandordirs; Name: "{tmp}\Signer_parts"
Type: files; Name: "{app}\*.log"

[Run]
Filename: "{app}\Signer\Signer.exe"; Description: "Запустить Signer сейчас"; Flags: postinstall nowait skipifsilent

[Code]
var
  DownloadPage: TDownloadWizardPage;
  ExtractProgressPage: TOutputProgressWizardPage;

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
  { Все части кроме последней по 100MB }
  if PartIndex < TotalParts then
    Result := 100000000
  else
    { Последняя часть ~13.7MB }
    Result := 13700000;
end;

{ ══════════════════════════════════════════════════════════════════
  SHA-256 verification (simplified - requires external tool)
  For production use, consider using a dedicated checksum tool
  ══════════════════════════════════════════════════════════════════ }

function GetSHA256OfFile(const FileName: String): String;
begin
  { SHA256 calculation via OLE doesn't work reliably in Inno Setup }
  { For now, we skip checksum verification }
  { TODO: Add external SHA256 tool (e.g., certutil.exe) }
  Result := '';
  Log('SHA256 verification not implemented yet');
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
  FileName: String;
begin
  Result := False;
  FileName := ExtractFileName(FilePath);
  
  ExpectedHash := ParseChecksumFile(ChecksumFile, FileName);
  if ExpectedHash = '' then
  begin
    Log('Warning: No checksum found for ' + FileName);
    Result := True; // Allow installation if checksum not found
    Exit;
  end;

  Log('Verifying checksum for ' + FileName);
  ActualHash := GetSHA256OfFile(FilePath);
  
  if ActualHash = '' then
  begin
    Log('Warning: Could not calculate SHA256 for ' + FileName);
    Result := True; // Allow installation if calculation failed
    Exit;
  end;

  Result := (ExpectedHash = ActualHash);
  
  if Result then
    Log('✓ Checksum verified: ' + FileName)
  else
    Log('✗ Checksum mismatch: ' + FileName + ' (expected: ' + ExpectedHash + ', actual: ' + ActualHash + ')');
end;

{ ══════════════════════════════════════════════════════════════════
  Download and extraction
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

  { Create download page }
  DownloadPage := CreateDownloadPage(
    'Скачивание файлов',
    'Установка скачивает необходимые файлы с GitHub',
    nil
  );
  
  { Add all archive parts }
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
  
  Log('Total download size: ' + FormatBytes(TotalSize));
  
  { Create extraction progress page }
  ExtractProgressPage := CreateOutputProgressPage(
    'Распаковка архива',
    'Пожалуйста, подождите...'
  );
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  
  { Start download when user clicks Next on the Ready page }
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
          SuppressibleMsgBox('Ошибка при скачивании файлов:' + #13#10 + GetExceptionMessage, mbError, MB_OK, IDOK);
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
  PartName, PartPath: String;
  ResultCode: Integer;
  ExtractCmd: String;
begin
  if CurStep = ssInstall then
  begin
    ExtractProgressPage.Show;
    try
      { Skip checksum verification for now - not implemented }
      { TODO: Add external SHA256 verification tool }
      Log('Skipping checksum verification (not implemented)');
      
      { Extract the multi-volume 7z archive }
      ExtractProgressPage.SetText('Распаковка архива...', 'Это может занять несколько минут');
      ExtractProgressPage.SetProgress(0, 100);
      
      ExtractCmd := Format('"%s" x "%s" -o"%s" -aoa -y', [ExpandConstant('{tmp}\7z.exe'), ExpandConstant('{tmp}\Signer.7z.001'), ExpandConstant('{app}')]);
      
      Log('Executing: ' + ExtractCmd);
      
      if not Exec(
        ExpandConstant('{tmp}\7z.exe'),
        Format('x "%s" -o"%s" -aoa -y', [ExpandConstant('{tmp}\Signer.7z.001'), ExpandConstant('{app}')]),
        '',
        SW_HIDE,
        ewWaitUntilTerminated,
        ResultCode
      ) or (ResultCode <> 0) then
      begin
        RaiseException('Failed to extract archive. 7-Zip error code: ' + IntToStr(ResultCode));
      end;
      
      ExtractProgressPage.SetText('Распаковка завершена', 'Файлы успешно установлены');
      ExtractProgressPage.SetProgress(100, 100);
      
      Log('✓ Archive extracted successfully');
      
      { Clean up downloaded parts to save space }
      ExtractProgressPage.SetText('Очистка временных файлов...', '');
      for I := 1 to {#SIGNER_PART_COUNT} do
      begin
        PartPath := ExpandConstant('{tmp}\' + GetPartFileName(I));
        DeleteFile(PartPath);
      end;
      
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

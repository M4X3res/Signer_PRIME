// Included inside [Code]. Only the directory created by this setup is cleaned.
var
  SignerWorkDir: String;
  SignerWorkParent: String;

function WorkspaceTempFileName(PathName, Prefix: String; Unique: Cardinal;
  Buffer: String): Cardinal;
  external 'GetTempFileNameW@kernel32.dll stdcall';

function GetWorkDir(Param: String): String;
begin
  if SignerWorkDir = '' then
  begin
    SignerWorkParent := AddBackslash(ExpandConstant('{app}'));
    if not ForceDirectories(SignerWorkParent) then
      RaiseException('Не удалось создать каталог установки: ' + SignerWorkParent);
    SetLength(SignerWorkDir, 260);
    if WorkspaceTempFileName(SignerWorkParent, 'sgn', 0, SignerWorkDir) = 0 then
      RaiseException('Не удалось выделить временную папку на выбранном диске');
    SetLength(SignerWorkDir, Pos(#0, SignerWorkDir) - 1);
    if not DeleteFile(SignerWorkDir) then
      RaiseException('Не удалось подготовить временную папку');
    if not CreateDir(SignerWorkDir) then
      RaiseException('Не удалось создать временную папку: ' + SignerWorkDir);
    if not SaveStringToFile(AddBackslash(SignerWorkDir) + '.signer-setup-owned', 'Signer workspace', False) then
      RaiseException('Не удалось записать временную папку');
    Log('Signer download/extraction directory: ' + SignerWorkDir);
  end;
  Result := SignerWorkDir;
end;

procedure DeinitializeSetup;
begin
  if (SignerWorkDir <> '') and (SignerWorkParent <> '') and
     (CompareText(ExtractFilePath(SignerWorkDir), SignerWorkParent) = 0) and
     FileExists(AddBackslash(SignerWorkDir) + '.signer-setup-owned') then
    if not DelTree(SignerWorkDir, True, True, True) then
      Log('Could not remove installer workspace: ' + SignerWorkDir);
end;

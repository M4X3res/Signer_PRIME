
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
const
  ReleaseTag='v2.0.0';
  Repo='M4X3res/Signer_PRIME';

function GetTickCount64: Int64;
external 'GetTickCount64@kernel32 stdcall';

var
  DownloadPage: TDownloadWizardPage;
  StartTick:Int64;
  CurrentFile:Integer;
  TotalFiles:Integer;
  ResultCode:Integer;

function DetectCuda:Boolean;
begin
  Result:=DirExists(ExpandConstant('{pf}\NVIDIA GPU Computing Toolkit\CUDA'))
       or DirExists(ExpandConstant('{pf64}\NVIDIA GPU Computing Toolkit\CUDA'));
end;

function DetectFFmpeg:Boolean;
begin
  Result:=FileExists(ExpandConstant('{pf}\ffmpeg\bin\ffmpeg.exe'))
       or FileExists(ExpandConstant('{pf64}\ffmpeg\bin\ffmpeg.exe'));
end;

function DetectKLite:Boolean;
begin
  Result:=RegKeyExists(HKLM,'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\K-Lite Codec Pack_is1')
       or RegKeyExists(HKLM64,'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\K-Lite Codec Pack_is1');
end;

function OnProgress(const Url,FileName:String;const Progress,ProgressMax:Int64):Boolean;
var
  Percent:Integer;
  Elapsed,Speed,Remain:Double;
begin
  if ProgressMax>0 then Percent:=Round((Progress*100.0)/ProgressMax) else Percent:=0;
  Elapsed:=(GetTickCount64-StartTick)/1000.0;
  if Elapsed<0.2 then Elapsed:=0.2;
  Speed:=Progress/Elapsed;
  if Speed>0 then Remain:=(ProgressMax-Progress)/Speed else Remain:=0;
  DownloadPage.Msg1Label.Caption:=Format('%s (%d из %d)',[ExtractFileName(FileName),CurrentFile,TotalFiles]);
  DownloadPage.Msg2Label.Caption:=Format('%d%%   %.2f MB/s   Осталось: %d c',[Percent,Speed/1024/1024,Round(Remain)]);
  Result:=True;
end;

procedure InitializeWizard;
begin
  ExtractTemporaryFile('7z.exe');
  ExtractTemporaryFile('7z.dll');
  DownloadPage:=CreateDownloadPage('Загрузка Signer','Получение файлов релиза...',@OnProgress);
end;

procedure DownloadReleaseAssets;
var
  PS,ListFile,Line:String;
  Lines:TArrayOfString;
  I,P:Integer;
begin
  ListFile:=ExpandConstant('{tmp}\release_files.txt');
  PS:=ExpandConstant('{tmp}\gh_release.ps1');

  SaveStringToFile(PS,
    '$ProgressPreference="SilentlyContinue";'+#13#10+
    '$r=Invoke-RestMethod "https://api.github.com/repos/'+Repo+'/releases/tags/'+ReleaseTag+'";'+#13#10+
    '$r.assets|ForEach-Object{"$($_.name)|$($_.browser_download_url)"}|Set-Content "'+ListFile+'" -Encoding UTF8',False);

  if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -ExecutionPolicy Bypass -File "'+PS+'"','',SW_HIDE,ewWaitUntilTerminated,ResultCode) then
    RaiseException('Не удалось получить список файлов релиза.');

  if not LoadStringsFromFile(ListFile,Lines) then
    RaiseException('Релиз не содержит файлов.');

  TotalFiles:=GetArrayLength(Lines);

  DownloadPage.Show;
  try
    for I:=0 to TotalFiles-1 do
    begin
      CurrentFile:=I+1;
      Line:=Lines[I];
      P:=Pos('|',Line);
      if P=0 then Continue;
      DownloadPage.Clear;
      DownloadPage.Add(Copy(Line,P+1,MaxInt),Copy(Line,1,P-1),'');
      StartTick:=GetTickCount64;
      DownloadPage.Download;
    end;
  finally
    DownloadPage.Hide;
  end;
end;

function NextButtonClick(CurPageID:Integer):Boolean;
begin
  Result:=True;
  if CurPageID=wpReady then
    DownloadReleaseAssets;
end;

procedure CurStepChanged(CurStep:TSetupStep);
begin
  if CurStep<>ssPostInstall then Exit;

  Exec(ExpandConstant('{tmp}\7z.exe'),
    'x "'+ExpandConstant('{tmp}\Signer.7z.001')+'" -o"'+ExpandConstant('{app}')+'" -aoa -y',
    '',SW_HIDE,ewWaitUntilTerminated,ResultCode);

  if IsComponentSelected('cuda') and not DetectCuda then
    Exec(ExpandConstant('{tmp}\cuda.exe'),'','',SW_SHOWNORMAL,ewWaitUntilTerminated,ResultCode);

  if IsComponentSelected('klite') and not DetectKLite then
    Exec(ExpandConstant('{tmp}\klite.exe'),'/verysilent /norestart','',SW_HIDE,ewWaitUntilTerminated,ResultCode);

  if IsComponentSelected('ffmpeg') and not DetectFFmpeg then
    Exec(ExpandConstant('{tmp}\7z.exe'),
      'x "'+ExpandConstant('{tmp}\ffmpeg.zip')+'" -o"'+ExpandConstant('{app}')+'" -aoa -y',
      '',SW_HIDE,ewWaitUntilTerminated,ResultCode);
end;

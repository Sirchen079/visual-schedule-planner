; 知时 桌面应用 Inno Setup 安装脚本
; 解决 electron-builder NSIS 无法在选盘符时自动建子目录的问题：
; Inno Setup 目录页选盘符时，Pascal Script 自动在路径末尾追加 \知时
; 编译：ISCC.exe zhishi.iss
; 源：electron-builder 产出的 release/win-unpacked/

#define MyAppName "知时"
#define MyAppVersion "1.3.0"
#define MyAppPublisher "知时"
#define MyAppExeName "知时.exe"

[Setup]
AppId={{8F4E2C9A-1234-5678-9ABC-DEF012345678}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\release-inno
OutputBaseFilename=知时 Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
PrivilegesRequired=lowest
; 升级/安装时自动关闭占用文件的旧版进程（PrepareToInstall 已先优雅关闭，此处作兜底）
CloseApplications=force
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "chinesesimp"; MessagesFile: "ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; 打包 electron-builder 的 win-unpacked 全部内容
Source: "..\release\win-unpacked\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Code]
const
  APP_EXE = '知时.exe';
  BACKEND_EXE = 'zhishi-backend.exe';

// 优雅关闭知时：先 POST /shutdown 触发后端备份+落盘+退出，再 taskkill 兜底强杀。
// 升级/卸载前调用，避免文件被占用导致安装失败，同时保护未落盘数据。
procedure CloseZhishiSilently();
var
  ResultCode: Integer;
begin
  // 1. 通知本地后端优雅退出（graceful_exit：backup_db + engine.dispose + exit）
  ShellExec('open', 'powershell.exe',
    '-NoProfile -ExecutionPolicy Bypass -Command "try{Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 -Method POST -Uri http://127.0.0.1:18731/shutdown}catch{}"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  // 2. 等待前端/后端进程退出并落盘
  Sleep(4000);
  // 3. 兜底：强制结束可能残留的进程（优雅关闭失败时；会丢失最近极少量未落盘写入，但有启动备份+SQLite journal 兜底）
  ShellExec('open', 'taskkill.exe', '/F /IM ' + APP_EXE, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  ShellExec('open', 'taskkill.exe', '/F /IM ' + BACKEND_EXE, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

// 复制文件前：确保旧版进程已退出，避免文件占用导致安装/升级失败
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  CloseZhishiSilently();
end;

// 卸载开始前：同样先优雅关闭，避免卸载因文件占用失败
function InitializeUninstall(): Boolean;
begin
  Result := True;
  CloseZhishiSilently();
end;

// 目录页「下一步」：若所选路径末尾不是应用名，自动追加 \知时 子目录，避免散落到盘符根
function NextButtonClick(CurPageID: Integer): Boolean;
var
  Path, AppName, Tail: String;
begin
  Result := True;
  if CurPageID = wpSelectDir then
  begin
    Path := WizardDirValue();
    AppName := '{#MyAppName}';
    // 去掉末尾反斜杠
    if (Length(Path) > 0) and (Path[Length(Path)] = '\') then
      Path := Copy(Path, 1, Length(Path) - 1);
    // 取末尾与 AppName 等长的子串比较
    if Length(Path) >= Length(AppName) then
      Tail := Copy(Path, Length(Path) - Length(AppName) + 1, Length(AppName))
    else
      Tail := '';
    if Tail <> AppName then
    begin
      WizardForm.DirEdit.Text := Path + '\' + AppName;
      MsgBox('已自动在所选目录下创建子文件夹：' + #13#10 + #13#10 + WizardForm.DirEdit.Text, mbInformation, MB_OK);
      Result := False;  // 返回目录页，让用户看到修正后的路径
    end;
  end;
end;

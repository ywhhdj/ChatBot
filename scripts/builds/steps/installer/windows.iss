; ═══════════════════════════════════════════════════════════
; ChatBot 安装脚本
; 编译：ISCC.exe installer\ChatBot.iss
; ═══════════════════════════════════════════════════════════

[Setup]
; 唯一 ID，升级时靠它识别旧版本
AppId={8F3A2B10-4E5C-4D7A-9B21-1234567890AB}
AppName=%app_name
AppVersion=%app_version


; 安装路径（LocalAppData 免 UAC）
DefaultDirName={{autopf}}\\{app_name}
DefaultGroupName=%app_name
DisableProgramGroupPage=yes
DisableDirPage=no
AllowNoIcons=yes

; 权限：当前用户即可，不要 admin
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; 架构
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; 输出
OutputDir=%installer_dir
OutputBaseFilename=%app_name-setup
Compression=lzma
SolidCompression=yes
LZMANumBlockThreads=4

; 视觉
WizardStyle=modern
SetupIconFile=..\static\app.ico
UninstallDisplayIcon={app}\bin\{#AppExeName}
UninstallDisplayName={#AppName} {#AppVersion}

; 版本信息（写进 setup.exe 的 PE 头）
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Setup
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}
VersionInfoVersion={#AppVersion}

; 卸载时不删用户数据（下面 Code 段里询问）
; Uninstallable=yes

[Languages]
Name: "chinese"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";  Description: "创建桌面快捷方式";  GroupDescription: "附加任务:"; Flags: unchecked
Name: "startupicon";  Description: "开机自动启动";      GroupDescription: "附加任务:"; Flags: unchecked

[Files]
Source:"{%install_dir}\\*"; DestDir:"{{app}}"; Flags:recursesubdirs createallsubdirs

[Icons]
Name:"{{group}}\\{cfg.app_name}"; Filename:"{{app}}\\bin\\{exe_name}"
Name:"{{userdesktop}}\\{cfg.app_name}"; Filename:"{{app}}\\bin\\{exe_name}"

[Run]
; 安装完成页的勾选项
Filename: "{app}\bin\{#AppExeName}"; Description: "立即启动 {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; 卸载前尝试关闭正在运行的进程
Filename: "{cmd}"; Parameters: "/C taskkill /IM {#AppExeName} /F >NUL 2>&1"; Flags: runhidden

[Registry]
; 程序信息（方便其他程序识别）
Root: HKCU; Subkey: "Software\{#AppPublisher}\{#AppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\{#AppPublisher}\{#AppName}"; ValueType: string; ValueName: "Version";     ValueData: "{#AppVersion}"
Root: HKCU; Subkey: "Software\{#AppPublisher}\{#AppName}"; ValueType: string; ValueName: "DataPath";    ValueData: "{localappdata}\{#AppName}"

; 系统识别"已安装程序"（控制面板可见）
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppName}_is1"; ValueType: string; ValueName: "DisplayName";     ValueData: "{#AppName} {#AppVersion}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppName}_is1"; ValueType: string; ValueName: "DisplayIcon";     ValueData: "{app}\bin\{#AppExeName}"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppName}_is1"; ValueType: string; ValueName: "Publisher";       ValueData: "{#AppPublisher}"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppName}_is1"; ValueType: string; ValueName: "InstallLocation"; ValueData: "{app}"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppName}_is1"; ValueType: string; ValueName: "UninstallString"; ValueData: "{uninstallexe}"

[Code]
{ ═══════════════════════════════════════════════════════════
  安装前检查
  ═══════════════════════════════════════════════════════════ }

function InitializeSetup(): Boolean;
var
  FreeMB: Cardinal;
  TotalMB: Cardinal;
begin
  Result := True;

  { 磁盘空间检查：至少 500MB }
  if GetSpaceOnDisk(ExpandConstant('{localappdata}'), True, FreeMB, TotalMB) then
  begin
    if FreeMB < 500 then
    begin
      if MsgBox('可用磁盘空间不足 500MB，是否继续安装？', mbConfirmation, MB_YESNO) = IDNO then
      begin
        Result := False;
        Exit;
      end;
    end;
  end;
end;

{ ═══════════════════════════════════════════════════════════
  处理"已安装旧版本"
  ═══════════════════════════════════════════════════════════ }

function GetInstalledVersion(): String;
begin
  RegQueryStringValue(HKCU, 'Software\{#AppPublisher}\{#AppName}', 'Version', Result);
end;

function InitializeSetup_CheckOldVersion(): Boolean;
var
  OldVer: String;
begin
  Result := True;
  OldVer := GetInstalledVersion();
  if OldVer <> '' then
  begin
    if MsgBox('检测到已安装版本 ' + OldVer + '，是否覆盖安装？' + #13#10 +
              '（用户数据会被保留）',
              mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
    end;
  end;
end;

{ ═══════════════════════════════════════════════════════════
  安装前关闭正在运行的进程
  ═══════════════════════════════════════════════════════════ }

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  { 尝试关闭进程，等待最多 5 秒 }
  Exec(ExpandConstant('{cmd}'),
       '/C taskkill /IM {#AppExeName} /F >NUL 2>&1',
       '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(500);
end;

{ ═══════════════════════════════════════════════════════════
  卸载时询问是否保留用户数据
  ═══════════════════════════════════════════════════════════ }

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\{#AppName}');
    if DirExists(DataDir) then
    begin
      if MsgBox('是否删除用户数据？' + #13#10 + #13#10 +
                DataDir + #13#10 + #13#10 +
                '选择"否"将保留配置与日志，下次安装可继续使用。',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        DelTree(DataDir, True, True, True);
      end;
    end;
  end;
end;

{ ═══════════════════════════════════════════════════════════
  安装后：创建用户数据目录结构
  ═══════════════════════════════════════════════════════════ }

procedure CurStepChanged(CurStep: TSetupStep);
var
  DataRoot: String;
begin
  if CurStep = ssPostInstall then
  begin
    DataRoot := ExpandConstant('{localappdata}\{#AppName}');
    ForceDirectories(DataRoot + '\var\log');
    ForceDirectories(DataRoot + '\var\data');
    ForceDirectories(DataRoot + '\var\run');
    ForceDirectories(DataRoot + '\config');
  end;
end;
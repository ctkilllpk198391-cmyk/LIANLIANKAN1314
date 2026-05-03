; WechatAgent · Inno Setup minimal version
; SILENT install proof · no LicenseFile · no [Code] · no extra Languages
; 编译: iscc installer/setup.iss

[Setup]
AppName=WechatAgent
AppVersion=0.1.0
AppPublisher=wechat_agent
DefaultDirName={localappdata}\WechatAgent
DefaultGroupName=WechatAgent
OutputDir=..\dist
OutputBaseFilename=WechatAgent-Setup
PrivilegesRequired=lowest
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
DisableProgramGroupPage=yes
DisableDirPage=yes
DisableReadyPage=yes
DisableFinishedPage=no
SetupLogging=yes
UninstallDisplayName=WechatAgent
UninstallDisplayIcon={app}\wechat_agent.exe

[Files]
Source: "..\dist\wechat_agent.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "default_config"; DestDir: "{app}"; DestName: ".env"; Flags: ignoreversion
; 内嵌微信 4.0.5.26 安装器 (SiverKing 镜像 191MB) — wxauto4 真支持版本
; CI 装机时 download 到 ../dist/ 由 Inno Setup 嵌入 setup.exe
Source: "..\dist\weixin_4.0.5.26.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{userdesktop}\WechatAgent"; Filename: "{app}\wechat_agent.exe"; \
  Parameters: "--tenant tenant_0001 --server http://120.26.208.212 --auto-accept"; \
  WorkingDir: "{app}"; Tasks: desktopicon
Name: "{userprograms}\WechatAgent\WechatAgent"; Filename: "{app}\wechat_agent.exe"; \
  Parameters: "--tenant tenant_0001 --server http://120.26.208.212 --auto-accept"; \
  WorkingDir: "{app}"
Name: "{userprograms}\WechatAgent\Uninstall WechatAgent"; Filename: "{uninstallexe}"

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcut"; Flags: checkedonce
Name: "autostart"; Description: "Auto-start at login"; Flags: checkedonce

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "WechatAgent"; \
  ValueData: """{app}\wechat_agent.exe"" --tenant tenant_0001 --server http://120.26.208.212 --auto-accept"; \
  Flags: uninsdeletevalue; Tasks: autostart

[Run]
; 1. 装微信 4.0.5.26 (静默, 不强制覆盖客户已有 4.0.5.13/26 版本)
; /S = NSIS 静默安装. 检测 Weixin.exe 已存在且版本匹配则跳过
Filename: "{tmp}\weixin_4.0.5.26.exe"; \
  Parameters: "/S"; \
  StatusMsg: "正在安装微信 4.0.5.26 (wxauto4 真支持版本)..."; \
  Check: ShouldInstallWeixin; \
  Flags: waituntilterminated

; 2. 启动 wechat_agent
Filename: "{app}\wechat_agent.exe"; \
  Parameters: "--tenant tenant_0001 --server http://120.26.208.212 --auto-accept"; \
  WorkingDir: "{app}"; \
  Description: "Launch WechatAgent"; \
  Flags: nowait postinstall skipifsilent

[Code]
function ShouldInstallWeixin: Boolean;
var
  WeixinExe: String;
  Version: String;
begin
  // 检测客户机微信 4.x 是否已是 4.0.5.13/26 (wxauto4 真支持)
  WeixinExe := ExpandConstant('{pf}\Tencent\Weixin\Weixin.exe');
  if not FileExists(WeixinExe) then begin
    WeixinExe := ExpandConstant('{pf32}\Tencent\Weixin\Weixin.exe');
  end;
  if FileExists(WeixinExe) then begin
    GetVersionNumbersString(WeixinExe, Version);
    Log('Detected Weixin.exe version: ' + Version);
    // 匹配 4.0.5.13 或 4.0.5.26 = 跳过装
    if (Version = '4.0.5.13') or (Version = '4.0.5.26') then begin
      Result := False;
      Exit;
    end;
  end;
  // 否则装 4.0.5.26
  Result := True;
end;

[UninstallDelete]
Type: filesandordirs; Name: "{app}\logs"

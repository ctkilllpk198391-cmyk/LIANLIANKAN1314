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
Filename: "{app}\wechat_agent.exe"; \
  Parameters: "--tenant tenant_0001 --server http://120.26.208.212 --auto-accept"; \
  WorkingDir: "{app}"; \
  Description: "Launch WechatAgent"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\logs"

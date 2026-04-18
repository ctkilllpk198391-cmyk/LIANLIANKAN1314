; WechatAgent 安装脚本 · Inno Setup 6
; 用户级安装,无需管理员;桌面快捷方式 + 开机自启 + 激活码 wizard
; 编译: iscc installer/setup.iss

[Setup]
AppName=WechatAgent
AppVersion=0.1.0
AppPublisher=wechat_agent
AppPublisherURL=https://wechat-agent.example
DefaultDirName={localappdata}\WechatAgent
DefaultGroupName=WechatAgent
LicenseFile=legal\user_agreement_v3.md
OutputDir=dist
OutputBaseFilename=WechatAgent-Setup
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
DisableProgramGroupPage=yes
SetupLogging=yes
UninstallDisplayName=WechatAgent
UninstallDisplayIcon={app}\wechat_agent.exe

[Languages]
Name: "schinese"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Files]
Source: "dist\wechat_agent.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "legal\*.md"; DestDir: "{app}\legal"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{userdesktop}\WechatAgent"; Filename: "{app}\wechat_agent.exe"; \
  Parameters: "--tenant {code:GetTenant} --server {code:GetServer} --auto-accept"; \
  WorkingDir: "{app}"; Tasks: desktopicon
Name: "{userprograms}\WechatAgent\WechatAgent"; Filename: "{app}\wechat_agent.exe"; \
  Parameters: "--tenant {code:GetTenant} --server {code:GetServer} --auto-accept"; \
  WorkingDir: "{app}"
Name: "{userprograms}\WechatAgent\卸载 WechatAgent"; Filename: "{uninstallexe}"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标："; Flags: checkedonce
Name: "autostart"; Description: "开机自启"; GroupDescription: "启动选项："; Flags: checkedonce

[Registry]
; 开机自启(用户级 HKCU,无需 admin)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "WechatAgent"; \
  ValueData: """{app}\wechat_agent.exe"" --tenant {code:GetTenant} --server {code:GetServer} --auto-accept"; \
  Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\wechat_agent.exe"; \
  Parameters: "--tenant {code:GetTenant} --server {code:GetServer} --auto-accept"; \
  WorkingDir: "{app}"; \
  Description: "立即启动 WechatAgent"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\logs"
Type: files; Name: "{app}\.env"

[Code]
var
  ActivationPage: TInputQueryWizardPage;
  ServerPage: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  // 激活码页(必填)
  ActivationPage := CreateInputQueryPage(
    wpLicense,
    '激活码验证',
    '请输入您的 WechatAgent 激活码',
    '格式 WXA-XXXX-XXXX-XXXX-XXXX (购买后由客服发给您)'
  );
  ActivationPage.Add('激活码:', False);

  // 服务器配置页(默认填好,高级用户可改)
  ServerPage := CreateInputQueryPage(
    ActivationPage.ID,
    '服务器配置',
    '高级选项 — 一般无需修改',
    '保持默认即可,除非客服指示更改'
  );
  ServerPage.Add('Server URL:', False);
  ServerPage.Add('Tenant ID:', False);
  ServerPage.Values[0] := 'http://120.26.208.212';
  ServerPage.Values[1] := 'tenant_0001';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Code: String;
begin
  Result := True;
  if CurPageID = ActivationPage.ID then
  begin
    Code := Trim(ActivationPage.Values[0]);
    if Length(Code) < 8 then
    begin
      MsgBox('激活码格式错误,请检查后重输。', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function GetActivationCode(Param: String): String;
begin
  Result := Trim(ActivationPage.Values[0]);
end;

function GetServer(Param: String): String;
begin
  Result := Trim(ServerPage.Values[0]);
end;

function GetTenant(Param: String): String;
begin
  Result := Trim(ServerPage.Values[1]);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  EnvPath: String;
  EnvContent: String;
begin
  if CurStep = ssPostInstall then
  begin
    // 写 .env 配置文件(client 启动时会读)
    EnvPath := ExpandConstant('{app}\.env');
    EnvContent :=
      'BAIYANG_SERVER_URL=' + GetServer('') + #13#10 +
      'BAIYANG_TENANT_ID=' + GetTenant('') + #13#10 +
      'BAIYANG_ACTIVATION_CODE=' + GetActivationCode('') + #13#10 +
      'PYTHONIOENCODING=utf-8' + #13#10 +
      'PYTHONUNBUFFERED=1' + #13#10;
    SaveStringToFile(EnvPath, EnvContent, False);
  end;
end;

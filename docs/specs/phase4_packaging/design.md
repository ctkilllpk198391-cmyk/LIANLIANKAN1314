# Phase 4 · 客户端产品化 · Design

---

## 1. Nuitka 打包脚本

```bash
# scripts/build_windows.sh (在 Windows 跑)
nuitka --standalone \
       --onefile \
       --windows-icon-from-ico=assets/baiyang.ico \
       --windows-disable-console \
       --include-package=client \
       --include-package=shared \
       --include-package=wxauto \
       --include-package=humancursor \
       --include-data-dir=config=config \
       --output-dir=dist \
       --output-filename=baiyang-client.exe \
       client/main.py
```

---

## 2. InnoSetup 安装包

```ini
; scripts/installer.iss
[Setup]
AppName=白羊数字分身
AppVersion=0.1.0
DefaultDirName={localappdata}\Baiyang
DefaultGroupName=白羊
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=Baiyang-Setup-0.1.0
SetupIconFile=assets\baiyang.ico
WizardStyle=modern

[Files]
Source: "dist\baiyang-client.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "config\config.example.yaml"; DestDir: "{app}\config"; DestName: "config.yaml"; Flags: onlyifdoesntexist
Source: "legal\user_agreement.md"; DestDir: "{app}\legal"
Source: "legal\privacy_policy.md"; DestDir: "{app}\legal"

[Icons]
Name: "{group}\白羊数字分身"; Filename: "{app}\baiyang-client.exe"
Name: "{userdesktop}\白羊"; Filename: "{app}\baiyang-client.exe"

[Run]
Filename: "{app}\baiyang-client.exe"; Description: "立即启动"; Flags: nowait postinstall skipifsilent
```

---

## 3. 自动更新

```python
# client/updater.py
class Updater:
    def __init__(self, current_version: str, manifest_url: str):
        self.current = current_version
        self.manifest_url = manifest_url

    async def check(self) -> dict | None:
        async with aiohttp.ClientSession() as s:
            async with s.get(self.manifest_url) as r:
                m = await r.json()
        if version.parse(m["version"]) > version.parse(self.current):
            return m
        return None

    async def download_and_install(self, manifest: dict) -> bool:
        url = manifest["download_url"]
        sha256_expected = manifest["sha256"]
        # 下载到 tmp · 校验 sha256 · mv 替换 + 重启
        ...
```

---

## 4. Sentry self-hosted

```python
# client/sentry_init.py
import sentry_sdk

def init_sentry(dsn: str, env: str = "production"):
    sentry_sdk.init(
        dsn=dsn,
        environment=env,
        release="baiyang-client@0.1.0",
        send_default_pii=False,        # 不发 PII
        before_send=_redact_chat_content,  # 移除聊天内容
        traces_sample_rate=0.1,
    )

def _redact_chat_content(event, hint):
    """从 event 中移除任何聊天文本字段。"""
    for key in ("text", "content", "boss_reply", "customer_msg"):
        if "extra" in event and key in event.get("extra", {}):
            event["extra"][key] = "[REDACTED]"
    return event
```

---

## 5. 远程配置热更

```python
# client/remote_config.py
class RemoteConfig:
    def __init__(self, server_url: str, local_cache: Path):
        self.server_url = server_url
        self.cache = local_cache

    async def fetch(self) -> dict | None:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{self.server_url}/v1/client_config") as r:
                payload = await r.json()
        sha = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        if sha != payload.get("expected_sha256"):
            return None  # 校验失败
        self.cache.write_text(json.dumps(payload, ensure_ascii=False))
        return payload
```

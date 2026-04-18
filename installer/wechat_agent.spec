# PyInstaller spec · wechat_agent client → 单 exe
# 用法 (Windows): pyinstaller installer/wechat_agent.spec --clean --noconfirm
# 输出: dist/wechat_agent.exe (含 Python runtime + 全部依赖)

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

# spec 在 installer/ · 项目根是上一级
SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
PROJECT_ROOT = os.path.dirname(SPEC_DIR)

block_cipher = None

# 收集整包(含 hidden imports / data / binaries)防止运行时漏
datas = []
binaries = []
hiddenimports = []

for pkg in [
    'fastapi', 'pydantic', 'pydantic_core', 'aiohttp', 'httpx',
    'sqlalchemy', 'aiosqlite', 'dotenv', 'yaml',
    'humancursor', 'appdirs', 'pkg_resources',
]:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as e:
        print(f"[spec] WARN: collect_all({pkg}) failed: {e}")

# wxautox + pywin32 只在 Windows 收集(macOS dry-run 时跳过)
if sys.platform == 'win32':
    for pkg in ['wxautox', 'win32api', 'win32con', 'win32gui', 'pywintypes']:
        try:
            d, b, h = collect_all(pkg)
            datas += d
            binaries += b
            hiddenimports += h
        except Exception as e:
            print(f"[spec] WARN: collect_all({pkg}) failed: {e}")

# 项目自己的子模块(client/ shared/ 全部)
hiddenimports += collect_submodules('client')
hiddenimports += collect_submodules('shared')

a = Analysis(
    [os.path.join(PROJECT_ROOT, 'client', 'main.py')],
    pathex=[PROJECT_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy.tests', 'PIL.tests'],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='wechat_agent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX 在 Windows Defender 易误报,关掉
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 留 console 方便初期调试看 log
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

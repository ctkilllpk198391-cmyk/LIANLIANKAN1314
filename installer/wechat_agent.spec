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

# wxauto4 (唯一开源引擎 in pypi v41.1.2) + 真依赖全 collect_all 防漏
# wxauto/wxautox/wxautox4 不在 pypi (商业版 plus.wxauto.org), 已从 watcher.py 移除
if sys.platform == 'win32':
    win_pkgs = [
        'wxauto4',  # 微信 4.x 开源
        'colorama', 'comtypes', 'PIL', 'psutil', 'pyperclip', 'tenacity',  # wxauto4 真依赖
        'uiautomation',  # 微信 4.1 直接控件树访问
        'win32api', 'win32con', 'win32gui', 'pywintypes',
    ]
    for pkg in win_pkgs:
        try:
            d, b, h = collect_all(pkg)
            datas += d
            binaries += b
            hiddenimports += h
            print(f"[spec] OK collect_all({pkg})")
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

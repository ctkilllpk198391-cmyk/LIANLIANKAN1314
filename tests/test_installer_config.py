"""tests/test_installer_config.py · F1 安装器配置完整性验证 · ≥3 用例。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

REPO_ROOT = Path(__file__).parent.parent
NUITKA_BUILD = REPO_ROOT / "installer" / "nuitka_build.py"
SETUP_ISS = REPO_ROOT / "installer" / "setup.iss"
BUILD_SH = REPO_ROOT / "installer" / "build.sh"


# ─── 文件存在性 ───────────────────────────────────────────────────────────────

def test_nuitka_build_py_exists():
    assert NUITKA_BUILD.exists(), "installer/nuitka_build.py 不存在"


def test_setup_iss_exists():
    assert SETUP_ISS.exists(), "installer/setup.iss 不存在"


def test_build_sh_exists():
    assert BUILD_SH.exists(), "installer/build.sh 不存在"


# ─── nuitka_build.py 关键字段 ─────────────────────────────────────────────────

class TestNuitkaBuildPy:
    @pytest.fixture(scope="class", autouse=True)
    def content(self, request):
        request.cls.text = NUITKA_BUILD.read_text(encoding="utf-8")

    def test_has_standalone_flag(self):
        assert "--standalone" in self.text

    def test_has_onefile_flag(self):
        assert "--onefile" in self.text

    def test_has_windows_disable_console(self):
        assert "--windows-disable-console" in self.text

    def test_has_include_package_client(self):
        assert "include-package" in self.text and "client" in self.text

    def test_has_include_package_server(self):
        assert "include-package" in self.text and "server" in self.text

    def test_has_company_name(self):
        assert "company-name" in self.text or "company_name" in self.text.lower()

    def test_has_product_name(self):
        assert "WechatAgent" in self.text

    def test_has_version(self):
        assert "0.1.0" in self.text

    def test_has_build_function(self):
        assert "def build(" in self.text

    def test_has_main_function(self):
        assert "def main(" in self.text

    def test_entry_point_is_client_main(self):
        assert "client/main.py" in self.text or "client\\main.py" in self.text

    def test_output_dir_param(self):
        assert "output-dir" in self.text or "output_dir" in self.text


# ─── setup.iss 关键字段 ───────────────────────────────────────────────────────

class TestSetupIss:
    @pytest.fixture(scope="class", autouse=True)
    def content(self, request):
        request.cls.text = SETUP_ISS.read_text(encoding="utf-8")

    def test_has_app_name(self):
        assert "AppName=WechatAgent" in self.text

    def test_has_app_version(self):
        assert "AppVersion=0.1.0" in self.text

    def test_has_license_file(self):
        assert "LicenseFile" in self.text and "user_agreement_v3" in self.text

    def test_has_output_dir(self):
        assert "OutputDir=dist" in self.text

    def test_has_output_base_filename(self):
        assert "WechatAgent-Setup" in self.text

    def test_has_exe_source(self):
        assert "wechat_agent.exe" in self.text

    def test_has_desktop_icon(self):
        assert "commondesktop" in self.text or "desktop" in self.text.lower()

    def test_has_startup_entry(self):
        # 开机自启：注册表 Run 或 userstartup
        assert "userstartup" in self.text or "Run" in self.text

    def test_has_files_section(self):
        assert "[Files]" in self.text

    def test_has_icons_section(self):
        assert "[Icons]" in self.text

    def test_has_run_section(self):
        assert "[Run]" in self.text

    def test_has_code_section(self):
        assert "[Code]" in self.text

    def test_has_privileges_required(self):
        assert "PrivilegesRequired=admin" in self.text

    def test_has_legal_files(self):
        assert "legal" in self.text


# ─── build.sh 关键字段 ────────────────────────────────────────────────────────

class TestBuildSh:
    @pytest.fixture(scope="class", autouse=True)
    def content(self, request):
        request.cls.text = BUILD_SH.read_text(encoding="utf-8")

    def test_has_shebang(self):
        assert self.text.startswith("#!/")

    def test_has_nuitka_build_call(self):
        assert "nuitka_build.py" in self.text

    def test_has_iscc_call(self):
        assert "iscc" in self.text

    def test_has_set_e(self):
        assert "set -e" in self.text

    def test_has_dist_check(self):
        assert "dist" in self.text


# ─── nuitka_build.py 可导入性验证 ────────────────────────────────────────────

def test_nuitka_build_importable():
    """nuitka_build.py 能在无 nuitka 环境下正常 import。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("nuitka_build", NUITKA_BUILD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "build")
    assert hasattr(mod, "main")
    assert hasattr(mod, "NUITKA_FLAGS")


def test_nuitka_flags_list_not_empty():
    import importlib.util
    spec = importlib.util.spec_from_file_location("nuitka_build", NUITKA_BUILD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert len(mod.NUITKA_FLAGS) >= 5


def test_build_function_returns_int_on_non_windows():
    """macOS 上 build() 打印命令后返回 0。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("nuitka_build", NUITKA_BUILD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        rc = mod.build(output_dir=tmpdir)
    assert rc == 0

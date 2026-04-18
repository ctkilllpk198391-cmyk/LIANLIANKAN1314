#!/usr/bin/env bash
# macOS 上准备 · Windows 真编译
# 用法：bash installer/build.sh [--output-dir dist]
set -e

cd "$(dirname "$0")/.."

OUTPUT_DIR="dist"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

mkdir -p "$OUTPUT_DIR"

echo "[1/3] Nuitka 编译..."
python3 installer/nuitka_build.py --output-dir "$OUTPUT_DIR"

echo "[2/3] InnoSetup 编译（仅 Windows）..."
if command -v iscc &> /dev/null; then
    iscc installer/setup.iss
else
    echo "[SKIP] iscc 不在 PATH · 跳过 InnoSetup · 请在 Windows 上手动运行："
    echo "       iscc installer/setup.iss"
fi

echo "[3/3] 完成 · 检查 $OUTPUT_DIR/"
ls -lh "$OUTPUT_DIR/" 2>/dev/null || echo "（dist/ 目录为空 · 非 Windows 环境正常）"

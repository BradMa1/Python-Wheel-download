#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOWNLOAD_DIR="$SCRIPT_DIR/packages_download"

if [ ! -d "$DOWNLOAD_DIR" ]; then
    echo "错误：找不到 $DOWNLOAD_DIR"
    exit 1
fi

echo "从 $DOWNLOAD_DIR 安装所有包..."
python3 -m pip install --no-index --find-links="$DOWNLOAD_DIR" "$DOWNLOAD_DIR"/*.whl "$DOWNLOAD_DIR"/*.tar.gz
echo "安装完成。"

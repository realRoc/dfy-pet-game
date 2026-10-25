#!/bin/bash
# macOS 双击启动：第一次会自动建虚拟环境并安装 PySide6-Essentials、PyAV 等依赖（约 400 MB），之后秒开。
cd "$(dirname "$0")" || exit 1

if [ ! -x .venv/bin/python ] || ! .venv/bin/python -c "import PySide6, requests, psutil, av, game.content" 2>/dev/null; then
  if ! command -v python3 >/dev/null 2>&1; then
    echo "没找到 python3，请先安装：https://www.python.org/downloads/macos/ 或 brew install python"
    read -r -p "按回车退出"
    exit 1
  fi
  echo "正在安装依赖……"
  { [ -x .venv/bin/python ] || python3 -m venv .venv; } && .venv/bin/pip install -r requirements.txt || {
    rm -rf .venv
    echo "依赖安装失败，检查网络后重试"
    read -r -p "按回车退出"
    exit 1
  }
fi

exec .venv/bin/python main.py

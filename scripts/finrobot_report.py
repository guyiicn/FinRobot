#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FinRobot A股研究报告工作流 — Python 版本

用法: python finrobot_report.py <ticker> <公司名> [peers...] [--theme ms]

示例:
  python finrobot_report.py 300413.SZ "芒果超媒" 002027 300133 300027
  python finrobot_report.py 301062.SZ "上海艾录" 002831 002014 002228 --theme cicc
"""

import sys
import subprocess
import os
from pathlib import Path

# FinRobot 工作区
FINROBOT_HOME = Path("/home/guyii/clawd/code/FinRobot")
SCRIPT_PATH = FINROBOT_HOME / "scripts" / "finrobot_report.sh"


def main():
    if len(sys.argv) < 3:
        print("用法: python finrobot_report.py <ticker> <公司名> [peers...] [--theme ms]")
        print("")
        print("示例:")
        print("  python finrobot_report.py 300413.SZ \"芒果超媒\" 002027 300133 300027")
        print("  python finrobot_report.py 301062.SZ \"上海艾录\" 002831 002014 002228 --theme cicc")
        sys.exit(1)

    # 检查脚本是否存在
    if not SCRIPT_PATH.exists():
        print(f"❌ 错误: 找不到工作流脚本 {SCRIPT_PATH}")
        sys.exit(1)

    # 构建命令
    cmd = ["bash", str(SCRIPT_PATH)] + sys.argv[1:]

    print(f"🚀 启动 FinRobot 工作流: {' '.join(sys.argv[1:])}")
    print("")

    # 执行
    result = subprocess.run(cmd, cwd=str(FINROBOT_HOME))

    sys.exit(result.returncode)


if __name__ == "__main__":
    main()

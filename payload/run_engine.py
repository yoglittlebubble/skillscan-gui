# -*- coding: utf-8 -*-
"""便携版 skillspector 启动器：用同目录的 Python + lib/ 里的依赖跑 CLI。

用法与 skillspector 命令完全一致：
    python.exe run_engine.py scan <目标> -f json
"""

import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(BASE, "lib")
if os.path.isdir(LIB) and LIB not in sys.path:
    sys.path.insert(0, LIB)

# 让引擎把临时文件、缓存都放在自己目录里，避免写到奇怪的位置
for env_key, sub in (("TEMP", "tmp"), ("TMP", "tmp")):
    d = os.path.join(BASE, sub)
    try:
        os.makedirs(d, exist_ok=True)
        os.environ[env_key] = d
    except OSError:
        pass


def main():
    from skillspector.cli_entry import app

    return app()


if __name__ == "__main__":
    sys.exit(main())

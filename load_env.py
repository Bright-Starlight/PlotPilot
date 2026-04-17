"""加载包根目录 `.env` 到 `os.environ`（与 CLI 行为一致，供 `serve` 使用）。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

_PACKAGE_ROOT = Path(__file__).resolve().parent
_ENV_PATH = _PACKAGE_ROOT / ".env"


def _parse_env_file(env_file: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip()
            # 去掉行内注释（# 后面的是注释，但不在引号内的）
            if "#" in v:
                # 简单处理：按 # 分割取第一部分
                v = v.split("#")[0].strip()
            if k:
                os.environ[k] = v
    return env_file

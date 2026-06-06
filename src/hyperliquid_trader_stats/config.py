from __future__ import annotations

import os
from pathlib import Path


def _clean_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_env_file(path: str | Path = ".env", *, override: bool = False) -> bool:
    env_path = Path(path)
    if not env_path.exists():
        return False

    # 只支持简单 KEY=value，避免为了本地 Mongo 配置额外引入 dotenv 依赖。
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        if override or key not in os.environ:
            os.environ[key] = _clean_env_value(value)
    return True

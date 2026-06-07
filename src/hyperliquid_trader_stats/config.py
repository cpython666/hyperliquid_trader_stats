import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
API_URL = "https://api.hyperliquid.xyz/info"

# MongoDB 配置（用于 Motor）
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "your_database_name")

# 代理配置：默认使用本机 Clash HTTP 代理；设置 HYPER_STATS_USE_PROXY=false 可关闭。
def _env_bool(name: str, default: bool) -> bool:
    """读取布尔环境变量，支持 true/false、1/0、yes/no。"""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off", ""}


USE_PROXY = _env_bool("HYPER_STATS_USE_PROXY", True)
PROXY_URL = os.getenv("HYPER_STATS_PROXY_URL", "http://127.0.0.1:7890")
AIOHTTP_PROXY = PROXY_URL if USE_PROXY and PROXY_URL else None
REQUESTS_PROXIES = (
    {"http": AIOHTTP_PROXY, "https": AIOHTTP_PROXY}
    if AIOHTTP_PROXY
    else None
)

_proxy_parts = urlparse(AIOHTTP_PROXY or "")
WEBSOCKET_PROXY_KWARGS = {}
if AIOHTTP_PROXY and _proxy_parts.hostname and _proxy_parts.port:
    WEBSOCKET_PROXY_KWARGS = {
        "http_proxy_host": _proxy_parts.hostname,
        "http_proxy_port": _proxy_parts.port,
        "proxy_type": _proxy_parts.scheme or "http",
    }

DEBUG = True

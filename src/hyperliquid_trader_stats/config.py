import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
API_URL = "https://api.hyperliquid.xyz/info"

# MongoDB 配置（用于 Motor）
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "your_database_name")

DEBUG = True

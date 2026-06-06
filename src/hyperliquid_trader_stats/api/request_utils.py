import logging
import time
import json
from DrissionPage import Chromium, ChromiumOptions
import atexit
from curl_cffi import requests
from typing import Optional, Any
from scrapy import Selector

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def cffi_get(url: str) -> Optional[requests.Response]:
    """使用 curl_cffi 发送 GET 请求，模拟 Chrome 135 浏览器"""
    try:
        print(url)
        headers = {
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        }
        response = requests.get(url, headers=headers, impersonate="chrome131")
        logger.info(f"接收响应，状态码: {response.status_code}")
        print(response.status_code)
        return response.json()
    except Exception as e:
        print("出错了", e,response.text)
        return None


class ChromiumSingleton:
    """Chromium 浏览器的单例类，确保全局只有一个浏览器实例"""

    _instance = None
    _chromium = None
    _tab = None

    def __new__(cls):
        """创建或复用全局 Chromium 浏览器实例。"""
        if cls._instance is None:
            logger.debug("开始初始化 Chromium 单例")
            cls._instance = super(ChromiumSingleton, cls).__new__(cls)
            # 初始化 Chromium 浏览器
            co = ChromiumOptions().auto_port()
            cls._chromium = Chromium(co)
            cls._tab = cls._chromium.new_tab()
            # 注册退出清理
            atexit.register(cls._cleanup)
            logger.info("Chromium 单例初始化完成")
        return cls._instance

    @classmethod
    def get_tab(cls):
        """获取单例的浏览器标签页"""
        logger.debug("获取 Chromium 标签页")
        if cls._instance is None:
            cls()  # 触发初始化
        return cls._tab

    @classmethod
    def _cleanup(cls):
        """清理 Chromium 资源，关闭浏览器"""
        logger.debug("开始清理 Chromium 资源")
        if cls._chromium:
            try:
                cls._chromium.quit()
                logger.info("Chromium 浏览器已关闭")
            except Exception as e:
                logger.error(f"关闭 Chromium 失败: {e}")
            cls._chromium = None
            cls._tab = None
            cls._instance = None


def listen_response(url: str) -> Optional[Any]:
    """打开页面并轮询正文内容，解析通过浏览器校验后的 JSON 响应。"""
    logger.info(f"开始请求 URL: {url}")
    tab = ChromiumSingleton.get_tab()

    try:
        # 开始监听
        logger.debug(f"启动监听: {url}")
        # 访问 URL
        logger.debug(f"访问 URL: {url}")
        tab.get(url)
        for _ in range(100):
            response = Selector(text=tab.html)
            text = "".join(response.xpath("//body//text()").getall())
            if "我们正在验证您的浏览器" in text:
                time.sleep(0.5)
            elif "无法验证您的浏览器" in text:
                tab.refresh()
                time.sleep(0.5)
            else:
                data = json.loads(text)
                return data
        logger.warning("未捕获有效响应，监听结束")
        return None

    except Exception as e:
        logger.error(f"监听过程中发生错误: {e}")
        return None


def example_usage():
    """示例用法：监听 Hyperdash trader-stats-v2 API"""
    address = "0x25652b7750934c68e78d5a8dd643ffec9dc9cc37"
    url = f"https://hyperdash.info/api/hyperdash/trader-stats-v2?address={address}"

    if result := listen_response(url):
        logger.info(f"监听成功，响应数据类型: {type(result)}")
        print(f"响应内容: {str(result)[:200]}...")
    else:
        logger.error("监听失败，未捕获有效响应")
        print("监听失败，未捕获有效响应")


if __name__ == "__main__":
    example_usage()

# -*- coding: utf-8 -*-
"""
溶解检测 HTTP 客户端 —— 供 Uni-Lab 集成调用。

封装对溶解检测服务的 HTTP 调用，Uni-Lab 侧只需 import 后调用一个函数即可，
无需关心 HTTP 细节。

用法（Uni-Lab 拍照完成后调用）：
    from dissolution_client import trigger_dissolution_detect

    result = trigger_dissolution_detect()   # 返回 0 或 1
    # result=1 → 已溶解，result=0 → 未溶解

依赖：仅 requests（Uni-Lab 已有）。

服务地址配置优先级：
    1. 函数参数 service_url 显式传入
    2. 环境变量 DISSOLUTION_SERVICE_URL
    3. 默认推理机地址 http://192.168.1.100:8003
"""
import os

import requests

# 默认服务地址 = 推理机（192.168.1.100，端口 8003）
DEFAULT_SERVICE_URL = os.environ.get(
    "DISSOLUTION_SERVICE_URL", "http://192.168.1.100:8003"
)


def _service_url(custom_url: str | None) -> str:
    return (custom_url or DEFAULT_SERVICE_URL).rstrip("/")


def trigger_dissolution_detect(service_url: str | None = None, timeout: int = 60) -> int:
    """拍照完成后触发溶解检测。

    服务内部自动：取最新照片 → 推理 → 写本地日志。

    Args:
        service_url: 服务地址，默认 http://127.0.0.1:8003
        timeout: 超时秒数，默认 60（CPU 推理较慢）

    Returns:
        int: 1=已溶解，0=未溶解（含无法可靠判断，安全默认）

    Raises:
        RuntimeError: 服务不可达、照片缺失或推理失败时抛出
    """
    base = _service_url(service_url)
    try:
        resp = requests.post(f"{base}/trigger_detect", timeout=timeout)
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"溶解检测服务不可达: {base} ({e})") from e

    if resp.status_code != 200:
        detail = resp.text[:200]
        raise RuntimeError(f"溶解检测失败 (HTTP {resp.status_code}): {detail}")

    try:
        result = resp.json()["result"]
    except (ValueError, KeyError) as e:
        raise RuntimeError(f"溶解检测返回格式异常: {resp.text[:200]}") from e

    return int(result)


def check_service(service_url: str | None = None, timeout: int = 10) -> bool:
    """健康检查：服务是否就绪（模型已加载）。

    Returns:
        bool: True=服务就绪，False=未就绪/不可达
    """
    base = _service_url(service_url)
    try:
        resp = requests.get(f"{base}/health", timeout=timeout)
        return resp.status_code == 200 and resp.json().get("model_loaded") is True
    except (requests.exceptions.RequestException, ValueError):
        return False


if __name__ == "__main__":
    # 自测：检查服务是否就绪，然后触发一次检测
    print("服务健康:", check_service())
    if check_service():
        print("触发检测 → result:", trigger_dissolution_detect())

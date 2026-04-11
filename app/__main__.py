#!/usr/bin/env python3
# coding: utf-8
"""
client-perf 启动入口

服务本身单进程运行（workers=1），并发由 asyncio 处理。
每个采集任务在独立子进程（TaskHandle/Process）中运行，互相隔离。

用法：
    python -m app              # 默认 0.0.0.0:8080
    python -m app --port 9090
    python -m app --reload   # 开发模式
"""
import argparse
import uvicorn

from app.api import app  # noqa: F401  — 供 uvicorn app.api:app 使用


def main():
    parser = argparse.ArgumentParser(description="client-perf 性能采集服务")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=8080, help="监听端口")
    parser.add_argument("--reload", action="store_true", help="开发模式热重载")
    args = parser.parse_args()

    uvicorn.run(
        "app.api:app",
        host=args.host,
        port=args.port,
        workers=1,          # 服务单进程，并发由 asyncio 负责
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
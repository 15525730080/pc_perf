#!/usr/bin/env python3
# coding: utf-8
"""
client-perf 启动入口

服务本身单进程运行（workers=1），并发由 asyncio 处理。
每个采集任务在独立子进程（TaskHandle/Process）中运行，互相隔离。

用法：
    python -m client_perf              # 默认 0.0.0.0:8080
    python -m client_perf --port 9090
    python -m client_perf --reload     # 开发模式
    client-perf                        # 安装后直接使用
"""
import argparse
import uvicorn

from client_perf.api import app  # noqa: F401  — 供 uvicorn app.api:app 使用


def main():
    parser = argparse.ArgumentParser(description="client-perf 性能采集服务")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=8080, help="监听端口")
    parser.add_argument("--reload", action="store_true", help="开发模式热重载")
    parser.add_argument("--no-elevate", action="store_true", help="不自动请求管理员权限")
    args = parser.parse_args()

    import uvicorn
    from client_perf.api import app  # noqa: F401

    uvicorn.run(
        "client_perf.api:app",
        host=args.host,
        port=args.port,
        workers=1,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()

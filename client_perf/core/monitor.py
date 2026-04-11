# coding: utf-8
"""
Monitor — 通用性能指标采集循环。

用法：
    m = Monitor(some_async_func, pid=1234, save_dir="/tmp/task1",
                key_value=["time", "cpu_usage(%)"], monitor_name="cpu")
    await m.run()   # 持续采集，直到 m.stop() 被调用
"""
import asyncio
import csv
import inspect
import time
import traceback
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

from client_perf.log import log as logger


class Monitor:
    """
    持续调用 `func(**kwargs)` 并将结果写入 CSV。

    参数
    ----
    func        : 异步采集函数，签名中的参数名必须与 kwargs 中的 key 对应
    key_value   : CSV 表头列表，如 ["time", "cpu_usage(%)"]；
                  括号内单位仅用于表头，写入时自动去掉
    monitor_name: CSV 文件名（不含扩展名），默认取 func.__name__
    save_dir    : CSV 保存目录
    is_out      : 是否写 CSV（截图等不需要写 CSV 时传 False）
    """

    def __init__(self, func: Callable[..., Coroutine[Any, Any, dict | None]], **kwargs: Any) -> None:
        self.func = func
        self.kwargs = kwargs
        self._stop_event = asyncio.Event()   # clear = 运行中；set = 停止
        self._stop_event.clear()             # 默认运行

        self.key_value: list[str] = kwargs.get("key_value", [])
        self.name: str = kwargs.pop("monitor_name", None) or func.__name__
        self.save_dir: str | None = kwargs.get("save_dir")
        self.is_out: bool = kwargs.get("is_out", True)

        self._keys: list[str] = [k.split("(")[0] for k in self.key_value]

        if self.is_out and self.save_dir:
            dir_path = Path(self.save_dir)
            dir_path.mkdir(parents=True, exist_ok=True)
            self.csv_path: Path | None = dir_path / f"{self.name}.csv"
            with open(self.csv_path, "w", encoding="utf-8", newline="") as f:
                csv.writer(f).writerow(self.key_value)
        else:
            self.csv_path = None

    # ── 公开接口 ──────────────────────────────────────────────

    def stop(self) -> None:
        """通知采集循环退出"""
        self._stop_event.set()

    async def run(self) -> None:
        """持续采集，直到 stop() 被调用"""
        param_names = set(inspect.signature(self.func).parameters.keys())
        # 只传函数签名中存在的参数
        call_kwargs: dict[str, Any] = {k: v for k, v in self.kwargs.items() if k in param_names}

        while not self._stop_event.is_set():
            t0 = time.monotonic()
            try:
                res = await self.func(**call_kwargs)
                if self.is_out and res and self.csv_path:
                    with open(self.csv_path, "a", encoding="utf-8", newline="") as f:
                        csv.writer(f).writerow(
                            [res.get(k, "") for k in self._keys]
                        )
            except Exception:
                logger.error(traceback.format_exc())
            finally:
                elapsed = time.monotonic() - t0
                if elapsed < 1.0:
                    await asyncio.sleep(1.0 - elapsed)

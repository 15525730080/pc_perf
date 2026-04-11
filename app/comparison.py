# coding: utf-8
"""
TaskComparison — 多任务性能指标对比。

对比逻辑：
  1. 读取每个任务的 CSV 数据（通过 DataCollect）
  2. 按指标提取均值（avg）、最大值（max）、最小值（min）
  3. 以 base_task 为基准，计算其他任务各指标的变化率
  4. 返回结构化对比结果，供前端图表和表格使用
"""
from __future__ import annotations

from typing import Any

from app.db import TaskCollection
from app.util import DataCollect

# ── 指标映射：metric_key -> (csv_stem, csv_column_prefix) ──────
# csv_column_prefix 是 CSV 表头中数值列的前缀（不含单位括号部分）
_METRIC_MAP: dict[str, tuple[str, str]] = {
    "cpu":        ("cpu",          "cpu_usage"),
    "memory":     ("memory",       "process_memory_usage"),
    "fps":        ("fps",          "fps"),
    "gpu":        ("gpu",          "gpu"),
    "threads":    ("process_info", "num_threads"),
    "handles":    ("process_info", "num_handles"),
    "disk_read":  ("disk_io",      "disk_read_rate"),
    "disk_write": ("disk_io",      "disk_write_rate"),
    "net_sent":   ("network_io",   "net_sent_rate"),
    "net_recv":   ("network_io",   "net_recv_rate"),
}


def _extract_values(data: list[dict], stem: str, col_prefix: str) -> list[float]:
    """从 get_all_data() 结果中提取指定指标的数值列表。"""
    for item in data:
        if item.get("name") != stem:
            continue
        vals: list[float] = []
        for row in item.get("value", []):
            for k, v in row.items():
                if k.startswith(col_prefix) and isinstance(v, (int, float)):
                    vals.append(float(v))
                    break
        return vals
    return []


def _calc_avg(vals: list[float]) -> float | None:
    return round(sum(vals) / len(vals), 4) if vals else None


def _calc_max(vals: list[float]) -> float | None:
    return round(max(vals), 4) if vals else None


def _calc_min(vals: list[float]) -> float | None:
    return round(min(vals), 4) if vals else None


def _build_task_avg(data: list[dict]) -> dict[str, float | None]:
    """返回 {metric_avg_key: value} 形如 {"cpu_avg": 12.3, ...}"""
    result: dict[str, float | None] = {}
    for metric, (stem, col) in _METRIC_MAP.items():
        vals = _extract_values(data, stem, col)
        result[f"{metric}_avg"] = _calc_avg(vals)
        result[f"{metric}_max"] = _calc_max(vals)
        result[f"{metric}_min"] = _calc_min(vals)
    return result


class TaskComparison:

    @classmethod
    async def create_comparison(
        cls,
        task_ids: list[int],
        base_task_id: int | None = None,
    ) -> dict[str, Any]:
        """
        对比多个任务，返回：
        {
            "base_task": {...},
            "tasks": [
                {
                    "id": 1, "name": "...", "version": "...",
                    "avg": {"cpu_avg": 12.3, "cpu_max": 20.1, ...},
                    "diff": {"cpu_avg": +2.1, ...},          # 相对基准的绝对差
                    "pct":  {"cpu_avg": +5.2, ...},          # 相对基准的百分比变化
                    "data": {...}                            # 原始时间序列数据
                },
                ...
            ]
        }
        """
        if not task_ids:
            raise ValueError("task_ids 不能为空")

        base_id = base_task_id if base_task_id in task_ids else task_ids[0]

        # 并发读取所有任务数据
        import asyncio
        task_infos: list[dict] = []
        task_data_list: list[list[dict]] = []

        async def _load(tid: int):
            info = await TaskCollection.get_item_task(tid)
            # 使用 is_format=False 获取原始数据，不补全时间点
            data = await DataCollect(info["file_dir"]).get_all_data(is_format=False)
            return info, data

        results = await asyncio.gather(*[_load(tid) for tid in task_ids])
        for info, data in results:
            task_infos.append(info)
            task_data_list.append(data)

        # 计算各任务均值
        avgs: list[dict] = [_build_task_avg(d) for d in task_data_list]

        # 找基准任务的均值
        base_idx = next(i for i, info in enumerate(task_infos) if info["id"] == base_id)
        base_avg = avgs[base_idx]
        base_info = task_infos[base_idx]

        tasks_result: list[dict[str, Any]] = []
        for i, info in enumerate(task_infos):
            avg = avgs[i]
            diff: dict[str, float | None] = {}
            pct:  dict[str, float | None] = {}
            for k, v in avg.items():
                bv = base_avg.get(k)
                if v is not None and bv is not None:
                    d = round(v - bv, 4)
                    diff[k] = d
                    pct[k] = round(d / bv * 100, 2) if bv != 0 else None
                else:
                    diff[k] = None
                    pct[k] = None

            # 构建原始数据结构，方便前端处理
            raw_data = {}
            # 首先按 stem 分组存储数据
            stem_data = {}
            for item in task_data_list[i]:
                metric_name = item.get("name", "")
                if metric_name:
                    stem_data[metric_name] = item.get("value", [])
            
            # 然后根据 _METRIC_MAP 映射到前端的 key
            for front_key, (stem, col_prefix) in _METRIC_MAP.items():
                if stem in stem_data:
                    # 对于 process_info、disk_io、network_io 等包含多个指标的情况
                    # 需要根据 col_prefix 提取对应的数据
                    if stem == "process_info":
                        if front_key == "threads":
                            # 提取线程数数据
                            threads_data = []
                            for row in stem_data[stem]:
                                for k, v in row.items():
                                    if k.startswith("num_threads") and isinstance(v, (int, float)):
                                        threads_data.append({"time": row.get("time"), "value": float(v)})
                                        break
                            raw_data[front_key] = threads_data
                        elif front_key == "handles":
                            # 提取句柄数数据
                            handles_data = []
                            for row in stem_data[stem]:
                                for k, v in row.items():
                                    if k.startswith("num_handles") and isinstance(v, (int, float)):
                                        handles_data.append({"time": row.get("time"), "value": float(v)})
                                        break
                            raw_data[front_key] = handles_data
                    elif stem == "disk_io":
                        if front_key == "disk_read":
                            # 提取磁盘读取数据
                            disk_read_data = []
                            for row in stem_data[stem]:
                                for k, v in row.items():
                                    if k.startswith("disk_read_rate") and isinstance(v, (int, float)):
                                        disk_read_data.append({"time": row.get("time"), "value": float(v)})
                                        break
                            raw_data[front_key] = disk_read_data
                        elif front_key == "disk_write":
                            # 提取磁盘写入数据
                            disk_write_data = []
                            for row in stem_data[stem]:
                                for k, v in row.items():
                                    if k.startswith("disk_write_rate") and isinstance(v, (int, float)):
                                        disk_write_data.append({"time": row.get("time"), "value": float(v)})
                                        break
                            raw_data[front_key] = disk_write_data
                    elif stem == "network_io":
                        if front_key == "net_sent":
                            # 提取网络发送数据
                            net_sent_data = []
                            for row in stem_data[stem]:
                                for k, v in row.items():
                                    if k.startswith("net_sent_rate") and isinstance(v, (int, float)):
                                        net_sent_data.append({"time": row.get("time"), "value": float(v)})
                                        break
                            raw_data[front_key] = net_sent_data
                        elif front_key == "net_recv":
                            # 提取网络接收数据
                            net_recv_data = []
                            for row in stem_data[stem]:
                                for k, v in row.items():
                                    if k.startswith("net_recv_rate") and isinstance(v, (int, float)):
                                        net_recv_data.append({"time": row.get("time"), "value": float(v)})
                                        break
                            raw_data[front_key] = net_recv_data
                    else:
                        # 对于 cpu、memory、fps、gpu 等单个指标的情况
                        # 直接使用原始数据，但需要确保每个数据点包含 time 和 value 字段
                        processed_data = []
                        for row in stem_data[stem]:
                            time = row.get("time")
                            if time:
                                # 找到数值字段
                                value = None
                                for k, v in row.items():
                                    if k != "time" and isinstance(v, (int, float)):
                                        value = float(v)
                                        break
                                if value is not None:
                                    processed_data.append({"time": time, "value": value})
                        raw_data[front_key] = processed_data

            tasks_result.append({
                "id":      info["id"],
                "name":    info.get("name", ""),
                "version": info.get("version", ""),
                "platform": info.get("platform", ""),
                "device_type": info.get("device_type", "pc"),
                "start_time": info.get("start_time", ""),
                "avg":  avg,
                "diff": diff,
                "pct":  pct,
                "data": raw_data,  # 添加原始时间序列数据
            })

        return {
            "base_task": {
                "id":   base_info["id"],
                "name": base_info.get("name", ""),
                "version": base_info.get("version", ""),
            },
            "tasks": tasks_result,
        }

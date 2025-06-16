"""
性能数据对比模块

用于比较不同任务之间的性能差异，分析性能趋势
"""
import json
import os
import time
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from app.log import log as logger
from app.util import DataCollect
from app.database import TaskCollection

class TaskComparison:
    """任务对比类"""
    
    @classmethod
    async def create_comparison(cls, task_ids: List[int], base_task_id: Optional[int] = None) -> Dict[str, Any]:
        """
        创建性能对比数据
        
        Args:
            task_ids: 要对比的任务ID列表
            base_task_id: 基准任务ID，如果不提供，默认使用第一个任务
            
        Returns:
            对比结果字典
        """
        logger.info(f"开始创建任务对比，任务ID: {task_ids}，基准任务ID: {base_task_id}")
        
        if not task_ids:
            raise ValueError("至少需要提供一个任务ID")
        
        # 如果没有提供基准任务ID，使用第一个任务作为基准
        if base_task_id is None:
            base_task_id = task_ids[0]
        elif base_task_id not in task_ids:
            task_ids.insert(0, base_task_id)
            
        # 收集每个任务的数据
        tasks_data = []
        for task_id in task_ids:
            logger.info(f"收集任务 {task_id} 数据")
            item_task = await TaskCollection.get_item_task(int(task_id))
            result = await DataCollect(item_task.get("file_dir")).get_all_data()
            
            tasks_data.append({
                "task_id": task_id,
                "name": item_task.get("name") or f"任务{task_id}",
                "version": item_task.get("version") or "未知版本",
                "start_time": item_task.get("start_time"),
                "end_time": item_task.get("end_time"),
                "data": result
            })
        
        # 如果只有一个任务，无法进行对比
        if len(tasks_data) == 1:
            return {
                "tasks": [{
                    "id": tasks_data[0]["task_id"], 
                    "name": tasks_data[0]["name"],
                    "version": tasks_data[0]["version"]
                }],
                "metrics": {},
                "summary": "只有一个任务，无法进行对比。"
            }
            
        # 进行数据对比分析
        comparison_result = cls._compare_performance_data(tasks_data, base_task_id)
        return comparison_result
    
    @classmethod
    def _compare_performance_data(cls, tasks_data: List[Dict], base_task_id: int) -> Dict[str, Any]:
        """
        对比性能数据
        
        Args:
            tasks_data: 任务数据列表
            base_task_id: 基准任务ID
            
        Returns:
            对比结果字典
        """
        # 基础对比结果结构
        comparison = {
            "tasks": [],
            "base_task": None,
            "metrics": {
                "cpu": {"diff": [], "percent_change": []},
                "memory": {"diff": [], "percent_change": []},
                "fps": {"diff": [], "percent_change": []},
                "gpu": {"diff": [], "percent_change": []},
                "threads": {"diff": [], "percent_change": []},
                "handles": {"diff": [], "percent_change": []},
                "disk_read": {"diff": [], "percent_change": []},
                "disk_write": {"diff": [], "percent_change": []},
                "net_sent": {"diff": [], "percent_change": []},
                "net_recv": {"diff": [], "percent_change": []}
            },
            "summary": {}
        }
        
        # 填充任务基本信息
        for task in tasks_data:
            task_info = {
                "id": task["task_id"],
                "name": task["name"],
                "version": task["version"],
                "start_time": task["start_time"],
                "end_time": task["end_time"],
                # 添加指标平均值
                "avg": cls._extract_metrics_avg(task["data"])
            }
            comparison["tasks"].append(task_info)
            
            # 标记基准任务
            if int(task["task_id"]) == base_task_id:
                comparison["base_task"] = task_info
        
        # 如果没有找到基准任务，使用第一个任务作为基准
        if comparison["base_task"] is None and comparison["tasks"]:
            comparison["base_task"] = comparison["tasks"][0]
            base_task_id = int(comparison["tasks"][0]["id"])
        
        # 找到基准任务数据
        base_task = next((t for t in tasks_data if int(t["task_id"]) == base_task_id), None)
        if not base_task:
            logger.error(f"未找到基准任务：{base_task_id}")
            return comparison
        
        # 计算每个任务相对于基准任务的差异
        for task in tasks_data:
            if int(task["task_id"]) == base_task_id:
                continue  # 跳过基准任务
                
            # 对比CPU使用率
            cls._compare_metric(base_task, task, comparison, "cpu")
            
            # 对比内存使用
            cls._compare_metric(base_task, task, comparison, "memory")
            
            # 对比FPS
            cls._compare_metric(base_task, task, comparison, "fps")
            
            # 对比GPU使用率
            cls._compare_metric(base_task, task, comparison, "gpu")
            
            # 对比线程数
            cls._compare_metric(base_task, task, comparison, "threads", "process_info")
            
            # 对比句柄数
            cls._compare_metric(base_task, task, comparison, "handles", "process_info")
            
            # 对比磁盘读取
            cls._compare_metric(base_task, task, comparison, "disk_read", "disk_io")
            
            # 对比磁盘写入
            cls._compare_metric(base_task, task, comparison, "disk_write", "disk_io")
            
            # 对比网络发送
            cls._compare_metric(base_task, task, comparison, "net_sent", "network_io")
            
            # 对比网络接收
            cls._compare_metric(base_task, task, comparison, "net_recv", "network_io")
        
        # 生成总结
        comparison["summary"] = cls._generate_comparison_summary(comparison["metrics"])
        
        return comparison
    
    @staticmethod
    def _extract_metrics_avg(data: List[Dict]) -> Dict[str, float]:
        """提取各项指标的平均值"""
        metrics = {}
        
        # 提取CPU使用率平均值
        cpu_values = TaskComparison._extract_metric_values(data, "cpu", "cpu_usage(%)")
        if cpu_values:
            metrics["cpu_avg"] = round(sum(cpu_values) / len(cpu_values), 2)
            metrics["cpu_max"] = round(max(cpu_values), 2)
        
        # 提取内存使用平均值
        memory_values = TaskComparison._extract_metric_values(data, "memory", "process_memory_usage(M)")
        if memory_values:
            metrics["memory_avg"] = round(sum(memory_values) / len(memory_values), 2)
            metrics["memory_max"] = round(max(memory_values), 2)
        
        # 提取FPS平均值
        fps_values = TaskComparison._extract_metric_values(data, "fps", "fps(帧)")
        if fps_values:
            metrics["fps_avg"] = round(sum(fps_values) / len(fps_values), 2)
            metrics["fps_min"] = round(min(fps_values), 2)
        
        # 提取GPU使用率平均值
        gpu_values = TaskComparison._extract_metric_values(data, "gpu", "gpu(%)")
        if gpu_values:
            metrics["gpu_avg"] = round(sum(gpu_values) / len(gpu_values), 2)
            metrics["gpu_max"] = round(max(gpu_values), 2)
        
        # 提取线程数平均值
        thread_values = TaskComparison._extract_metric_values(data, "process_info", "num_threads(个)")
        if thread_values:
            metrics["threads_avg"] = round(sum(thread_values) / len(thread_values), 2)
            metrics["threads_max"] = round(max(thread_values), 2)
        
        # 提取句柄数平均值
        handle_values = TaskComparison._extract_metric_values(data, "process_info", "num_handles(个)")
        if handle_values:
            metrics["handles_avg"] = round(sum(handle_values) / len(handle_values), 2)
            metrics["handles_max"] = round(max(handle_values), 2)
        
        # 提取磁盘读取速率平均值
        disk_read_values = TaskComparison._extract_metric_values(data, "disk_io", "disk_read_rate(MB/s)")
        if disk_read_values:
            metrics["disk_read_avg"] = round(sum(disk_read_values) / len(disk_read_values), 2)
            metrics["disk_read_max"] = round(max(disk_read_values), 2)
        
        # 提取磁盘写入速率平均值
        disk_write_values = TaskComparison._extract_metric_values(data, "disk_io", "disk_write_rate(MB/s)")
        if disk_write_values:
            metrics["disk_write_avg"] = round(sum(disk_write_values) / len(disk_write_values), 2)
            metrics["disk_write_max"] = round(max(disk_write_values), 2)
        
        # 提取网络发送速率平均值
        net_sent_values = TaskComparison._extract_metric_values(data, "network_io", "net_sent_rate(MB/s)")
        if net_sent_values:
            metrics["net_sent_avg"] = round(sum(net_sent_values) / len(net_sent_values), 2)
            metrics["net_sent_max"] = round(max(net_sent_values), 2)
        
        # 提取网络接收速率平均值
        net_recv_values = TaskComparison._extract_metric_values(data, "network_io", "net_recv_rate(MB/s)")
        if net_recv_values:
            metrics["net_recv_avg"] = round(sum(net_recv_values) / len(net_recv_values), 2)
            metrics["net_recv_max"] = round(max(net_recv_values), 2)
        
        return metrics
    
    @staticmethod
    def _extract_metric_values(data: List[Dict], metric_name: str, value_key: str) -> List[float]:
        """提取指定指标的所有数值"""
        values = []
        for item in data:
            if item.get("name") == metric_name:
                for v in item.get("value", []):
                    if value_key in v and v.get(value_key) != "-":
                        try:
                            values.append(float(v.get(value_key)))
                        except (ValueError, TypeError):
                            pass
        return values
    
    @classmethod
    def _compare_metric(cls, 
                      base_task: Dict, 
                      compare_task: Dict, 
                      comparison: Dict,
                      metric_key: str,
                      data_key: Optional[str] = None) -> None:
        """比较两个任务的指定指标差异"""
        if data_key is None:
            data_key = metric_key
            
        # 根据不同指标确定数值键名
        value_key_mapping = {
            "cpu": "cpu_usage(%)",
            "memory": "process_memory_usage(M)",
            "fps": "fps(帧)",
            "gpu": "gpu(%)",
            "threads": "num_threads(个)",
            "handles": "num_handles(个)",
            "disk_read": "disk_read_rate(MB/s)",
            "disk_write": "disk_write_rate(MB/s)",
            "net_sent": "net_sent_rate(MB/s)",
            "net_recv": "net_recv_rate(MB/s)"
        }
        
        value_key = value_key_mapping.get(metric_key)
        if not value_key:
            logger.warning(f"未找到指标键 {metric_key} 的映射")
            return
            
        # 提取基准值和比较值
        base_values = cls._extract_metric_values(base_task["data"], data_key, value_key)
        compare_values = cls._extract_metric_values(compare_task["data"], data_key, value_key)
        
        if not base_values or not compare_values:
            logger.warning(f"任务 {base_task['task_id']} 或 {compare_task['task_id']} 没有 {metric_key} 指标数据")
            return
            
        # 计算平均值
        base_avg = sum(base_values) / len(base_values)
        compare_avg = sum(compare_values) / len(compare_values)
        
        # 计算差异和百分比变化
        diff = compare_avg - base_avg
        percent_change = (diff / base_avg * 100) if base_avg != 0 else 0
        
        # 存储结果
        task_index = next((i for i, t in enumerate(comparison["tasks"]) 
                         if int(t["id"]) == int(compare_task["task_id"])), None)
        
        if task_index is not None:
            # 添加到对应任务的差异和百分比变化列表
            comparison["metrics"][metric_key]["diff"].append({
                "task_id": compare_task["task_id"],
                "value": round(diff, 2)
            })
            comparison["metrics"][metric_key]["percent_change"].append({
                "task_id": compare_task["task_id"],
                "value": round(percent_change, 2)
            })
    
    @staticmethod
    def _generate_comparison_summary(metrics: Dict) -> Dict:
        """生成对比总结"""
        summary = {}
        
        # 指标改进方向（值越小越好/值越大越好）
        better_if_smaller = {"cpu", "memory", "disk_write", "disk_read", "net_sent", "net_recv"}
        
        for metric_name, data in metrics.items():
            if not data["diff"]:
                continue
                
            # 计算平均差异和平均百分比变化
            diffs = [item["value"] for item in data["diff"]]
            percentages = [item["value"] for item in data["percent_change"]]
            
            if diffs and percentages:
                avg_diff = sum(diffs) / len(diffs)
                avg_percent = sum(percentages) / len(percentages)
                
                # 判断是否优化
                is_better = (avg_diff < 0) if metric_name in better_if_smaller else (avg_diff > 0)
                
                summary[metric_name] = {
                    "avg_diff": round(avg_diff, 2),
                    "avg_percent_change": round(avg_percent, 2),
                    "is_better": is_better
                }
        
        return summary 
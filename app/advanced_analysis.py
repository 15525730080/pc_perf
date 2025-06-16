"""
高级性能数据分析模块

提供更高级的性能数据分析功能，如:
- 数据标准化和对齐
- 统计显著性分析
- 异常值检测
- 性能瓶颈分析
"""
import numpy as np
import os
import time
import logging
from typing import List, Dict, Any, Optional, Tuple, Union
from app.log import log as logger
from app.util import DataCollect
from app.comparison import DataNormalizer


class AdvancedAnalyzer:
    """高级性能分析器"""
    
    @classmethod
    async def analyze_tasks(cls, base_data: Dict[str, Any], comp_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        对两个任务的性能数据进行高级分析
        
        Args:
            base_data: 基准任务数据
            comp_data: 对比任务数据
            
        Returns:
            高级分析结果
        """
        analysis_results = {
            "statistical_significance": {},
            "anomaly_detection": {},
            "performance_stability": {},
            "bottleneck_analysis": {}
        }
        
        # 指标列表
        metrics = [
            {"key": "cpu", "name": "CPU使用率", "unit": "%", "data_key": "cpu_usage(%)"},
            {"key": "memory", "name": "内存使用量", "unit": "MB", "data_key": "process_memory_usage(M)"},
            {"key": "fps", "name": "FPS帧率", "unit": "帧", "data_key": "fps(帧)"},
            {"key": "gpu", "name": "GPU使用率", "unit": "%", "data_key": "gpu(%)"},
            {"key": "threads", "name": "线程数", "unit": "个", "data_key": "num_threads(个)"},
            {"key": "handles", "name": "句柄数", "unit": "个", "data_key": "num_handles(个)"},
            {"key": "disk_read", "name": "磁盘读取速率", "unit": "MB/s", "data_key": "disk_read_rate(MB/s)"},
            {"key": "disk_write", "name": "磁盘写入速率", "unit": "MB/s", "data_key": "disk_write_rate(MB/s)"},
            {"key": "net_sent", "name": "网络发送速率", "unit": "MB/s", "data_key": "net_sent_rate(MB/s)"},
            {"key": "net_recv", "name": "网络接收速率", "unit": "MB/s", "data_key": "net_recv_rate(MB/s)"}
        ]
        
        # 对每个指标进行高级分析
        for metric in metrics:
            # 提取基准任务和对比任务中该指标的数据
            base_metric_data = cls._extract_metric_data(base_data, metric["key"], metric["data_key"])
            comp_metric_data = cls._extract_metric_data(comp_data, metric["key"], metric["data_key"])
            
            if not base_metric_data or not comp_metric_data:
                continue
                
            # 1. 数据标准化和对齐
            norm_base_data, norm_comp_data = cls._normalize_and_align_data(base_metric_data, comp_metric_data)
            
            # 2. 统计显著性分析
            stat_result = cls._perform_statistical_analysis(norm_base_data, norm_comp_data)
            analysis_results["statistical_significance"][metric["key"]] = stat_result
            
            # 3. 异常值检测
            base_anomalies = cls._detect_anomalies(norm_base_data, metric["key"])
            comp_anomalies = cls._detect_anomalies(norm_comp_data, metric["key"])
            analysis_results["anomaly_detection"][metric["key"]] = {
                "base": base_anomalies,
                "compare": comp_anomalies
            }
            
            # 4. 性能稳定性分析
            base_stability = cls._analyze_stability(norm_base_data)
            comp_stability = cls._analyze_stability(norm_comp_data)
            analysis_results["performance_stability"][metric["key"]] = {
                "base": base_stability,
                "compare": comp_stability,
                "improved": bool(comp_stability["coefficient_of_variation"] < base_stability["coefficient_of_variation"]
                    if metric["key"] not in ["fps"] else  # 对于FPS，值越大越好
                    comp_stability["coefficient_of_variation"] > base_stability["coefficient_of_variation"])
            }
        
        # 5. 性能瓶颈分析
        bottlenecks = cls._analyze_bottlenecks(analysis_results)
        analysis_results["bottleneck_analysis"] = bottlenecks
        
        return analysis_results
    
    @staticmethod
    def _extract_metric_data(task_data: Dict[str, Any], metric_name: str, data_key: str) -> List[Dict]:
        """
        从任务数据中提取指定指标的数据
        
        Args:
            task_data: 任务数据
            metric_name: 指标名称
            data_key: 数据键名
            
        Returns:
            指标数据列表
        """
        metric_data = []
        
        # 遍历任务数据
        for item in task_data.get("data", []):
            if item.get("name") == metric_name:
                for point in item.get("value", []):
                    if data_key in point and point.get(data_key) != "-":
                        try:
                            value = float(point.get(data_key))
                            time_point = float(point.get("time", 0))
                            metric_data.append({
                                "time": time_point,
                                "value": value
                            })
                        except (ValueError, TypeError):
                            pass
        
        # 按时间排序
        if metric_data:
            metric_data.sort(key=lambda x: x["time"])
            
        return metric_data
    
    @staticmethod
    def _normalize_and_align_data(base_data: List[Dict], comp_data: List[Dict]) -> Tuple[List[float], List[float]]:
        """
        标准化并对齐两个数据序列
        
        Args:
            base_data: 基准数据
            comp_data: 对比数据
            
        Returns:
            标准化后的基准数据值和对比数据值
        """
        # 使用DataNormalizer进行时间序列标准化
        norm_base, norm_comp = DataNormalizer.normalize_time_series(base_data, comp_data)
        
        # 提取值
        base_values = [point.get("value", 0) for point in norm_base]
        comp_values = [point.get("value", 0) for point in norm_comp]
        
        return base_values, comp_values
    
    @staticmethod
    def _perform_statistical_analysis(base_values: List[float], comp_values: List[float]) -> Dict[str, Any]:
        """
        执行统计显著性分析
        
        Args:
            base_values: 基准数据值列表
            comp_values: 对比数据值列表
            
        Returns:
            统计分析结果
        """
        # 基本统计量
        base_mean = sum(base_values) / len(base_values) if base_values else 0
        comp_mean = sum(comp_values) / len(comp_values) if comp_values else 0
        
        base_std = float(np.std(base_values)) if len(base_values) > 1 else 0
        comp_std = float(np.std(comp_values)) if len(comp_values) > 1 else 0
        
        # 计算差异的置信度
        # 如果样本量足够大，可以使用t检验
        p_value = 1.0
        confidence = 0.0
        is_significant = False
        t_stat = 0.0
        
        if len(base_values) >= 10 and len(comp_values) >= 10:
            try:
                from scipy import stats
                t_stat, p_value = stats.ttest_ind(base_values, comp_values, equal_var=False)
                # 确保转换为Python原生类型
                t_stat = float(t_stat)
                p_value = float(p_value)
                confidence = (1 - p_value) * 100
                
                # 判断差异显著性
                is_significant = bool(p_value < 0.05)
            except ImportError:
                # 如果没有scipy，使用简化的方法估算置信度
                n1, n2 = len(base_values), len(comp_values)
                pooled_std = ((n1 - 1) * base_std**2 + (n2 - 1) * comp_std**2) / (n1 + n2 - 2)
                pooled_std = pooled_std**0.5
                
                # 估算t统计量
                if pooled_std > 0:
                    t_stat = (comp_mean - base_mean) / (pooled_std * ((1/n1 + 1/n2)**0.5))
                    
                    # 简单估算p值和置信度（非精确）
                    # 这里只是一个粗略估计，实际应该使用t分布表或scipy
                    abs_t = abs(t_stat)
                    if abs_t > 2.58:  # 约99%置信度
                        p_value = 0.01
                        confidence = 99.0
                    elif abs_t > 1.96:  # 约95%置信度
                        p_value = 0.05
                        confidence = 95.0
                    elif abs_t > 1.65:  # 约90%置信度
                        p_value = 0.10
                        confidence = 90.0
                    else:
                        p_value = 0.20
                        confidence = 80.0
                    
                    is_significant = bool(p_value < 0.05)
        
        return {
            "base_mean": round(base_mean, 3),
            "comp_mean": round(comp_mean, 3),
            "base_std": round(base_std, 3),
            "comp_std": round(comp_std, 3),
            "diff": round(comp_mean - base_mean, 3),
            "percent_change": round(((comp_mean - base_mean) / base_mean * 100) if base_mean else 0, 2),
            "t_statistic": round(t_stat, 3),
            "p_value": round(p_value, 4),
            "confidence": round(confidence, 2),
            "is_significant": bool(is_significant)  # 确保转换为Python原生布尔类型
        }
    
    @staticmethod
    def _detect_anomalies(data_values: List[float], metric_key: str) -> Dict[str, Any]:
        """
        检测异常值
        
        Args:
            data_values: 数据值列表
            metric_key: 指标键名
            
        Returns:
            异常值检测结果
        """
        if not data_values or len(data_values) < 4:
            return {
                "anomalies_count": 0,
                "anomalies_percent": 0,
                "anomalies_indices": [],
                "anomalies_values": []
            }
        
        # 计算四分位数
        q1 = float(np.percentile(data_values, 25))
        q3 = float(np.percentile(data_values, 75))
        iqr = q3 - q1
        
        # 定义异常值范围（使用1.5 * IQR规则）
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        
        # 对于FPS，只检测低于下界的值（FPS越高越好）
        if metric_key == "fps":
            anomalies_indices = [i for i, value in enumerate(data_values) if value < lower_bound]
            anomalies_values = [data_values[i] for i in anomalies_indices]
        else:
            # 对于其他指标，检测超出上界的值（值越低越好）
            anomalies_indices = [i for i, value in enumerate(data_values) if value > upper_bound]
            anomalies_values = [data_values[i] for i in anomalies_indices]
        
        # 确保所有数据都是Python原生类型
        anomalies_indices = [int(i) for i in anomalies_indices]
        anomalies_values = [float(v) for v in anomalies_values]
        
        return {
            "anomalies_count": len(anomalies_indices),
            "anomalies_percent": round(len(anomalies_indices) / len(data_values) * 100, 2) if data_values else 0,
            "anomalies_indices": anomalies_indices,
            "anomalies_values": anomalies_values,
            "bounds": {
                "lower": round(float(lower_bound), 3),
                "upper": round(float(upper_bound), 3)
            }
        }
    
    @staticmethod
    def _analyze_stability(data_values: List[float]) -> Dict[str, float]:
        """
        分析数据稳定性
        
        Args:
            data_values: 数据值列表
            
        Returns:
            稳定性分析结果
        """
        if not data_values or len(data_values) < 2:
            return {
                "mean": 0,
                "std": 0,
                "coefficient_of_variation": 0,
                "stability_score": 0
            }
        
        mean = sum(data_values) / len(data_values)
        std = float(np.std(data_values))
        
        # 计算变异系数（标准差/平均值）
        cv = (std / mean) if mean else float('inf')
        
        # 稳定性评分（1 - 变异系数），最低0分，最高100分
        stability_score = max(0, min(100, (1 - cv) * 100))
        
        return {
            "mean": round(mean, 3),
            "std": round(std, 3),
            "coefficient_of_variation": round(cv, 4),
            "stability_score": round(stability_score, 2)
        }
    
    @staticmethod
    def _analyze_bottlenecks(analysis_results: Dict[str, Dict]) -> Dict[str, Any]:
        """
        分析性能瓶颈
        
        Args:
            analysis_results: 分析结果
            
        Returns:
            瓶颈分析结果
        """
        # 关注的指标
        metrics_of_interest = ["cpu", "memory", "fps", "gpu", "disk_read", "disk_write"]
        
        # 潜在瓶颈列表
        potential_bottlenecks = []
        
        # 分析每个指标的统计显著性和异常值
        for metric in metrics_of_interest:
            stat_data = analysis_results["statistical_significance"].get(metric)
            anomaly_data = analysis_results["anomaly_detection"].get(metric)
            stability_data = analysis_results["performance_stability"].get(metric)
            
            if not stat_data or not anomaly_data or not stability_data:
                continue
                
            # 判断是否是潜在瓶颈
            is_bottleneck = False
            bottleneck_reasons = []
            
            # 条件1：对比版本中的指标显著变差
            if stat_data["is_significant"]:
                # 对于CPU、内存、磁盘I/O、网络I/O，值越低越好
                # 对于FPS，值越高越好
                is_negative_change = stat_data["diff"] > 0 if metric != "fps" else stat_data["diff"] < 0
                if is_negative_change and stat_data["percent_change"] > 5:  # 变化超过5%
                    is_bottleneck = True
                    bottleneck_reasons.append(f"{metric}性能显著变差 ({stat_data['percent_change']}%)")
            
            # 条件2：对比版本中的异常值明显增多
            base_anomalies = anomaly_data["base"]["anomalies_percent"]
            comp_anomalies = anomaly_data["compare"]["anomalies_percent"]
            
            if comp_anomalies > base_anomalies + 5:  # 异常值比例增加超过5%
                is_bottleneck = True
                bottleneck_reasons.append(f"{metric}异常值明显增多 (从{base_anomalies}%增至{comp_anomalies}%)")
            
            # 条件3：对比版本中的稳定性明显降低
            if not stability_data["improved"] and abs(stability_data["base"]["stability_score"] - stability_data["compare"]["stability_score"]) > 10:
                is_bottleneck = True
                bottleneck_reasons.append(f"{metric}稳定性明显降低 (从{stability_data['base']['stability_score']}降至{stability_data['compare']['stability_score']})")
            
            # 如果判定为瓶颈，添加到列表
            if is_bottleneck:
                potential_bottlenecks.append({
                    "metric": metric,
                    "reasons": bottleneck_reasons,
                    "significance": {
                        "p_value": float(stat_data["p_value"]),
                        "confidence": float(stat_data["confidence"])
                    },
                    "percent_change": float(stat_data["percent_change"])
                })
        
        # 按照变化百分比排序瓶颈，变化越大越靠前
        potential_bottlenecks.sort(key=lambda x: abs(x["percent_change"]), reverse=True)
        
        return {
            "has_bottlenecks": bool(len(potential_bottlenecks) > 0),
            "bottlenecks_count": len(potential_bottlenecks),
            "potential_bottlenecks": potential_bottlenecks,
        } 
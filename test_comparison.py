#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
历史版本报告对比功能测试脚本
"""

import asyncio
import os
import sys
import json
import argparse
import requests
from urllib.parse import urljoin
from datetime import datetime

# 默认API基础URL
BASE_URL = "http://127.0.0.1:20223"

class ComparisonTester:
    """历史版本对比功能测试类"""
    
    def __init__(self, base_url):
        self.base_url = base_url
        
    def api_url(self, path):
        """生成完整API路径"""
        return urljoin(self.base_url, path)
    
    def get_all_tasks(self):
        """获取所有任务"""
        response = requests.get(self.api_url("/get_all_task/"))
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 200:
                return data.get("msg", [])
        return []
    
    def set_task_version(self, task_id, version):
        """设置任务版本"""
        response = requests.get(self.api_url("/set_task_version/"), params={
            "task_id": task_id,
            "version": version
        })
        return response.json()
    
    def set_task_baseline(self, task_id, is_baseline=True):
        """设置任务为基线版本"""
        response = requests.get(self.api_url("/set_task_baseline/"), params={
            "task_id": task_id,
            "is_baseline": "true" if is_baseline else "false"
        })
        return response.json()
    
    def get_baseline_task(self):
        """获取基线任务"""
        response = requests.get(self.api_url("/get_baseline_task/"))
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 200:
                return data.get("msg")
        return None
        
    def compare_tasks(self, task_ids, base_task_id=None):
        """比较多个任务"""
        params = {
            "task_ids": ",".join(str(tid) for tid in task_ids)
        }
        if base_task_id:
            params["base_task_id"] = base_task_id
            
        response = requests.get(self.api_url("/compare_tasks/"), params=params)
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 200:
                return data.get("msg")
        return None
        
    def export_comparison_excel(self, task_ids, base_task_id=None, report_name=None):
        """导出对比Excel报表"""
        params = {
            "task_ids": ",".join(str(tid) for tid in task_ids)
        }
        if base_task_id:
            params["base_task_id"] = base_task_id
            
        if report_name:
            params["report_name"] = report_name
        else:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            params["report_name"] = f"测试对比报告_{timestamp}"
            
        response = requests.get(self.api_url("/export_comparison_excel/"), params=params)
        
        # 如果是Excel文件，保存到本地
        if response.status_code == 200 and "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in response.headers.get("Content-Type", ""):
            filename = response.headers.get("Content-Disposition", "").split("filename=")[-1].strip('"')
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                filename = f"对比报告_{timestamp}.xlsx"
                
            with open(filename, "wb") as f:
                f.write(response.content)
            return {
                "success": True,
                "filename": filename,
                "message": f"对比报表已导出到 {filename}"
            }
        else:
            # 如果不是Excel文件，可能是错误信息
            try:
                return response.json()
            except:
                return {
                    "success": False,
                    "message": f"导出失败: {response.text}"
                }
        
    def get_comparison_reports(self):
        """获取所有对比报告"""
        response = requests.get(self.api_url("/get_comparison_reports/"))
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 200:
                return data.get("msg", [])
        return []
        
    def delete_comparison_report(self, report_id):
        """删除对比报告"""
        response = requests.get(self.api_url("/delete_comparison_report/"), params={
            "report_id": report_id
        })
        return response.json()

    def advanced_compare_tasks(self, task_ids, base_task_id=None):
        """高级比较多个任务"""
        params = {
            "task_ids": ",".join(str(tid) for tid in task_ids)
        }
        if base_task_id:
            params["base_task_id"] = base_task_id
            
        response = requests.get(self.api_url("/advanced_compare_tasks/"), params=params)
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 200:
                return data.get("msg")
        return None
        
    def export_advanced_comparison_excel(self, task_ids, base_task_id=None, report_name=None):
        """导出高级对比Excel报表"""
        params = {
            "task_ids": ",".join(str(tid) for tid in task_ids)
        }
        if base_task_id:
            params["base_task_id"] = base_task_id
            
        if report_name:
            params["report_name"] = report_name
        else:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            params["report_name"] = f"高级测试对比报告_{timestamp}"
            
        response = requests.get(self.api_url("/export_advanced_comparison_excel/"), params=params)
        
        # 如果是Excel文件，保存到本地
        if response.status_code == 200 and "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in response.headers.get("Content-Type", ""):
            filename = response.headers.get("Content-Disposition", "").split("filename=")[-1].strip('"')
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                filename = f"高级对比报告_{timestamp}.xlsx"
                
            with open(filename, "wb") as f:
                f.write(response.content)
            return {
                "success": True,
                "filename": filename,
                "message": f"高级对比报表已导出到 {filename}"
            }
        else:
            # 如果不是Excel文件，可能是错误信息
            try:
                return response.json()
            except:
                return {
                    "success": False,
                    "message": f"导出失败: {response.text}"
                }


def print_json(data):
    """打印JSON数据"""
    print(json.dumps(data, indent=2, ensure_ascii=False))


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="历史版本对比功能测试")
    parser.add_argument("--url", default=BASE_URL, help=f"API基础URL (默认: {BASE_URL})")
    parser.add_argument("--action", choices=[
        "list_tasks",
        "set_version",
        "set_baseline",
        "get_baseline",
        "compare",
        "export",
        "list_reports",
        "delete_report",
        "advanced_compare",
        "export_advanced",
        "demo",
        "advanced_demo"
    ], default="demo", help="要执行的操作")
    parser.add_argument("--task-ids", help="任务ID列表，用逗号分隔")
    parser.add_argument("--base-task-id", type=int, help="基准任务ID")
    parser.add_argument("--version", help="任务版本")
    parser.add_argument("--report-id", type=int, help="对比报告ID")
    parser.add_argument("--report-name", help="报告名称")
    
    args = parser.parse_args()
    tester = ComparisonTester(args.url)
    
    if args.action == "list_tasks":
        # 列出所有任务
        tasks = tester.get_all_tasks()
        print(f"找到 {len(tasks)} 个任务:")
        for task in tasks:
            print(f"ID: {task.get('id')}, 名称: {task.get('name')}, 版本: {task.get('version', '无')}, 基线: {task.get('is_baseline', False)}")
    
    elif args.action == "set_version":
        # 设置任务版本
        if not args.task_ids or not args.version:
            print("错误: 需要指定任务ID (--task-ids) 和版本 (--version)")
            return
            
        task_id = args.task_ids.split(",")[0]  # 只取第一个ID
        result = tester.set_task_version(task_id, args.version)
        print_json(result)
    
    elif args.action == "set_baseline":
        # 设置基线任务
        if not args.task_ids:
            print("错误: 需要指定任务ID (--task-ids)")
            return
            
        task_id = args.task_ids.split(",")[0]  # 只取第一个ID
        result = tester.set_task_baseline(task_id, True)
        print_json(result)
    
    elif args.action == "get_baseline":
        # 获取基线任务
        baseline = tester.get_baseline_task()
        if baseline:
            print(f"基线任务: ID={baseline.get('id')}, 名称={baseline.get('name')}, 版本={baseline.get('version', '无')}")
        else:
            print("没有设置基线任务")
    
    elif args.action == "compare":
        # 比较任务
        if not args.task_ids:
            print("错误: 需要指定任务ID列表 (--task-ids)")
            return
            
        task_ids = [int(tid.strip()) for tid in args.task_ids.split(",")]
        comparison = tester.compare_tasks(task_ids, args.base_task_id)
        print_json(comparison)
    
    elif args.action == "export":
        # 导出对比报表
        if not args.task_ids:
            print("错误: 需要指定任务ID列表 (--task-ids)")
            return
            
        task_ids = [int(tid.strip()) for tid in args.task_ids.split(",")]
        result = tester.export_comparison_excel(task_ids, args.base_task_id, args.report_name)
        print_json(result)
    
    elif args.action == "list_reports":
        # 列出所有对比报告
        reports = tester.get_comparison_reports()
        print(f"找到 {len(reports)} 个对比报告:")
        for report in reports:
            print(f"ID: {report.get('id')}, 名称: {report.get('name')}, 创建时间: {report.get('create_time')}")
    
    elif args.action == "delete_report":
        # 删除对比报告
        if not args.report_id:
            print("错误: 需要指定报告ID (--report-id)")
            return
            
        result = tester.delete_comparison_report(args.report_id)
        print_json(result)
    
    elif args.action == "advanced_compare":
        # 高级比较任务
        if not args.task_ids:
            print("错误: 需要指定任务ID列表 (--task-ids)")
            return
            
        task_ids = [int(tid.strip()) for tid in args.task_ids.split(",")]
        comparison = tester.advanced_compare_tasks(task_ids, args.base_task_id)
        print_json(comparison)
    
    elif args.action == "export_advanced":
        # 导出高级对比报表
        if not args.task_ids:
            print("错误: 需要指定任务ID列表 (--task-ids)")
            return
            
        task_ids = [int(tid.strip()) for tid in args.task_ids.split(",")]
        result = tester.export_advanced_comparison_excel(task_ids, args.base_task_id, args.report_name)
        print_json(result)
    
    elif args.action == "demo":
        # 演示所有功能
        print("=== 历史版本报告对比功能演示 ===")
        
        # 1. 获取所有任务
        print("\n1. 获取所有任务")
        tasks = tester.get_all_tasks()
        print(f"找到 {len(tasks)} 个任务:")
        for i, task in enumerate(tasks[:5], 1):  # 只显示前5个
            print(f"{i}. ID: {task.get('id')}, 名称: {task.get('name')}, 状态: {task.get('status')}")
            
        if len(tasks) < 2:
            print("需要至少两个已完成的任务才能进行对比测试")
            return
            
        # 选择两个已完成的任务进行对比
        completed_tasks = [t for t in tasks if t.get('status') == 2]
        if len(completed_tasks) < 2:
            print("需要至少两个已完成的任务才能进行对比测试")
            return
            
        test_tasks = completed_tasks[:2]  # 选择前两个已完成的任务
        
        # 2. 设置任务版本
        print("\n2. 设置任务版本")
        result1 = tester.set_task_version(test_tasks[0]['id'], "v1.0.0")
        print(f"设置任务 {test_tasks[0]['id']} 版本为 v1.0.0: {result1.get('msg')}")
        
        result2 = tester.set_task_version(test_tasks[1]['id'], "v1.1.0")
        print(f"设置任务 {test_tasks[1]['id']} 版本为 v1.1.0: {result2.get('msg')}")
        
        # 3. 设置基线任务
        print("\n3. 设置基线任务")
        result = tester.set_task_baseline(test_tasks[0]['id'])
        print(f"设置任务 {test_tasks[0]['id']} 为基线版本: {result.get('msg')}")
        
        # 4. 获取基线任务
        print("\n4. 获取基线任务")
        baseline = tester.get_baseline_task()
        if baseline:
            print(f"基线任务: ID={baseline.get('id')}, 名称={baseline.get('name')}")
        else:
            print("没有设置基线任务")
            
        # 5. 比较任务
        print("\n5. 比较任务")
        task_ids = [t['id'] for t in test_tasks]
        comparison = tester.compare_tasks(task_ids)
        if comparison:
            print(f"成功比较 {len(comparison.get('tasks', []))} 个任务")
            summary = comparison.get('summary', {})
            print("对比摘要:")
            for metric, data in summary.items():
                trend = "改善" if data.get('is_better') else "下降"
                print(f"  {metric}: 差异 {data.get('avg_diff')}, 变化率 {data.get('avg_percent_change')}%, 趋势: {trend}")
        
        # 6. 导出对比报表
        print("\n6. 导出对比报表")
        report_name = f"测试对比报告_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        result = tester.export_comparison_excel(task_ids, None, report_name)
        if result.get("success"):
            print(f"报表导出成功: {result.get('message')}")
        else:
            print(f"报表导出失败: {result.get('message')}")
            
        # 7. 获取所有对比报告
        print("\n7. 获取所有对比报告")
        reports = tester.get_comparison_reports()
        print(f"找到 {len(reports)} 个对比报告:")
        for i, report in enumerate(reports[:5], 1):  # 只显示前5个
            print(f"{i}. ID: {report.get('id')}, 名称: {report.get('name')}, 创建时间: {report.get('create_time')}")

    elif args.action == "advanced_demo":
        # 演示高级对比功能
        print("=== 高级历史版本报告对比功能演示 ===")
        
        # 1. 获取所有任务
        print("\n1. 获取所有任务")
        tasks = tester.get_all_tasks()
        print(f"找到 {len(tasks)} 个任务:")
        for i, task in enumerate(tasks[:5], 1):  # 只显示前5个
            print(f"{i}. ID: {task.get('id')}, 名称: {task.get('name')}, 状态: {task.get('status')}")
            
        if len(tasks) < 2:
            print("需要至少两个已完成的任务才能进行高级对比测试")
            return
            
        # 选择两个已完成的任务进行对比
        completed_tasks = [t for t in tasks if t.get('status') == 2]
        if len(completed_tasks) < 2:
            print("需要至少两个已完成的任务才能进行高级对比测试")
            return
            
        test_tasks = completed_tasks[:2]  # 选择前两个已完成的任务
        print(f"\n选择任务 {test_tasks[0]['id']} 作为基准任务，任务 {test_tasks[1]['id']} 作为对比任务。")
        
        # 2. 设置任务版本
        print("\n2. 设置任务版本")
        result1 = tester.set_task_version(test_tasks[0]['id'], "v1.0.0 (基准)")
        print(f"设置任务 {test_tasks[0]['id']} 版本为 v1.0.0 (基准): {result1.get('msg')}")
        
        result2 = tester.set_task_version(test_tasks[1]['id'], "v1.1.0 (测试)")
        print(f"设置任务 {test_tasks[1]['id']} 版本为 v1.1.0 (测试): {result2.get('msg')}")
        
        # 3. 进行高级任务对比分析
        print("\n3. 进行高级性能对比分析")
        task_ids = [t['id'] for t in test_tasks]
        advanced_comparison = tester.advanced_compare_tasks(task_ids, test_tasks[0]['id'])
        if advanced_comparison:
            print("高级对比分析完成，分析以下指标:")
            
            # 显示瓶颈分析结果
            bottleneck_analysis = advanced_comparison.get("advanced_analysis", {}).get("bottleneck_analysis", {})
            if bottleneck_analysis.get("has_bottlenecks", False):
                print(f"检测到 {bottleneck_analysis.get('bottlenecks_count')} 个潜在性能瓶颈:")
                for i, bottleneck in enumerate(bottleneck_analysis.get("potential_bottlenecks", []), 1):
                    print(f"  瓶颈 {i}: {bottleneck.get('metric')} - 变化率: {bottleneck.get('percent_change')}%")
                    for reason in bottleneck.get("reasons", []):
                        print(f"    - {reason}")
            else:
                print("未检测到显著的性能瓶颈")
        
        # 4. 导出高级对比报表
        print("\n4. 导出高级对比报表")
        report_name = f"高级测试对比报告_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        result = tester.export_advanced_comparison_excel(task_ids, test_tasks[0]['id'], report_name)
        if result.get("success"):
            print(f"高级对比报表导出成功: {result.get('message')}")
        else:
            print(f"高级对比报表导出失败: {result.get('message')}")


if __name__ == "__main__":
    main() 
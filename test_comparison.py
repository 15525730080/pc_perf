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
    """比较任务测试类"""
    
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")
    
    def api_url(self, path):
        """构造API URL"""
        return f"{self.base_url}/{path.lstrip('/')}"
    
    def get_all_tasks(self):
        """获取所有任务"""
        response = requests.get(self.api_url("/get_all_task/"))
        return response.json().get("msg", [])
    
    def set_task_version(self, task_id, version):
        """设置任务版本"""
        url = self.api_url(f"/set_task_version/?task_id={task_id}&version={urllib.parse.quote(version)}")
        response = requests.get(url)
        return response.json()
    
    def set_task_baseline(self, task_id, is_baseline=True):
        """设置任务为基线版本"""
        url = self.api_url(f"/set_task_baseline/?task_id={task_id}&is_baseline={str(is_baseline).lower()}")
        response = requests.get(url)
        return response.json()
    
    def get_baseline_task(self):
        """获取基线任务"""
        response = requests.get(self.api_url("/get_baseline_task/"))
        if response.status_code == 200:
            json_data = response.json()
            if json_data.get("code") == 404:
                return None
            return json_data.get("msg")
        return None
    
    def compare_tasks(self, task_ids, base_task_id=None):
        """比较任务"""
        url = self.api_url(f"/compare_tasks/?task_ids={','.join(str(tid) for tid in task_ids)}")
        if base_task_id:
            url += f"&base_task_id={base_task_id}"
            
        response = requests.get(url)
        if response.status_code == 200:
            return response.json().get("msg")
        return None
    
    def export_comparison_excel(self, task_ids, base_task_id=None, report_name=None):
        """导出对比Excel报表"""
        url = self.api_url(f"/export_comparison_excel/?task_ids={','.join(str(tid) for tid in task_ids)}")
        if base_task_id:
            url += f"&base_task_id={base_task_id}"
        if report_name:
            url += f"&report_name={urllib.parse.quote(report_name)}"
            
        response = requests.get(url)
        if response.status_code == 200:
            # 如果返回的是Excel文件
            if 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' in response.headers.get('Content-Type', ''):
                # 获取文件名
                content_disposition = response.headers.get('Content-Disposition', '')
                filename = None
                if content_disposition:
                    import re
                    matches = re.findall('filename="(.+)"', content_disposition)
                    if matches:
                        filename = matches[0]
                if not filename:
                    filename = report_name or f"performance_comparison_{datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx"
                
                # 保存文件
                file_path = os.path.join("test_result", "comparison_reports", filename)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, 'wb') as f:
                    f.write(response.content)
                return {"success": True, "message": f"对比报表已导出到: {file_path}"}
            else:
                # 如果返回的是JSON错误信息
                try:
                    return {"success": False, "message": response.json().get("msg", "导出失败")}
                except:
                    return {"success": False, "message": f"导出失败，状态码: {response.status_code}"}
        return {"success": False, "message": f"导出失败，状态码: {response.status_code}"}
    
    def get_comparison_reports(self):
        """获取所有对比报告"""
        response = requests.get(self.api_url("/get_comparison_reports/"))
        if response.status_code == 200:
            return response.json().get("msg", [])
        return []
    
    def delete_comparison_report(self, report_id):
        """删除对比报告"""
        url = self.api_url(f"/delete_comparison_report/?report_id={report_id}")
        response = requests.get(url)
        return response.json()


def print_json(data):
    """打印格式化的JSON数据"""
    print(json.dumps(data, indent=2, ensure_ascii=False))


def main():
    """主函数"""
    # 创建命令行解析器
    parser = argparse.ArgumentParser(description="性能对比测试工具")
    
    # 添加参数
    parser.add_argument("action", choices=[
        "list", "set_version", "set_baseline", "get_baseline", 
        "compare", "export", "list_reports", "delete_report", 
        "demo"
    ], help="要执行的操作")
    parser.add_argument("--task-id", type=int, help="任务ID")
    parser.add_argument("--task-ids", type=str, help="任务ID列表，用逗号分隔")
    parser.add_argument("--base-task-id", type=int, help="基准任务ID")
    parser.add_argument("--version", type=str, help="版本号")
    parser.add_argument("--report-id", type=int, help="报告ID")
    parser.add_argument("--report-name", type=str, help="报告名称")
    parser.add_argument("--url", type=str, default="http://127.0.0.1:20223", help="API基础URL")
    
    # 解析命令行参数
    args = parser.parse_args()
    
    # 创建测试器实例
    tester = ComparisonTester(args.url)
    
    # 根据action执行对应操作
    if args.action == "list":
        # 获取所有任务
        tasks = tester.get_all_tasks()
        print(f"找到 {len(tasks)} 个任务:")
        for i, task in enumerate(tasks, 1):
            status_map = {0: "未开始", 1: "执行中", 2: "已完成", 3: "已暂停"}
            status = status_map.get(task.get("status"), "未知")
            print(f"{i}. ID: {task.get('id')}, 名称: {task.get('name')}, 状态: {status}, 版本: {task.get('version', '无')}, 基线: {'是' if task.get('is_baseline') else '否'}")
    
    elif args.action == "set_version":
        # 设置任务版本
        if not args.task_id or not args.version:
            print("错误: 需要指定任务ID (--task-id) 和版本号 (--version)")
            return
            
        result = tester.set_task_version(args.task_id, args.version)
        print_json(result)
    
    elif args.action == "set_baseline":
        # 设置任务为基线版本
        if not args.task_id:
            print("错误: 需要指定任务ID (--task-id)")
            return
            
        result = tester.set_task_baseline(args.task_id)
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


if __name__ == "__main__":
    main() 
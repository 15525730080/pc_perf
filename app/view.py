import asyncio
import base64
import os
import platform
import shutil
import time
import traceback
from pathlib import Path
from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, FileResponse
from starlette.staticfiles import StaticFiles
from app.core.pc_tools import sys_info, pids, screenshot, process_tree
from app.database import TaskCollection
from app.log import log as logger
from app.task_handle import TaskHandle
from app.util import DataCollect
from app.excel_report import create_excel_report
from apscheduler.schedulers.asyncio import AsyncIOScheduler

app = FastAPI()
scheduler = AsyncIOScheduler()
logger.info("工作空间{0}".format(os.getcwd()))
cur_file = Path(__file__)
BASE_CSV_DIR = cur_file.parent.parent.joinpath("test_result")
BASE_CSV_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=BASE_CSV_DIR.resolve()), name="static")


class ResultBean(dict):

    def __init__(self, code=200, msg="success"):
        super().__init__(code=code, msg=msg)


@app.middleware("http")
async def http_filter(request: Request, call_next):
    try:
        response = await call_next(request)
    except BaseException as e:
        logger.error(traceback.format_exc())
        return JSONResponse(content=ResultBean(code=500, msg=str(e)))
    return response


@app.get("/")
def index():
    return RedirectResponse(url="/static/index.html")


@app.get("/system_info/")
async def system_info():
    return JSONResponse(content=ResultBean(msg=await sys_info()))


@app.get("/pid_img/")
async def pid_img(pid: int):
    img_bytes = await screenshot(pid, None)
    base64_encoded = base64.b64encode(img_bytes).decode('utf-8')
    return base64_encoded


@app.get("/get_pids/")
async def get_pids(is_print_tree: bool = False):
    if is_print_tree:
        return JSONResponse(content=ResultBean(msg=await process_tree()))
    else:
        return JSONResponse(content=ResultBean(msg=await pids()))


@app.get("/get_all_task/")
async def get_all_task():
    return JSONResponse(content=ResultBean(msg=await TaskCollection.get_all_task()))


@app.get("/run_task/")
async def run_task(request: Request, pid: int, pid_name: str, task_name: str, include_child: bool = False):
    return_task_id, file_dir = await TaskCollection.create_task(pid, pid_name, BASE_CSV_DIR.resolve(), task_name,
                                                                include_child)

    task_process = TaskHandle(serialno=platform.node(), file_dir=file_dir,
                              task_id=return_task_id, platform=platform.system(), target_pid=pid,
                              include_child=include_child)
    task_process.start()
    return JSONResponse(content=ResultBean())


@app.get("/stop_task/")
async def stop_task(request: Request, task_id: int):
    task = await TaskCollection.stop_task(task_id)
    try:
        TaskHandle.stop_handle(task.get("monitor_pid"))
    except BaseException as e:
        logger.error(e)
        logger.error(traceback.format_exc())
    return JSONResponse(content=ResultBean())


async def check_stop_task_monitor_pid_close():
    logger.info('定期任务执行时间：检查是否有漏杀死monitor进程')
    monitor_pid = await TaskCollection.get_all_stop_task_monitor_pid()
    all_pids = await pids()
    for i in all_pids:
        if int(i["pid"]) in monitor_pid:
            try:
                logger.info("check kill {0}".format(i["pid"]))
                TaskHandle.stop_handle(i["pid"])
            except:
                logger.error(traceback.format_exc())
    logger.info('定期任务执行时间：检查是否有漏杀死monitor进程end')


@app.get("/result/")
async def task_result(request: Request, task_id: int):
    item_task = await TaskCollection.get_item_task(task_id)
    result = await DataCollect(item_task.get("file_dir")).get_all_data()
    return JSONResponse(content=ResultBean(msg=result))


@app.get("/task_status/")
async def task_task(request: Request, task_id: int):
    item_task = await TaskCollection.get_item_task(task_id)
    return JSONResponse(content=ResultBean(msg=item_task.get("status")))  # 0未开始, 1 执行中 , 2 执行完成 3.暂停


@app.get("/delete_task/")
async def delete_task(request: Request, task_id: int):
    item = await TaskCollection.delete_task(task_id)
    if os.path.exists(item.get("file_dir")):
        try:
            shutil.rmtree(item.get("file_dir"))
        except:
            logger.error(traceback.format_exc())
    return JSONResponse(content=ResultBean())


@app.get("/change_task_name/")
async def change_task_name(request: Request, task_id: int, new_name: str):
    item_task = await TaskCollection.change_task_name(task_id, new_name)
    return JSONResponse(content=ResultBean(msg="修改任务名称为：" + item_task.get("name")))


@app.get("/export_excel/")
async def export_excel(request: Request, task_id: int):
    """导出Excel格式的性能报表"""
    try:
        # 记录开始导出
        logger.info(f"开始导出Excel报表: 任务ID={task_id}")
        
        # 获取任务信息
        item_task = await TaskCollection.get_item_task(task_id)
        logger.info(f"获取任务信息成功: {item_task.get('name')}, 路径: {item_task.get('file_dir')}")
        
        # 获取任务数据
        result = await DataCollect(item_task.get("file_dir")).get_all_data()
        logger.info(f"获取任务数据成功: {len(result)} 个数据系列")
        
        # 生成Excel报表
        file_path = create_excel_report(
            item_task.get("name") or f"任务{task_id}", 
            result, 
            item_task.get("file_dir")
        )
        logger.info(f"Excel报表生成成功: {file_path}")
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            logger.error(f"生成的Excel报表文件不存在: {file_path}")
            return JSONResponse(content=ResultBean(code=500, msg=f"生成的Excel报表文件不存在"))
            
        # 返回文件下载响应
        logger.info(f"返回文件下载响应: {os.path.basename(file_path)}")
        return FileResponse(
            path=file_path,
            filename=os.path.basename(file_path),
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        logger.error(f"导出Excel报表失败: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse(content=ResultBean(code=500, msg=f"导出Excel报表失败: {str(e)}"))


@app.get("/set_task_version/")
async def set_task_version(request: Request, task_id: int, version: str):
    """设置任务的版本信息"""
    try:
        task = await TaskCollection.set_task_version(task_id, version)
        return JSONResponse(content=ResultBean(msg=f"已设置任务 {task_id} 的版本为 {version}"))
    except Exception as e:
        logger.error(f"设置任务版本失败: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse(content=ResultBean(code=500, msg=f"设置任务版本失败: {str(e)}"))


@app.get("/set_task_baseline/")
async def set_task_baseline(request: Request, task_id: int, is_baseline: bool = True):
    """设置任务为基线版本"""
    try:
        task = await TaskCollection.set_task_baseline(task_id, is_baseline)
        status = "基线" if is_baseline else "非基线"
        return JSONResponse(content=ResultBean(msg=f"已设置任务 {task_id} 为{status}版本"))
    except Exception as e:
        logger.error(f"设置任务基线状态失败: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse(content=ResultBean(code=500, msg=f"设置任务基线状态失败: {str(e)}"))


@app.get("/get_baseline_task/")
async def get_baseline_task(request: Request):
    """获取基线任务信息"""
    try:
        task = await TaskCollection.get_baseline_task()
        if task:
            return JSONResponse(content=ResultBean(msg=task))
        else:
            return JSONResponse(content=ResultBean(msg=None, code=404))
    except Exception as e:
        logger.error(f"获取基线任务信息失败: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse(content=ResultBean(code=500, msg=f"获取基线任务信息失败: {str(e)}"))


@app.get("/compare_tasks/")
async def compare_tasks(request: Request, task_ids: str, base_task_id: int = None):
    """比较多个任务的性能数据"""
    try:
        from app.comparison import TaskComparison
        
        task_id_list = [int(task_id.strip()) for task_id in task_ids.split(",")]
        
        if not task_id_list:
            return JSONResponse(content=ResultBean(code=400, msg="未提供有效的任务ID"))
            
        comparison_data = await TaskComparison.create_comparison(task_id_list, base_task_id)
        return JSONResponse(content=ResultBean(msg=comparison_data))
    except Exception as e:
        logger.error(f"对比任务失败: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse(content=ResultBean(code=500, msg=f"对比任务失败: {str(e)}"))


@app.get("/export_comparison_excel/")
async def export_comparison_excel(request: Request, task_ids: str, base_task_id: int = None, report_name: str = None):
    """导出对比Excel报表"""
    try:
        from app.comparison import TaskComparison
        from app.comparison_report import create_comparison_excel
        from app.database import ComparisonReportCollection
        
        # 解析任务ID列表
        task_id_list = [int(task_id.strip()) for task_id in task_ids.split(",")]
        
        if not task_id_list:
            return JSONResponse(content=ResultBean(code=400, msg="未提供有效的任务ID"))
        
        # 获取对比数据
        comparison_data = await TaskComparison.create_comparison(task_id_list, base_task_id)
        
        # 生成Excel报表
        if not report_name:
            report_name = f"性能对比报告_{time.strftime('%Y%m%d_%H%M%S')}"
            
        file_path = await create_comparison_excel(comparison_data, report_name)
        
        # 保存对比报告记录
        report = await ComparisonReportCollection.create_report(
            name=report_name,
            task_ids=task_id_list,
            base_task_id=base_task_id or task_id_list[0],
            description=f"对比任务: {', '.join(str(tid) for tid in task_id_list)}"
        )
        
        # 更新报告路径
        await ComparisonReportCollection.update_report(report["id"], report_path=file_path)
        
        # 返回文件下载响应
        return FileResponse(
            path=file_path,
            filename=os.path.basename(file_path),
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        logger.error(f"导出对比报表失败: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse(content=ResultBean(code=500, msg=f"导出对比报表失败: {str(e)}"))


@app.get("/get_comparison_reports/")
async def get_comparison_reports(request: Request):
    """获取所有对比报告"""
    try:
        from app.database import ComparisonReportCollection
        reports = await ComparisonReportCollection.get_all_reports()
        return JSONResponse(content=ResultBean(msg=reports))
    except Exception as e:
        logger.error(f"获取对比报告列表失败: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse(content=ResultBean(code=500, msg=f"获取对比报告列表失败: {str(e)}"))


@app.get("/delete_comparison_report/")
async def delete_comparison_report(request: Request, report_id: int):
    """删除对比报告"""
    try:
        from app.database import ComparisonReportCollection
        report = await ComparisonReportCollection.delete_report(report_id)
        
        # 如果存在报告文件，删除文件
        if report and "report_path" in report and report["report_path"]:
            try:
                if os.path.exists(report["report_path"]):
                    os.remove(report["report_path"])
            except Exception as e:
                logger.error(f"删除对比报告文件失败: {str(e)}")
        
        return JSONResponse(content=ResultBean(msg="对比报告已删除"))
    except Exception as e:
        logger.error(f"删除对比报告失败: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse(content=ResultBean(code=500, msg=f"删除对比报告失败: {str(e)}"))


@app.on_event("startup")
async def app_start():
    # 创建数据库表
    from app.database import create_table
    await create_table()

    scheduler.add_job(check_stop_task_monitor_pid_close, 'interval', seconds=60)
    scheduler.start()

@app.on_event("shutdown")
async def app_shutdown():
    # 关闭调度器，确保资源释放
    scheduler.shutdown()
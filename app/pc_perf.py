import pyximport
pyximport.install(language_level=3)
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
from starlette.responses import JSONResponse, RedirectResponse
from starlette.staticfiles import StaticFiles
from app.core.pc_tools import sys_info, pids, screenshot
from app.database import TaskCollection
from app.log import log as logger
from app.task_handle import TaskHandle
from app.util import DataCollect
from apscheduler.schedulers.background import BackgroundScheduler

app = FastAPI()
scheduler = BackgroundScheduler()
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
async def get_pids():
    return JSONResponse(content=ResultBean(msg=await pids()))


@app.get("/get_all_task/")
async def get_all_task():
    return JSONResponse(content=ResultBean(msg=await TaskCollection.get_all_task()))


@app.get("/run_task/")
async def run_task(request: Request, pid: int, pid_name: str, task_name: str):
    start_time = time.time()
    status = 0
    return_task_id, file_dir = await TaskCollection.create_task(pid, pid_name, BASE_CSV_DIR.resolve(), task_name)

    task_process = TaskHandle(serialno=platform.node(), file_dir=file_dir,
                              task_id=return_task_id, platform=platform.system(), target_pid=pid)
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


def check_stop_task_monitor_pid_close():
    async def func():
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

    asyncio.run(func())


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


@app.on_event("startup")
async def app_start():
    scheduler.add_job(check_stop_task_monitor_pid_close, 'interval', seconds=60)
    scheduler.start()

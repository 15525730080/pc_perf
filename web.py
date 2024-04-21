import base64
import multiprocessing
import os
import platform
import shutil
import threading
import time
import traceback
import webbrowser
import sys
from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.staticfiles import StaticFiles
from core.pc_tools import sys_info, pids, screenshot
from dao import TaskCollection
from log import log as logger
from task_handle import TaskHandle
from util import DataCollect


app = FastAPI()
logger.info("工作空间{0}".format(os.getcwd()))
BASE_CSV_DIR = os.path.join(os.path.dirname(__file__), "test_result")
if not os.path.exists(BASE_CSV_DIR):
    os.mkdir(BASE_CSV_DIR)
app.mount("/static", StaticFiles(directory=BASE_CSV_DIR), name="static")


class ResultBean(dict):

    def __init__(self, code=200, msg="success"):
        super().__init__(code=code, msg=msg)


@app.middleware("http")
async def http_filter(request: Request, call_next):
    try:
        response = await call_next(request)
    except BaseException as e:
        logger.error(str(e))
        traceback.print_exc()
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
    return_task_id, file_dir = await TaskCollection.create_task(pid, pid_name, BASE_CSV_DIR, task_name)

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
        traceback.print_exc()
    return JSONResponse(content=ResultBean())


@app.get("/result/")
async def task_result(request: Request, task_id: int):
    item_task = await TaskCollection.get_item_task(task_id)
    result = await DataCollect(item_task.get("file_dir")).get_all_data()
    return JSONResponse(content=ResultBean(msg=result))


@app.get("/task_status/")
async def task_task(request: Request, task_id: int):
    item_task = await TaskCollection.get_item_task(task_id)
    return JSONResponse(content=ResultBean(msg=item_task.status))  # 0未开始, 1 执行中 , 2 执行完成 3.暂停


@app.get("/delete_task/")
async def delete_task(request: Request, task_id: int):
    item = await TaskCollection.delete_task(task_id)
    if os.path.exists(item.get("file_dir")):
        try:
            shutil.rmtree(item.get("file_dir"))
        except:
            traceback.print_exc()
    return JSONResponse(content=ResultBean())


def open_url():
    time.sleep(2)
    webbrowser.open("http://127.0.0.1:80")


def main():
    if __name__ == "__main__":
        import uvicorn
        multiprocessing.freeze_support()
        threading.Thread(target=open_url).start()
        logger.info("服务启动请访问: http://localhost:80")
        uvicorn.run("web:app", host="0.0.0.0", port=80, log_level="error", reload=False)


if __name__ == "__main__":
    main()

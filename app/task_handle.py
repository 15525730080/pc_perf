# coding=utf-8
import asyncio
import os
import traceback
from builtins import *
from multiprocessing.context import Process

import psutil

from app.database import TaskCollection
from app.log import log as logger
from app.core.pc_tools import perf as pc_perf


class TaskHandle(Process):

    def __init__(self, serialno: str, target_pid: int, file_dir: str, task_id: int, platform: str, include_child:bool):
        super(TaskHandle, self).__init__()
        self.serialno = serialno
        self.target_pid = target_pid
        self.file_dir = file_dir
        self.include_child = include_child
        if not os.path.exists(self.file_dir):
            os.makedirs(self.file_dir)
        self.daemon = True
        self.task_id = task_id
        self.platform = platform  # platform.system()

    def start(self):
        logger.info("join task handle")
        super().start()

    def run(self):
        logger.info("join task handle run")
        asyncio.run(TaskCollection.set_task_running(self.task_id, self.pid))
        asyncio.run(pc_perf(self.target_pid, self.file_dir, include_child=self.include_child))

    @staticmethod
    def stop_handle(monitor_pid):
        logger.info("Stopping task handle and subprocesses... {0}".format(monitor_pid))
        # kill the pc_perf subprocess
        current_process = psutil.Process(monitor_pid)
        try:
            for child in current_process.children(recursive=True):
                os.kill(child.pid, 9)
        except Exception as e:
            logger.error(e)
        finally:
            try:
                os.kill(current_process.pid, 9)
            except:
                logger.error(traceback.format_exc())



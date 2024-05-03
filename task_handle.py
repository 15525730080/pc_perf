# coding=utf-8
import asyncio
import os
import traceback
from builtins import *
from multiprocessing.context import Process

import psutil

from dao import TaskCollection
from log import log as logger
from core.pc_tools import perf as pc_perf


class TaskHandle(Process):

    def __init__(self, serialno: str, target_pid: int, file_dir: str, task_id: int, platform: str):
        super(TaskHandle, self).__init__()
        self.serialno = serialno
        self.target_pid = target_pid
        self.file_dir = file_dir
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
        asyncio.run(pc_perf(self.target_pid, self.file_dir))

    @staticmethod
    def stop_handle(monitor_pid):
        logger.info("Stopping task handle and subprocesses... {0}".format(monitor_pid))
        # Terminate the pc_perf subprocess
        current_process = psutil.Process(monitor_pid)
        try:
            for child in current_process.children(recursive=True):
                child.terminate()
                child.wait(0.2)
        except Exception as e:
            logger.error(e)
        finally:
            try:
                current_process.terminate()
                current_process.wait(1)
            except:
                logger.error(traceback.print_exc())

if __name__ == '__main__':
    TaskHandle.stop_handle(15160)

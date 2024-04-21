import asyncio
import csv
import inspect
import json
import time
from pathlib import Path

from log import log as logger


def print_json(data, *args, **kwargs):
    data_json = json.dumps(data)
    logger.info(data_json, *args, **kwargs)


class MonitorIter(object):

    def __init__(self, stop_event):
        self.stop_event = stop_event

    def __aiter__(self):
        return self

    def __anext__(self):
        if self.stop_event.is_set():
            future = asyncio.Future()
            future.set_result(None)
            return future
        elif not self.stop_event.is_set():
            raise StopAsyncIteration()


class Monitor(object):

    def __init__(self, func, **kwargs):
        super(Monitor, self).__init__()
        self.stop_event = asyncio.Event()
        self.func = func
        self.kwargs = kwargs
        self.stop_event.set()
        self.key_value = kwargs.get("key_value", [])
        self.name = self.func.__name__
        self.save_dir = kwargs.get("save_dir")
        self.is_out = self.kwargs.get("is_out", True)
        if self.is_out:
            dir_instance = Path(self.save_dir)
            if not dir_instance.exists():
                dir_instance.mkdir()
            csv_instance = dir_instance.joinpath(self.name + ".csv")
            self.csv_path = csv_instance.resolve()
            with open(self.csv_path, "w", encoding="utf-8", newline="") as f:
                csv_writer = csv.writer(f)
                csv_writer.writerow(self.key_value)
            self.key_value = [key.split("(")[0] for key in self.key_value]

    async def run(self):
        async for _ in MonitorIter(self.stop_event):
            before_func = time.time()
            param_names = inspect.signature(self.func).parameters.keys()
            params = {name: self.kwargs.get(name) for name in param_names}
            print(params)
            res = await self.func(**params)
            if self.is_out and res:
                with open(self.csv_path, "a+", encoding="utf-8", newline="") as f:
                    csv_writer = csv.writer(f)
                    csv_writer.writerow([res.get(key, "") for key in self.key_value])
            end_func = time.time()
            if interval_time := (int(end_func) - int(before_func)) <= 1:
                await asyncio.sleep(interval_time)

    def stop(self):
        self.stop_event.clear()

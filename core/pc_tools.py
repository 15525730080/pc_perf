import asyncio
import json
import platform
import subprocess
import threading
import time
import traceback
from io import BytesIO
import psutil
import pynvml
from pathlib import Path
from log import log
from core.monitor import Monitor

SUPPORT_GPU = True
try:
    pynvml.nvmlInit()
except:
    log.error(traceback.format_exc())
    log.info("本设备gpu获取不适配")
    SUPPORT_GPU = False
from PIL import ImageGrab


def print_json(msg):
    log.info(json.dumps(msg))


class WinFps(object):
    frame_que = list()
    single_instance = None
    fps_process = None

    def __init__(self, pid):
        self.pid = pid

    def __new__(cls, *args, **kwargs):
        if not cls.single_instance:
            cls.single_instance = super().__new__(cls)
        return cls.single_instance

    def fps(self):
        if not WinFps.fps_process:
            threading.Thread(target=self.start_fps_collect, args=(self.pid,)).start()
        if self.check_queue_head_frames_complete():
            return self.pop_complete_fps()

    @staticmethod
    def check_queue_head_frames_complete():
        if not WinFps.frame_que:
            return False
        head_time = int(WinFps.frame_que[0])
        end_time = int(WinFps.frame_que[-1])
        if head_time == end_time:
            return False
        return True

    @staticmethod
    def pop_complete_fps():
        head_time = int(WinFps.frame_que[0])
        complete_fps = []
        while int(WinFps.frame_que[0]) == head_time:
            complete_fps.append(WinFps.frame_que.pop(0))
        return complete_fps

    def start_fps_collect(self, pid):
        start_fps_collect_time = int(time.time())
        PresentMon = Path(__file__).parent.parent.joinpath("PresentMon.exe")
        res_terminate = subprocess.Popen(
            [PresentMon, "-process_id", str(pid), "-output_stdout", "-stop_existing_session"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        WinFps.fps_process = res_terminate
        res_terminate.stdout.readline()
        while not res_terminate.poll():
            line = res_terminate.stdout.readline()
            if not line:
                try:
                    res_terminate.kill()
                except:
                    traceback.print_exc()
                break
            try:
                line = line.decode(encoding="utf-8")
                line_list = line.split(",")
                print("line ", line_list)
                WinFps.frame_que.append(start_fps_collect_time + round(float(line_list[7]), 7))
            except:
                time.sleep(1)
                log.error(traceback.format_exc())


async def sys_info():
    def real_func():
        current_platform = platform.system()
        computer_name = platform.node()
        res = {"platform": current_platform, "computer_name": computer_name, "time": time.time(),
               "cpu_cores": psutil.cpu_count(), "ram": "{0}G".format(int(psutil.virtual_memory().total / 1024 ** 3)),
               "rom": "{0}G".format(int(psutil.disk_usage('/').total / 1024 ** 3))}
        print_json(res)
        return res

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=10)


async def pids():
    def real_func():
        process_list = []
        for proc in psutil.process_iter(attrs=['name', 'pid', 'cmdline', 'username']):
            try:
                if proc.is_running():
                    process_list.append(
                        {"name": proc.info['name'], "pid": proc.info['pid'], "cmd": proc.info['cmdline'],
                         "username": proc.username()})
            except Exception as e:
                log.error(e)
        process_list.sort(key=lambda x: x['name'])
        # print_json(process_list)
        return process_list

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=10)


async def screenshot(pid, save_dir):
    def real_func(pid, save_dir):
        start_time = int(time.time())
        if pid:
            window = None
            if platform.system() == "Windows":
                import ctypes
                import pygetwindow as gw
                def get_pid(hwnd):
                    pid = ctypes.wintypes.DWORD()
                    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    return pid.value

                def get_window_by_pid(pid):
                    for window in gw.getAllWindows():
                        if get_pid(window._hWnd) == pid:
                            return window
                    return None

                window = get_window_by_pid(int(pid))
            if window:
                screenshot = ImageGrab.grab(
                    bbox=(window.left, window.top, window.left + window.width, window.top + window.height),
                    all_screens=True)
            else:
                screenshot = ImageGrab.grab(all_screens=True)
            if save_dir:
                dir_instance = Path(save_dir)
                screenshot_dir = dir_instance.joinpath("screenshot")
                screenshot_dir.mkdir(exist_ok=True)
                screenshot.save(screenshot_dir.joinpath(str(start_time) + ".png"), format="PNG")
            else:
                output_buffer = BytesIO()
                screenshot.save(output_buffer, format='PNG')
                output_buffer.seek(0)  # 重置缓冲区指针
                image_data = output_buffer.getvalue()
                return image_data

    return await asyncio.wait_for(asyncio.to_thread(real_func, pid, save_dir), timeout=10)


async def cpu(pid):
    def real_func(pid):
        start_time = int(time.time())
        proc = psutil.Process(pid=int(pid))
        cpu_usage = proc.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        res = {"cpu_usage": cpu_usage / cpu_count, "cpu_usage_all": cpu_usage,
               "cpu_core_num": cpu_count, "time": start_time}
        print_json(res)
        return res

    return await asyncio.wait_for(asyncio.to_thread(real_func, pid), timeout=10)


async def memory(pid):
    def real_func(pid):
        start_time = int(time.time())
        process = psutil.Process(int(pid))
        process_memory_info = process.memory_info()
        process_memory_usage = process_memory_info.rss / (1024 ** 2)  # In MB
        memory_info = {"process_memory_usage": process_memory_usage, "time": start_time}
        print_json(memory_info)
        return memory_info

    return await asyncio.wait_for(asyncio.to_thread(real_func, pid), timeout=10)


async def fps(pid):
    if platform.system() != "Windows":
        return {"type": "fps", "time": int(time.time())}
    frames = WinFps(pid).fps()
    if not frames:
        return frames
    res = {"type": "fps", "fps": len(frames), "frames": frames, "time": int(frames[0]) if frames else int(time.time())}
    print_json(res)
    return res


async def gpu(pid):
    def real_func(pid):
        pid = int(pid)
        start_time = int(time.time())
        if SUPPORT_GPU:
            device_count = pynvml.nvmlDeviceGetCount()
            res = None
            for i in range(device_count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                processes = pynvml.nvmlDeviceGetComputeRunningProcesses(handle)
                for process in processes:
                    print(process)
                    if process.pid == pid:
                        gpu_Utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
                        gpu_utilization_percentage = gpu_Utilization.gpu  # GPU的计算使用率
                        res = {"gpu": gpu_utilization_percentage, "time": start_time}
                        print_json(res)
                        return res
            return res
        else:
            return {"time": start_time}

    return await asyncio.wait_for(asyncio.to_thread(real_func, pid), timeout=10)


async def process_info(pid):
    def real_func(pid):
        start_time = int(time.time())
        process = psutil.Process(int(pid))
        num_handles = None
        num_threads = None
        try:
            num_handles = process.num_handles()
        except:
            log.error(traceback.format_exc())
        try:
            num_threads = process.num_threads()
        except:
            log.error(traceback.format_exc())
        res = {"time": start_time}
        if num_handles: res["num_handles"] = num_handles
        if num_threads: res["num_threads"] = num_threads
        print_json(res)
        return res

    return await asyncio.wait_for(asyncio.to_thread(real_func, pid), timeout=10)


async def perf(pid, save_dir):
    monitors = {
        "cpu": Monitor(cpu,
                       pid=pid,
                       key_value=["time", "cpu_usage(%)", "cpu_usage_all(%)", "cpu_core_num(个)"],
                       save_dir=save_dir),
        "memory": Monitor(memory,
                          pid=pid,
                          key_value=["time", "process_memory_usage(M)"],
                          save_dir=save_dir),
        "process_info": Monitor(process_info,
                                pid=pid,
                                key_value=["time", "num_threads(个)", "num_handles(个)"],
                                save_dir=save_dir),
        "fps": Monitor(fps,
                       pid=pid,
                       key_value=["time", "fps(帧)", "frames"],
                       save_dir=save_dir),
        "gpu": Monitor(gpu,
                       pid=pid,
                       key_value=["time", "gpu(%)"],
                       save_dir=save_dir),
        "screenshot": Monitor(screenshot,
                              pid=pid,
                              save_dir=save_dir, is_out=False)
    }
    run_monitors = [monitor.run() for name, monitor in monitors.items()]
    await asyncio.gather(*run_monitors)

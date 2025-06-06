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
from app.log import log
from app.core.monitor import Monitor

SUPPORT_GPU = True
try:
    pynvml.nvmlInit()
except:
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
        PresentMon = Path(__file__).parent.parent.parent.joinpath("PresentMon.exe")
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


async def process_tree():
    def real_func():
        process_list = []
        for proc in psutil.process_iter(attrs=['name', 'pid', 'cmdline', 'username', 'ppid']):
            try:
                # 检查进程是否正在运行且父进程 ID 为 1
                if proc.is_running() and proc.ppid() == 1:
                    process_info = {
                        "name": proc.info['name'],
                        "ppid": proc.info['ppid'],
                        "pid": proc.info['pid'],
                        "cmd": proc.info['cmdline'],
                        "username": proc.username(),
                        "child_p": []
                    }
                    try:
                        # 获取子进程信息
                        children = proc.children(recursive=True)
                        for child in children:
                            try:
                                child_info = {
                                    "name": child.name(),
                                    "ppid": child.ppid(),
                                    "pid": child.pid,
                                    "cmd": child.cmdline(),
                                    "username": child.username()
                                }
                                process_info["child_p"].append(child_info)
                            except Exception:
                                # 处理子进程不存在的情况
                                log.error(f"子进程 {child.pid} 已不存在")
                    except psutil.NoSuchProcess:
                        # 处理父进程不存在的情况
                        log.error(f"父进程 {proc.pid} 已不存在")
                    process_list.append(process_info)
            except Exception as e:
                log.error(e)
        process_list.sort(key=lambda x: -len(x['child_p']))
        # print_json(process_list)
        return process_list

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=10)

async def screenshot(pid, save_dir, include_child=False):
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
                
                def get_window_by_pid(pids):
                    for window in gw.getAllWindows():
                        if get_pid(window._hWnd) in pids:
                            return window
                    return None
                
                pids = [pid]
                if include_child:
                    process = psutil.Process(int(pid))
                    p_chs = process.children(recursive=True)
                    if p_chs:
                        sub_pid = [sub_p.pid for sub_p in p_chs]
                        pids.extend(sub_pid)
                window = get_window_by_pid(pids)
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


async def cpu(pid, include_child=False):
    process = psutil.Process(int(pid))
    get_main_cpu = asyncio.to_thread(process.cpu_percent, interval=1)
    tasks = [get_main_cpu]
    if include_child:
        children = process.children(recursive=True)
        if children:
            tasks.extend([asyncio.to_thread(child.cpu_percent, interval=1) 
                         for child in children])   
    all_cpu_values = await asyncio.gather(*tasks, return_exceptions=True)
    total_cpu_usage = sum(v for v in all_cpu_values if not isinstance(v, Exception))
    cpu_count = psutil.cpu_count()
    res = {
        "cpu_usage": total_cpu_usage / cpu_count,
        "cpu_usage_all": total_cpu_usage,
        "cpu_core_num": cpu_count,
        "time": int(time.time())
    }
    print_json(res)
    return res

async def memory(pid, include_child=False):
    process = psutil.Process(int(pid))
    get_main_mem = asyncio.to_thread(lambda: process.memory_info().rss / (1024 ** 2))
    tasks = [get_main_mem]
    if include_child:
        p_chs = process.children(recursive=True)
        if p_chs:
            tasks.extend([asyncio.to_thread(lambda p=sub_p: p.memory_info().rss / (1024 ** 2)) 
                         for sub_p in p_chs])
    all_mem_values = await asyncio.gather(*tasks, return_exceptions=True)
    total_memory = sum(v for v in all_mem_values if not isinstance(v, Exception))
    res = {"process_memory_usage": total_memory, "time": int(time.time())}
    print_json(res)
    return res

async def fps(pid, include_child=False):
    pid = int(pid)
    if platform.system() != "Windows":
        return {"type": "fps", "time": int(time.time())}
    frames = WinFps(pid).fps()
    if not frames:
        return frames
    res = {"type": "fps", "fps": len(frames), "frames": frames, "time": int(frames[0]) if frames else int(time.time())}
    print_json(res)
    return res


async def gpu(pid, include_child=False):
    pid = int(pid)
    def real_func(pid):
        pids = [pid]
        if include_child:
            process = psutil.Process(int(pid))
            p_chs = process.children(recursive=True)
            if p_chs:
                sub_pid = [sub_p.pid for sub_p in p_chs]
                pids.extend(sub_pid)
        start_time = int(time.time())
        sum_gpu = 0
        if SUPPORT_GPU:
            device_count = pynvml.nvmlDeviceGetCount()
            res = None
            for i in range(device_count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                processes = pynvml.nvmlDeviceGetComputeRunningProcesses(handle)
                for process in processes:
                    if process.pid in pids:
                        gpu_Utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
                        gpu_utilization_percentage = gpu_Utilization.gpu  # GPU的计算使用率
                        sum_gpu += gpu_utilization_percentage
            res = {"gpu": gpu_utilization_percentage, "time": start_time}
            return res
        else:
            return {"time": start_time}

    return await asyncio.wait_for(asyncio.to_thread(real_func, pid), timeout=10)


async def process_info(pid, include_child=False):
    start_time = int(time.time())
    process = psutil.Process(int(pid))
    num_handles = None
    if hasattr(process, "num_handles"):
        get_main_num_handles = asyncio.to_thread(process.num_handles)
    get_main_num_threads = asyncio.to_thread(process.num_threads)
    if hasattr(process, "num_handles"):
        handles_task = [get_main_num_handles]
    threads_task = [get_main_num_threads]
    if include_child:
        children = process.children(recursive=True)
        if children:
            if hasattr(process, "num_handles"):
                handles_task.extend([asyncio.to_thread(child.num_handles) for child in children])  
            threads_task.extend([asyncio.to_thread(child.num_threads) for child in children])  
    if hasattr(process, "num_handles"):
        all_num_handles_values = await asyncio.gather(*handles_task, return_exceptions=True)
    all_num_threads_values = await asyncio.gather(*threads_task, return_exceptions=True)
    if hasattr(process, "num_handles"):
        num_handles = sum(v for v in all_num_handles_values if not isinstance(v, Exception))
    num_threads= sum(v for v in all_num_threads_values if not isinstance(v, Exception))
    res = {"time": start_time}
    if num_handles: res["num_handles"] = num_handles
    if num_threads: res["num_threads"] = num_threads
    return res


async def perf(pid, save_dir, include_child):
    monitors = {
        "cpu": Monitor(cpu,
                       pid=pid,
                       key_value=["time", "cpu_usage(%)", "cpu_usage_all(%)", "cpu_core_num(个)"],
                       save_dir=save_dir, include_child=include_child),
        "memory": Monitor(memory,
                          pid=pid,
                          key_value=["time", "process_memory_usage(M)"],
                          save_dir=save_dir, include_child=include_child),
        "process_info": Monitor(process_info,
                                pid=pid,
                                key_value=["time", "num_threads(个)", "num_handles(个)"],
                                save_dir=save_dir, include_child=include_child),
        "fps": Monitor(fps,
                       pid=pid,
                       key_value=["time", "fps(帧)", "frames"],
                       save_dir=save_dir, include_child=include_child),
        "gpu": Monitor(gpu,
                       pid=pid,
                       key_value=["time", "gpu(%)"],
                       save_dir=save_dir, include_child=include_child),
        "screenshot": Monitor(screenshot,
                              pid=pid,
                              save_dir=save_dir, is_out=False, include_child=include_child)
    }
    run_monitors = [monitor.run() for name, monitor in monitors.items()]
    await asyncio.gather(*run_monitors)

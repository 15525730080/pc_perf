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
from app.log import log as logger
from app.core.monitor import Monitor

# 定义常量
MB_CONVERSION = 1024 * 1024

SUPPORT_GPU = True
try:
    pynvml.nvmlInit()
except:
    logger.info("本设备gpu获取不适配")
    SUPPORT_GPU = False
from PIL import ImageGrab


def print_json(msg):
    logger.info(json.dumps(msg))


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
                except Exception as e:
                    logger.error(e)
                break
            try:
                line = line.decode(encoding="utf-8")
                line_list = line.split(",")
                WinFps.frame_que.append(start_fps_collect_time + round(float(line_list[7]), 7))
            except:
                time.sleep(1)
                logger.error(traceback.format_exc())


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
                logger.error(e)
        process_list.sort(key=lambda x: x['name'])
        # print_json(process_list)
        return process_list

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=10)


def get_visible_top_level_windows():
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    EnumWindows = user32.EnumWindows
    IsWindowVisible = user32.IsWindowVisible
    GetWindowTextLengthW = user32.GetWindowTextLengthW
    GetWindowTextW = user32.GetWindowTextW
    GetWindowThreadProcessId = user32.GetWindowThreadProcessId

    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    results = []

    @EnumWindowsProc
    def enum_proc(hwnd, lParam):
        if IsWindowVisible(hwnd):
            length = GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.strip()
                if title:
                    pid = wintypes.DWORD()
                    GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    results.append(pid.value)
        return True

    EnumWindows(enum_proc, 0)
    return results


async def process_tree():
    def real_func():
        process_list = []
        if platform.system() == "Windows":
            appliction_pids = get_visible_top_level_windows()
        else:
            appliction_pids = [0, 1]
        for proc in psutil.process_iter(attrs=['name', 'pid', 'cmdline', 'username', 'ppid']):
            try:
                # 检查进程是否正在运行且父进程 ID 为 1
                if proc.is_running() and (
                        proc.pid if platform.system() == "Windows" else proc.ppid()) in appliction_pids:
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
                                logger.error(f"子进程 {child.pid} 已不存在")
                    except psutil.NoSuchProcess:
                        # 处理父进程不存在的情况
                        logger.error(f"父进程 {proc.pid} 已不存在")
                    process_list.append(process_info)
            except Exception as e:
                logger.error(e)
        process_list.sort(key=lambda x: -len(x['child_p']))
        # print_json(process_list)
        return process_list

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=10)


async def screenshot(pid, save_dir, include_child=False):
    def real_func(pid, save_dir):
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
                screenshot.save(screenshot_dir.joinpath(str(int(time.time() + 0.5)) + ".png"), format="PNG")
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
    # print_json(res)
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
            gpu_utilization_percentage = None
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
    num_threads = sum(v for v in all_num_threads_values if not isinstance(v, Exception))
    res = {"time": start_time}
    if num_handles: res["num_handles"] = num_handles
    if num_threads: res["num_threads"] = num_threads
    return res


async def disk_io(pid, include_child=False):
    """监控进程的磁盘I/O指标"""
    process = psutil.Process(int(pid))
    # 获取初始IO计数
    try:
        # 获取主进程的IO计数器
        get_main_io = asyncio.to_thread(process.io_counters)
        prev_io = await get_main_io
        prev_disk_read = prev_io.read_bytes
        prev_disk_write = prev_io.write_bytes
        
        # 休眠一小段时间以计算速率
        await asyncio.sleep(1)
        
        # 获取更新后的IO计数器
        current_io = await asyncio.to_thread(process.io_counters)
        disk_read = current_io.read_bytes
        disk_write = current_io.write_bytes
        
        # 计算磁盘I/O速率，增加最小检测阈值
        disk_read_rate = max(0, (disk_read - prev_disk_read) / MB_CONVERSION) 
        disk_write_rate = max(0, (disk_write - prev_disk_write) / MB_CONVERSION)
        
        # 忽略小于1KB的读写操作
        if disk_read_rate < 0.001:  # 约1KB/s
            disk_read_rate = 0
        if disk_write_rate < 0.001:
            disk_write_rate = 0
            
        res = {
            "disk_read_rate": round(disk_read_rate, 2),  # MB/s
            "disk_write_rate": round(disk_write_rate, 2),  # MB/s
            "disk_read": disk_read,  # 总读取字节数
            "disk_write": disk_write,  # 总写入字节数
            "time": int(time.time())
        }
        
        logger.info(json.dumps(res))
        return res
    except (psutil.AccessDenied, AttributeError) as e:
        logger.error(f"获取磁盘I/O数据失败: {str(e)}")
        return {"disk_read_rate": 0, "disk_write_rate": 0, "time": int(time.time())}


async def network_io(pid, include_child=False):
    """监控进程的网络I/O指标"""
    start_time = int(time.time())
    
    try:
        # 获取初始网络计数
        net_io = psutil.net_io_counters()
        prev_net_sent = net_io.bytes_sent
        prev_net_recv = net_io.bytes_recv
        
        # 休眠一小段时间以计算速率
        await asyncio.sleep(1)
        
        # 获取更新后的网络计数
        current_net_io = psutil.net_io_counters()
        net_sent = current_net_io.bytes_sent
        net_recv = current_net_io.bytes_recv
        
        # 计算网络IO速率
        net_sent_rate = max(0, (net_sent - prev_net_sent) / MB_CONVERSION)
        net_recv_rate = max(0, (net_recv - prev_net_recv) / MB_CONVERSION)
        
        # 忽略小于1KB的网络传输
        if net_sent_rate < 0.001:
            net_sent_rate = 0
        if net_recv_rate < 0.001:
            net_recv_rate = 0
            
        res = {
            "net_sent_rate": round(net_sent_rate, 2),  # MB/s
            "net_recv_rate": round(net_recv_rate, 2),  # MB/s
            "net_sent": net_sent,  # 总发送字节数
            "net_recv": net_recv,  # 总接收字节数
            "time": start_time
        }
        
        logger.info(json.dumps(res))
        return res
    except Exception as e:
        logger.error(f"获取网络I/O数据失败: {str(e)}")
        return {"net_sent_rate": 0, "net_recv_rate": 0, "time": start_time}


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
        "disk_io": Monitor(disk_io,
                          pid=pid,
                          key_value=["time", "disk_read_rate(MB/s)", "disk_write_rate(MB/s)", "disk_read(字节)", "disk_write(字节)"],
                          save_dir=save_dir, include_child=include_child),
        "network_io": Monitor(network_io,
                             pid=pid,
                             key_value=["time", "net_sent_rate(MB/s)", "net_recv_rate(MB/s)", "net_sent(字节)", "net_recv(字节)"],
                             save_dir=save_dir, include_child=include_child),
        "screenshot": Monitor(screenshot,
                              pid=pid,
                              save_dir=save_dir, is_out=False, include_child=include_child)
    }
    run_monitors = [monitor.run() for name, monitor in monitors.items()]
    await asyncio.gather(*run_monitors)

# coding:utf-8
"""
HarmonyOS 性能测试模块
通过 hdc（HarmonyOS Device Connector）命令行工具采集设备性能数据。

依赖：hdc 工具需在 PATH 中，或通过 HDC_PATH 环境变量指定路径。
安装方式：随 DevEco Studio 或 HarmonyOS SDK 一起安装，通常位于 SDK/toolchains/ 目录。

支持的指标：
  - CPU 使用率（/proc/stat + /proc/<pid>/stat）
  - 内存使用（hidumper --mem 或 /proc/<pid>/status）
  - 网络 IO（/proc/net/dev 两次采样差值）
  - 磁盘 IO（/proc/<pid>/io 两次采样差值）
  - 电池信息（hidumper -s BatteryService）
  - FPS（hidumper -s RenderService）
  - 截图（hdc shell snapshot_display）
  - 进程信息（线程数、FD 数）
"""
import asyncio
import json
import os
import re
import shutil
import subprocess
import time
import threading
from pathlib import Path
from typing import Optional, Dict, List

from app.log import log as logger
from app.core.monitor import Monitor

# ─────────────────────────── hdc 路径 ───────────────────────────

HDC_PATH = (
    os.environ.get("HDC_PATH")
    or shutil.which("hdc")
)

if not HDC_PATH:
    logger.warning("hdc 未找到，HarmonyOS 性能测试不可用。请安装 DevEco Studio 或 HarmonyOS SDK 并将 hdc 加入 PATH，或设置 HDC_PATH 环境变量")

HDC_AVAILABLE = bool(HDC_PATH)


def _hdc(args: list, serial: str = None, timeout: int = 15) -> Optional[str]:
    """
    执行 hdc 命令，返回输出字符串。
    若指定 serial，则加 -t <serial> 参数。
    """
    if not HDC_PATH:
        return None
    cmd = [HDC_PATH]
    if serial:
        cmd += ["-t", serial]
    cmd += args
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8"
        )
        out = result.stdout.strip()
        if out:
            return out
        err = result.stderr.strip()
        if err:
            return err
        return None
    except subprocess.TimeoutExpired:
        logger.error(f"hdc {' '.join(args)} 超时")
    except Exception as e:
        logger.error(f"hdc {' '.join(args)} 异常: {e}")
    return None


def _shell(serial: str, cmd: str, timeout: int = 15) -> str:
    """在鸿蒙设备上执行 shell 命令，返回输出（空字符串表示失败）"""
    out = _hdc(["shell", cmd], serial=serial, timeout=timeout)
    return out or ""


def print_json(msg):
    logger.info(json.dumps(msg, ensure_ascii=False))


# ─────────────────────────── 设备管理 ───────────────────────────

def get_harmony_devices() -> List[Dict]:
    """获取已连接的 HarmonyOS 设备列表"""
    if not HDC_AVAILABLE:
        return []
    try:
        output = _hdc(["list", "targets"])
        if not output:
            return []
        devices = []
        for line in output.strip().split("\n"):
            line = line.strip()
            # 过滤掉提示行，只保留设备序列号
            if not line or line.startswith("[") or "Empty" in line or "targets" in line.lower():
                continue
            serial = line.split()[0]
            # 获取设备基本信息
            model = _shell(serial, "getprop ro.product.model 2>/dev/null").strip() or "Unknown"
            brand = _shell(serial, "getprop ro.product.brand 2>/dev/null").strip() or "Unknown"
            os_version = _shell(serial, "getprop ro.build.version.release 2>/dev/null").strip() or "Unknown"
            sdk_version = _shell(serial, "getprop ro.build.version.sdk 2>/dev/null").strip() or "Unknown"
            devices.append({
                "serial": serial,
                "model": model,
                "brand": brand,
                "harmony_version": os_version,
                "sdk_version": sdk_version,
                "status": "online",
                "device_type": "harmony",
                "name": f"{brand} {model}",
            })
        return devices
    except Exception as e:
        logger.error(f"获取 HarmonyOS 设备列表失败: {e}")
        return []


# ─────────────────────────── 设备信息 ───────────────────────────

async def harmony_sys_info(serial: str) -> Dict:
    """获取 HarmonyOS 设备系统信息"""
    def real_func():
        model = _shell(serial, "getprop ro.product.model").strip() or "Unknown"
        brand = _shell(serial, "getprop ro.product.brand").strip() or "Unknown"
        os_version = _shell(serial, "getprop ro.build.version.release").strip() or "Unknown"

        # CPU 核心数
        cpu_cores_out = _shell(serial, "cat /proc/cpuinfo | grep processor | wc -l").strip()
        cpu_cores = int(cpu_cores_out) if cpu_cores_out.isdigit() else 0

        # 内存总量
        mem_info = _shell(serial, "cat /proc/meminfo | grep MemTotal").strip()
        mem_kb = int(re.search(r'(\d+)', mem_info).group(1)) if mem_info else 0
        mem_gb = round(mem_kb / 1024 / 1024, 1)

        # 存储
        disk_info = _shell(serial, "df /data | tail -1").strip()
        disk_parts = disk_info.split()
        disk_total_gb = round(int(disk_parts[1]) / 1024 / 1024, 1) if len(disk_parts) > 1 else 0

        res = {
            "platform": "HarmonyOS",
            "computer_name": f"{brand} {model}",
            "time": time.time(),
            "cpu_cores": cpu_cores,
            "ram": f"{mem_gb}G",
            "rom": f"{disk_total_gb}G",
            "harmony_version": os_version,
            "serial": serial,
        }
        print_json(res)
        return res

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=15)


# ─────────────────────────── 进程/应用列表 ───────────────────────────

async def harmony_packages(serial: str) -> List[Dict]:
    """获取 HarmonyOS 设备上已安装的应用包名列表"""
    def real_func():
        # 使用 bm dump 获取已安装包列表
        output = _shell(serial, "bm dump -a 2>/dev/null")
        packages = []
        if output:
            for line in output.strip().split("\n"):
                line = line.strip()
                # 过滤掉非包名行
                if not line or line.startswith("ID") or ":" in line[:3]:
                    continue
                # 尝试获取该包的 PID
                pid_output = _shell(serial, f"pidof {line} 2>/dev/null").strip()
                pid = int(pid_output.split()[0]) if pid_output and pid_output.split()[0].isdigit() else 0
                packages.append({
                    "package_name": line,
                    "pid": pid,
                    "name": line,
                    "running": pid > 0,
                    "bundle_id": line,
                })
        # 如果 bm dump 没有输出，尝试 pm list packages
        if not packages:
            output2 = _shell(serial, "pm list packages -3 2>/dev/null")
            for line in output2.strip().split("\n"):
                line = line.strip()
                if line.startswith("package:"):
                    pkg = line.replace("package:", "").strip()
                    if pkg:
                        pid_output = _shell(serial, f"pidof {pkg} 2>/dev/null").strip()
                        pid = int(pid_output.split()[0]) if pid_output and pid_output.split()[0].isdigit() else 0
                        packages.append({
                            "package_name": pkg,
                            "pid": pid,
                            "name": pkg,
                            "running": pid > 0,
                            "bundle_id": pkg,
                        })
        packages.sort(key=lambda x: (-int(x['running']), x['name']))
        return packages

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=20)


# ─────────────────────────── CPU 采集 ───────────────────────────

def _read_proc_stat(serial: str) -> Optional[Dict]:
    """读取 /proc/stat 获取系统 CPU 时间"""
    output = _shell(serial, "cat /proc/stat | head -1").strip()
    parts = output.split()
    if len(parts) < 5 or parts[0] != "cpu":
        return None
    try:
        user = int(parts[1])
        nice = int(parts[2])
        system = int(parts[3])
        idle = int(parts[4])
        iowait = int(parts[5]) if len(parts) > 5 else 0
        irq = int(parts[6]) if len(parts) > 6 else 0
        softirq = int(parts[7]) if len(parts) > 7 else 0
        total = user + nice + system + idle + iowait + irq + softirq
        return {"user": user, "nice": nice, "system": system, "idle": idle,
                "iowait": iowait, "irq": irq, "softirq": softirq, "total": total}
    except (ValueError, IndexError):
        return None


def _read_pid_stat(serial: str, pid: int) -> Optional[Dict]:
    """读取 /proc/<pid>/stat 获取进程 CPU 时间"""
    output = _shell(serial, f"cat /proc/{pid}/stat 2>/dev/null").strip()
    if not output:
        return None
    parts = output.split()
    if len(parts) < 15:
        return None
    try:
        utime = int(parts[13])
        stime = int(parts[14])
        return {"utime": utime, "stime": stime, "total": utime + stime}
    except (ValueError, IndexError):
        return None


async def harmony_cpu(serial: str, pid: int = 0, package_name: str = "", **kwargs) -> Dict:
    """
    采集 HarmonyOS 进程 CPU 使用率
    使用 /proc/stat 和 /proc/<pid>/stat 两次采样计算
    """
    def real_func():
        current_time = int(time.time())

        # 获取目标 PID
        target_pid = pid
        if not target_pid and package_name:
            pid_output = _shell(serial, f"pidof {package_name} 2>/dev/null").strip()
            if pid_output:
                parts = pid_output.split()
                target_pid = int(parts[0]) if parts[0].isdigit() else 0

        # CPU 核心数
        cpu_cores_out = _shell(serial, "cat /proc/cpuinfo | grep processor | wc -l").strip()
        cpu_cores = int(cpu_cores_out) if cpu_cores_out.isdigit() else 1

        if not target_pid:
            return {"cpu_usage": 0, "cpu_usage_all": 0, "cpu_core_num": cpu_cores, "time": current_time}

        # 第一次采样
        sys_stat1 = _read_proc_stat(serial)
        pid_stat1 = _read_pid_stat(serial, target_pid)

        time.sleep(1)

        # 第二次采样
        sys_stat2 = _read_proc_stat(serial)
        pid_stat2 = _read_pid_stat(serial, target_pid)

        cpu_usage_all = 0.0
        cpu_usage = 0.0

        if sys_stat1 and sys_stat2:
            sys_delta = sys_stat2["total"] - sys_stat1["total"]
            sys_idle_delta = sys_stat2["idle"] - sys_stat1["idle"]
            if sys_delta > 0:
                cpu_usage_all = round((1 - sys_idle_delta / sys_delta) * 100, 2)

        if pid_stat1 and pid_stat2 and sys_stat1 and sys_stat2:
            pid_delta = pid_stat2["total"] - pid_stat1["total"]
            sys_delta = sys_stat2["total"] - sys_stat1["total"]
            if sys_delta > 0:
                cpu_usage = round(pid_delta / sys_delta * 100 * cpu_cores, 2)

        res = {
            "cpu_usage": cpu_usage,
            "cpu_usage_all": cpu_usage_all,
            "cpu_core_num": cpu_cores,
            "time": current_time
        }
        print_json(res)
        return res

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=20)


# ─────────────────────────── 内存采集 ───────────────────────────

async def harmony_memory(serial: str, pid: int = 0, package_name: str = "", **kwargs) -> Dict:
    """
    采集 HarmonyOS 进程内存使用
    优先使用 hidumper --mem <bundle> 获取 PSS，失败则用 /proc/<pid>/status
    """
    def real_func():
        target = package_name if package_name else str(pid)
        if not target or target == "0":
            return {"process_memory_usage": 0, "time": int(time.time())}

        memory_mb = 0.0

        # 方法1: hidumper --mem（鸿蒙专用，获取 PSS）
        if package_name:
            try:
                output = _shell(serial, f"hidumper --mem {package_name} 2>/dev/null", timeout=10)
                if output:
                    # 查找 Total PSS 行
                    match = re.search(r'Total\s+PSS[:\s]+(\d+)', output, re.IGNORECASE)
                    if match:
                        memory_mb = int(match.group(1)) / 1024.0
                    else:
                        # 查找 Pss Total 行
                        match = re.search(r'Pss\s+Total[:\s]+(\d+)', output, re.IGNORECASE)
                        if match:
                            memory_mb = int(match.group(1)) / 1024.0
            except Exception as e:
                logger.warning(f"hidumper --mem 失败: {e}")

        # 方法2: /proc/<pid>/status（备用）
        target_pid = pid
        if memory_mb == 0:
            if not target_pid and package_name:
                pid_output = _shell(serial, f"pidof {package_name} 2>/dev/null").strip()
                if pid_output:
                    parts = pid_output.split()
                    target_pid = int(parts[0]) if parts[0].isdigit() else 0
            if target_pid:
                try:
                    status_output = _shell(serial, f"cat /proc/{target_pid}/status 2>/dev/null")
                    match = re.search(r'VmRSS:\s+(\d+)\s+kB', status_output)
                    if match:
                        memory_mb = int(match.group(1)) / 1024.0
                except Exception as e:
                    logger.warning(f"/proc/pid/status 读取失败: {e}")

        res = {"process_memory_usage": round(memory_mb, 2), "time": int(time.time())}
        print_json(res)
        return res

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=20)


# ─────────────────────────── FPS 采集 ───────────────────────────

async def harmony_fps(serial: str, pid: int = 0, package_name: str = "", **kwargs) -> Dict:
    """
    采集 HarmonyOS 应用 FPS
    通过 hidumper -s RenderService 获取帧率数据
    """
    def real_func():
        current_time = int(time.time())
        fps = 0

        try:
            output = _shell(serial, "hidumper -s RenderService -a screen 2>/dev/null", timeout=10)
            if output:
                # 查找 fps 字段
                match = re.search(r'fps[:\s=]+(\d+\.?\d*)', output, re.IGNORECASE)
                if match:
                    fps = int(float(match.group(1)))
                else:
                    # 查找 refreshRate 或 refresh rate
                    match = re.search(r'refresh\s*[Rr]ate[:\s=]+(\d+)', output)
                    if match:
                        fps = int(match.group(1))
        except Exception as e:
            logger.warning(f"hidumper RenderService 失败: {e}")

        return {
            "type": "fps",
            "fps": fps,
            "frames": [current_time + i * 0.001 for i in range(min(fps, 120))],
            "time": current_time
        }

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=15)


# ─────────────────────────── GPU 采集 ───────────────────────────

async def harmony_gpu(serial: str, **kwargs) -> Dict:
    """
    采集 HarmonyOS GPU 使用率
    尝试读取 /sys 节点（与 Android 类似，鸿蒙底层共用 Linux 内核）
    """
    def real_func():
        start_time = int(time.time())
        gpu_usage = None

        # 尝试 Qualcomm GPU 节点
        gpu_paths = [
            "/sys/class/kgsl/kgsl-3d0/gpubusy",
            "/sys/class/kgsl/kgsl-3d0/gpu_busy_percentage",
        ]
        for path in gpu_paths:
            output = _shell(serial, f"cat {path} 2>/dev/null").strip()
            if output and "No such file" not in output and "Permission denied" not in output:
                try:
                    parts = output.split()
                    if len(parts) == 2:
                        busy = int(parts[0])
                        total = int(parts[1])
                        if total > 0:
                            gpu_usage = round((busy / total) * 100, 2)
                            break
                    elif len(parts) == 1:
                        gpu_usage = float(parts[0].replace('%', ''))
                        break
                except (ValueError, ZeroDivisionError):
                    continue

        # 尝试 Mali GPU
        if gpu_usage is None:
            mali_output = _shell(serial, "cat /sys/devices/platform/*.gpu/utilisation 2>/dev/null").strip()
            if mali_output and "No such file" not in mali_output:
                try:
                    gpu_usage = float(mali_output.replace('%', '').strip())
                except ValueError:
                    pass

        return {"gpu": gpu_usage, "time": start_time}

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=15)


# ─────────────────────────── 进程信息 ───────────────────────────

async def harmony_process_info(serial: str, pid: int = 0, package_name: str = "", **kwargs) -> Dict:
    """采集 HarmonyOS 进程的线程数、FD 数等信息"""
    def real_func():
        start_time = int(time.time())
        target_pid = pid
        if not target_pid and package_name:
            pid_output = _shell(serial, f"pidof {package_name} 2>/dev/null").strip()
            if pid_output:
                parts = pid_output.split()
                target_pid = int(parts[0]) if parts[0].isdigit() else 0

        num_threads = 0
        num_fds = 0
        if target_pid:
            thread_output = _shell(serial, f"ls /proc/{target_pid}/task 2>/dev/null | wc -l").strip()
            num_threads = int(thread_output) if thread_output.isdigit() else 0
            fd_output = _shell(serial, f"ls /proc/{target_pid}/fd 2>/dev/null | wc -l").strip()
            num_fds = int(fd_output) if fd_output.isdigit() else 0

        return {"time": start_time, "num_threads": num_threads, "num_handles": num_fds}

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=15)


# ─────────────────────────── 磁盘 IO ───────────────────────────

async def harmony_disk_io(serial: str, pid: int = 0, package_name: str = "", **kwargs) -> Dict:
    """采集 HarmonyOS 进程磁盘 I/O（通过 /proc/<pid>/io 两次采样）"""
    MB_CONVERSION = 1024 * 1024

    def real_func():
        target_pid = pid
        if not target_pid and package_name:
            pid_output = _shell(serial, f"pidof {package_name} 2>/dev/null").strip()
            if pid_output:
                parts = pid_output.split()
                target_pid = int(parts[0]) if parts[0].isdigit() else 0

        if not target_pid:
            return {"disk_read_rate": 0, "disk_write_rate": 0,
                    "disk_read": 0, "disk_write": 0, "time": int(time.time())}

        io_output1 = _shell(serial, f"cat /proc/{target_pid}/io 2>/dev/null").strip()
        time.sleep(1)
        io_output2 = _shell(serial, f"cat /proc/{target_pid}/io 2>/dev/null").strip()

        def parse_io(output):
            result = {}
            for line in output.split('\n'):
                parts = line.strip().split(':')
                if len(parts) == 2:
                    key = parts[0].strip()
                    val = parts[1].strip()
                    if val.isdigit():
                        result[key] = int(val)
            return result

        io1 = parse_io(io_output1)
        io2 = parse_io(io_output2)

        read_bytes1 = io1.get('read_bytes', 0)
        write_bytes1 = io1.get('write_bytes', 0)
        read_bytes2 = io2.get('read_bytes', 0)
        write_bytes2 = io2.get('write_bytes', 0)

        disk_read_rate = max(0, (read_bytes2 - read_bytes1) / MB_CONVERSION)
        disk_write_rate = max(0, (write_bytes2 - write_bytes1) / MB_CONVERSION)

        if disk_read_rate < 0.001:
            disk_read_rate = 0
        if disk_write_rate < 0.001:
            disk_write_rate = 0

        res = {
            "disk_read_rate": round(disk_read_rate, 4),
            "disk_write_rate": round(disk_write_rate, 4),
            "disk_read": read_bytes2,
            "disk_write": write_bytes2,
            "time": int(time.time())
        }
        return res

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=20)


# ─────────────────────────── 网络 IO ───────────────────────────

_net_io_cache: Dict[str, Dict] = {}
_net_io_lock = threading.Lock()


async def harmony_network_io(serial: str, pid: int = 0, package_name: str = "", **kwargs) -> Dict:
    """
    采集 HarmonyOS 网络 I/O
    通过 /proc/net/dev 两次采样计算速率（设备级）
    若能获取 UID，则优先使用 /proc/net/xt_qtaguid/stats 进程级统计
    """
    MB_CONVERSION = 1024 * 1024

    def real_func():
        current_time = int(time.time())

        # 尝试获取进程 UID
        uid = None
        target_pid = pid
        if not target_pid and package_name:
            pid_output = _shell(serial, f"pidof {package_name} 2>/dev/null").strip()
            if pid_output:
                parts = pid_output.split()
                target_pid = int(parts[0]) if parts[0].isdigit() else 0

        if target_pid:
            uid_output = _shell(serial, f"cat /proc/{target_pid}/status 2>/dev/null | grep Uid").strip()
            match = re.search(r'Uid:\s+(\d+)', uid_output)
            if match:
                uid = int(match.group(1))

        def get_net_by_uid(uid_val):
            output = _shell(serial, "cat /proc/net/xt_qtaguid/stats 2>/dev/null").strip()
            if not output:
                return None, None
            rx_bytes = tx_bytes = 0
            for line in output.split('\n')[1:]:
                parts = line.strip().split()
                if len(parts) >= 8:
                    try:
                        if int(parts[3]) == uid_val:
                            rx_bytes += int(parts[5])
                            tx_bytes += int(parts[7])
                    except (ValueError, IndexError):
                        continue
            return rx_bytes, tx_bytes

        def get_net_device():
            rx_bytes = tx_bytes = 0
            output = _shell(serial, "cat /proc/net/dev").strip()
            for line in output.split('\n')[2:]:
                parts = line.strip().split()
                if len(parts) >= 10 and ':' in parts[0]:
                    iface = parts[0].replace(':', '')
                    if iface not in ('lo',):
                        try:
                            rx_bytes += int(parts[1])
                            tx_bytes += int(parts[9])
                        except (ValueError, IndexError):
                            continue
            return rx_bytes, tx_bytes

        # 使用缓存计算速率（避免重复 sleep）
        if uid is not None:
            rx_now, tx_now = get_net_by_uid(uid)
            if rx_now is None:
                rx_now, tx_now = get_net_device()
        else:
            rx_now, tx_now = get_net_device()

        rx_now = rx_now or 0
        tx_now = tx_now or 0

        with _net_io_lock:
            cache = _net_io_cache.get(serial)
            if cache:
                dt = current_time - cache["time"]
                if dt > 0:
                    recv_rate = max(0, (rx_now - cache["net_in"]) / MB_CONVERSION / dt)
                    sent_rate = max(0, (tx_now - cache["net_out"]) / MB_CONVERSION / dt)
                else:
                    recv_rate = sent_rate = 0
            else:
                recv_rate = sent_rate = 0

            _net_io_cache[serial] = {
                "time": current_time,
                "net_in": rx_now,
                "net_out": tx_now,
            }

        return {
            "net_sent_rate": round(sent_rate, 4),
            "net_recv_rate": round(recv_rate, 4),
            "net_sent": tx_now,
            "net_recv": rx_now,
            "time": current_time
        }

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=20)


# ─────────────────────────── 电池信息 ───────────────────────────

async def harmony_battery(serial: str, **kwargs) -> Dict:
    """
    采集 HarmonyOS 设备电池信息
    通过 hidumper -s BatteryService 获取
    """
    def real_func():
        battery_info = {"time": int(time.time())}

        try:
            output = _shell(serial, "hidumper -s BatteryService -a -i 2>/dev/null", timeout=10)
            if not output:
                output = _shell(serial, "hidumper -s BatteryService 2>/dev/null", timeout=10)

            if output:
                # 电量
                match = re.search(r'capacity[:\s=]+(\d+)', output, re.IGNORECASE)
                if match:
                    battery_info['battery_level'] = int(match.group(1))
                # 温度（单位 0.1°C）
                match = re.search(r'temperature[:\s=]+(-?\d+)', output, re.IGNORECASE)
                if match:
                    battery_info['battery_temperature'] = round(int(match.group(1)) / 10.0, 1)
                # 电流（μA → mA）
                match = re.search(r'current[:\s=]+(-?\d+)', output, re.IGNORECASE)
                if match:
                    battery_info['battery_current'] = round(int(match.group(1)) / 1000.0, 2)
        except Exception as e:
            logger.warning(f"hidumper BatteryService 失败: {e}")

        battery_info.setdefault('battery_level', 0)
        battery_info.setdefault('battery_temperature', 0)
        battery_info.setdefault('battery_current', 0)
        return battery_info

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=15)


# ─────────────────────────── 截图 ───────────────────────────

async def harmony_screenshot(serial: str, save_dir: str = None, **kwargs):
    """HarmonyOS 设备截图（hdc shell snapshot_display）"""
    def real_func():
        if not HDC_PATH:
            return None

        remote_path = f"/data/local/tmp/hm_shot_{int(time.time())}.png"
        # 在设备上截图
        _shell(serial, f"snapshot_display -f {remote_path} 2>/dev/null")
        time.sleep(0.5)

        if save_dir:
            screenshot_dir = Path(save_dir) / "screenshot"
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            local_path = str(screenshot_dir / f"{int(time.time())}.png")
        else:
            local_path = f"/tmp/hm_screenshot_{int(time.time())}.png"

        # 拉取截图到本地
        try:
            result = subprocess.run(
                [HDC_PATH, "-t", serial, "file", "recv", remote_path, local_path],
                capture_output=True, timeout=15
            )
            # 清理设备上的临时文件
            _shell(serial, f"rm -f {remote_path} 2>/dev/null")

            if os.path.isfile(local_path) and os.path.getsize(local_path) > 0:
                if not save_dir:
                    with open(local_path, "rb") as f:
                        data = f.read()
                    os.remove(local_path)
                    return data
                return True
        except Exception as e:
            logger.error(f"HarmonyOS 截图失败: {e}")
        return None

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=20)


# ─────────────────────────── 性能采集入口 ───────────────────────────

async def harmony_perf(serial: str, package_name: str, pid: int, save_dir: str, include_child: bool = False):
    """
    HarmonyOS 性能采集入口，与 Android/iOS 端保持一致的 Monitor 结构。

    支持的指标：
    - CPU 使用率（/proc/stat 两次采样）
    - 内存使用（hidumper --mem 或 /proc/<pid>/status）
    - FPS（hidumper -s RenderService）
    - GPU（/sys 节点）
    - 网络 IO（/proc/net/dev 缓存差值）
    - 磁盘 IO（/proc/<pid>/io 两次采样）
    - 电池（hidumper -s BatteryService）
    - 截图（snapshot_display + hdc file recv）
    - 进程信息（线程数、FD 数）
    """
    # 如果没有 pid，尝试通过包名获取
    if not pid and package_name:
        try:
            pid_output = _shell(serial, f"pidof {package_name} 2>/dev/null").strip()
            if pid_output:
                parts = pid_output.split()
                pid = int(parts[0]) if parts[0].isdigit() else 0
        except Exception:
            pid = 0

    logger.info(f"HarmonyOS 性能采集: serial={serial}, package={package_name}, pid={pid}")

    monitors = {
        "cpu": Monitor(harmony_cpu,
                       serial=serial, pid=pid, package_name=package_name,
                       monitor_name="cpu",
                       key_value=["time", "cpu_usage(%)", "cpu_usage_all(%)", "cpu_core_num(个)"],
                       save_dir=save_dir),
        "memory": Monitor(harmony_memory,
                          serial=serial, pid=pid, package_name=package_name,
                          monitor_name="memory",
                          key_value=["time", "process_memory_usage(M)"],
                          save_dir=save_dir),
        "process_info": Monitor(harmony_process_info,
                                serial=serial, pid=pid, package_name=package_name,
                                monitor_name="process_info",
                                key_value=["time", "num_threads(个)", "num_handles(个)"],
                                save_dir=save_dir),
        "fps": Monitor(harmony_fps,
                       serial=serial, pid=pid, package_name=package_name,
                       monitor_name="fps",
                       key_value=["time", "fps(帧)", "frames"],
                       save_dir=save_dir),
        "gpu": Monitor(harmony_gpu,
                       serial=serial,
                       monitor_name="gpu",
                       key_value=["time", "gpu(%)"],
                       save_dir=save_dir),
        "disk_io": Monitor(harmony_disk_io,
                           serial=serial, pid=pid, package_name=package_name,
                           monitor_name="disk_io",
                           key_value=["time", "disk_read_rate(MB/s)", "disk_write_rate(MB/s)",
                                      "disk_read(字节)", "disk_write(字节)"],
                           save_dir=save_dir),
        "network_io": Monitor(harmony_network_io,
                              serial=serial, pid=pid, package_name=package_name,
                              monitor_name="network_io",
                              key_value=["time", "net_sent_rate(MB/s)", "net_recv_rate(MB/s)",
                                         "net_sent(字节)", "net_recv(字节)"],
                              save_dir=save_dir),
        "battery": Monitor(harmony_battery,
                           serial=serial,
                           monitor_name="battery",
                           key_value=["time", "battery_level(%)", "battery_temperature(℃)",
                                      "battery_current(mA)"],
                           save_dir=save_dir),
        "screenshot": Monitor(harmony_screenshot,
                              serial=serial,
                              save_dir=save_dir, is_out=False)
    }
    run_monitors = [monitor.run() for name, monitor in monitors.items()]
    await asyncio.gather(*run_monitors)

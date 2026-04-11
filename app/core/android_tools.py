# coding:utf-8
"""
Android 性能测试模块
通过 adbutils 连接 Android 设备，采集 CPU、内存、FPS、GPU、网络、磁盘等性能指标。
指标维度与 PC 端保持一致。
"""
import asyncio
import json
import re
import time
import traceback
from typing import Optional, Dict, List

from app.log import log as logger
from app.core.monitor import Monitor

try:
    import adbutils
    ADB_AVAILABLE = True
except ImportError:
    ADB_AVAILABLE = False
    logger.warning("adbutils 未安装，Android 性能测试不可用。请执行: pip install adbutils")


def print_json(msg):
    logger.info(json.dumps(msg, ensure_ascii=False))


# ─────────────────────────── 设备管理 ───────────────────────────

def get_adb_devices() -> List[Dict]:
    """获取已连接的 Android 设备列表"""
    if not ADB_AVAILABLE:
        return []
    try:
        client = adbutils.AdbClient()
        devices = []
        for d in client.device_list():
            serial = d.serial
            try:
                model = d.prop.model or "Unknown"
                brand = d.prop.get("ro.product.brand", "Unknown")
                android_version = d.prop.get("ro.build.version.release", "Unknown")
                sdk_version = d.prop.get("ro.build.version.sdk", "Unknown")
                devices.append({
                    "serial": serial,
                    "model": model,
                    "brand": brand,
                    "android_version": android_version,
                    "sdk_version": sdk_version,
                    "status": "online",
                    "device_type": "android",
                    # 统一字段
                    "name": f"{brand} {model}",
                })
            except Exception as e:
                logger.error(f"获取设备 {serial} 信息失败: {e}")
                devices.append({
                    "serial": serial,
                    "model": "Unknown",
                    "brand": "Unknown",
                    "android_version": "Unknown",
                    "sdk_version": "Unknown",
                    "status": "error",
                    "device_type": "android",
                    "name": serial,
                })
        return devices
    except Exception as e:
        logger.error(f"获取 Android 设备列表失败: {e}")
        return []


def _get_device(serial: str):
    """根据序列号获取 adb 设备对象"""
    client = adbutils.AdbClient()
    return client.device(serial)


# ─────────────────────────── 设备信息 ───────────────────────────

async def android_sys_info(serial: str) -> Dict:
    """获取 Android 设备系统信息"""
    def real_func():
        d = _get_device(serial)
        cpu_info = d.shell("cat /proc/cpuinfo | grep processor | wc -l").strip()
        mem_info = d.shell("cat /proc/meminfo | grep MemTotal").strip()
        # 解析内存 (kB -> GB)
        mem_kb = int(re.search(r'(\d+)', mem_info).group(1)) if mem_info else 0
        mem_gb = round(mem_kb / 1024 / 1024, 1)
        # 存储
        disk_info = d.shell("df /data | tail -1").strip()
        disk_parts = disk_info.split()
        disk_total_gb = round(int(disk_parts[1]) / 1024 / 1024, 1) if len(disk_parts) > 1 else 0

        model = d.prop.model or "Unknown"
        brand = d.prop.get("ro.product.brand", "Unknown")
        android_version = d.prop.get("ro.build.version.release", "Unknown")

        res = {
            "platform": "Android",
            "computer_name": f"{brand} {model}",
            "time": time.time(),
            "cpu_cores": int(cpu_info) if cpu_info.isdigit() else 0,
            "ram": f"{mem_gb}G",
            "rom": f"{disk_total_gb}G",
            "android_version": android_version,
            "serial": serial
        }
        print_json(res)
        return res

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=15)


# ─────────────────────────── 进程列表 ───────────────────────────

async def android_pids(serial: str) -> List[Dict]:
    """获取 Android 设备上的进程列表（应用级别）"""
    def real_func():
        d = _get_device(serial)
        # 获取正在运行的应用包名列表
        output = d.shell("ps -A -o PID,NAME,RSS,USER 2>/dev/null || ps -A")
        process_list = []
        for line in output.strip().split('\n')[1:]:  # 跳过表头
            parts = line.split()
            if len(parts) >= 2:
                try:
                    pid = int(parts[0])
                    name = parts[1] if len(parts) >= 2 else "unknown"
                    process_list.append({
                        "pid": pid,
                        "name": name,
                        "cmd": [name],
                        "username": parts[-1] if len(parts) >= 4 else ""
                    })
                except (ValueError, IndexError):
                    continue
        process_list.sort(key=lambda x: x['name'])
        return process_list

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=15)


async def android_packages(serial: str) -> List[Dict]:
    """获取 Android 设备上已安装的应用包名列表（更实用的选择方式）"""
    def real_func():
        d = _get_device(serial)
        # 获取第三方应用
        output = d.shell("pm list packages -3")
        packages = []
        for line in output.strip().split('\n'):
            line = line.strip()
            if line.startswith("package:"):
                pkg = line.replace("package:", "").strip()
                if pkg:
                    # 获取该包的 PID
                    pid_output = d.shell(f"pidof {pkg}").strip()
                    pid = int(pid_output.split()[0]) if pid_output and pid_output.split()[0].isdigit() else 0
                    packages.append({
                        "package_name": pkg,
                        "pid": pid,
                        "name": pkg,
                        "running": pid > 0,
                        # 兼容 iOS 字段
                        "bundle_id": pkg,
                    })
        packages.sort(key=lambda x: (-int(x['running']), x['name']))
        return packages

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=15)


# ─────────────────────────── CPU 采集 ───────────────────────────

def _read_proc_stat_cpu(d) -> Optional[Dict]:
    """
    读取 /proc/stat 获取系统 CPU 使用率（更准确）
    返回 {'user': x, 'nice': x, 'system': x, 'idle': x, 'total': x}
    """
    output = d.shell("cat /proc/stat | head -1").strip()
    # cpu  user nice system idle iowait irq softirq steal guest guest_nice
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


def _read_proc_pid_stat(d, pid: int) -> Optional[Dict]:
    """
    读取 /proc/<pid>/stat 获取进程 CPU 时间
    返回 {'utime': x, 'stime': x, 'total': x}
    """
    output = d.shell(f"cat /proc/{pid}/stat 2>/dev/null").strip()
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


async def android_cpu(serial: str, pid: int = 0, package_name: str = "", **kwargs) -> Dict:
    """
    采集 Android 进程 CPU 使用率
    使用 /proc/stat 和 /proc/<pid>/stat 计算精确的 CPU 占用率
    """
    def real_func():
        d = _get_device(serial)
        current_time = int(time.time())

        # 获取目标 PID
        target_pid = pid
        if not target_pid and package_name:
            pid_output = d.shell(f"pidof {package_name}").strip()
            if pid_output:
                parts = pid_output.split()
                target_pid = int(parts[0]) if parts[0].isdigit() else 0

        # 获取 CPU 核心数
        cpu_cores_output = d.shell("cat /proc/cpuinfo | grep processor | wc -l").strip()
        cpu_cores = int(cpu_cores_output) if cpu_cores_output.isdigit() else 1

        if not target_pid:
            return {"cpu_usage": 0, "cpu_usage_all": 0, "cpu_core_num": cpu_cores, "time": current_time}

        # 第一次采样
        sys_stat1 = _read_proc_stat_cpu(d)
        pid_stat1 = _read_proc_pid_stat(d, target_pid)

        time.sleep(1)

        # 第二次采样
        sys_stat2 = _read_proc_stat_cpu(d)
        pid_stat2 = _read_proc_pid_stat(d, target_pid)

        cpu_usage_all = 0.0
        cpu_usage = 0.0

        if sys_stat1 and sys_stat2:
            sys_delta = sys_stat2["total"] - sys_stat1["total"]
            sys_idle_delta = sys_stat2["idle"] - sys_stat1["idle"]
            if sys_delta > 0:
                # 系统整体 CPU 使用率
                cpu_usage_all = round((1 - sys_idle_delta / sys_delta) * 100, 2)

        if pid_stat1 and pid_stat2 and sys_stat1 and sys_stat2:
            pid_delta = pid_stat2["total"] - pid_stat1["total"]
            sys_delta = sys_stat2["total"] - sys_stat1["total"]
            if sys_delta > 0:
                # 进程 CPU 使用率（相对于单核）
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

async def android_memory(serial: str, pid: int = 0, package_name: str = "", **kwargs) -> Dict:
    """
    采集 Android 进程内存使用
    优先使用 dumpsys meminfo 获取 PSS 内存，失败则用 /proc/<pid>/status
    """
    def real_func():
        d = _get_device(serial)
        target = package_name if package_name else str(pid)
        if not target or target == "0":
            return {"process_memory_usage": 0, "time": int(time.time())}

        memory_mb = 0.0

        # 方法1: dumpsys meminfo（最准确，获取 PSS）
        try:
            output = d.shell(f"dumpsys meminfo {target} 2>/dev/null")
            if output.strip():
                # 尝试多种格式
                # 格式1: "TOTAL PSS:    xxxxx"
                match = re.search(r'TOTAL\s+PSS:\s+(\d+)', output)
                if match:
                    memory_mb = int(match.group(1)) / 1024.0
                else:
                    # 格式2: "TOTAL    xxxxx    xxxxx    xxxxx"
                    match = re.search(r'TOTAL\s+(\d+)', output)
                    if match:
                        memory_mb = int(match.group(1)) / 1024.0
                    else:
                        # 格式3: "    TOTAL:   xxxxx kB"
                        match = re.search(r'TOTAL:\s+(\d+)\s+kB', output, re.IGNORECASE)
                        if match:
                            memory_mb = int(match.group(1)) / 1024.0
        except Exception as e:
            logger.warning(f"dumpsys meminfo 失败: {e}")

        # 方法2: /proc/<pid>/status（备用）
        if memory_mb == 0 and pid:
            try:
                status_output = d.shell(f"cat /proc/{pid}/status 2>/dev/null")
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

async def android_fps(serial: str, pid: int = 0, package_name: str = "", **kwargs) -> Optional[Dict]:
    """
    采集 Android 应用 FPS
    使用 SurfaceFlinger 的 dumpsys 获取帧数据
    """
    def real_func():
        d = _get_device(serial)
        current_time = int(time.time())

        # 获取当前前台 Activity
        if not package_name:
            activity_output = d.shell("dumpsys activity activities | grep mResumedActivity")
            if not activity_output.strip():
                activity_output = d.shell("dumpsys activity activities | grep mFocusedActivity")
            # 解析包名
            match = re.search(r'(\S+)/(\S+)', activity_output)
            current_package = match.group(1) if match else ""
        else:
            current_package = package_name

        if not current_package:
            return {"type": "fps", "fps": 0, "frames": [], "time": current_time}

        # 方法1: 使用 gfxinfo framestats（更准确）
        try:
            # 重置统计
            d.shell(f"dumpsys gfxinfo {current_package} reset 2>/dev/null")
            time.sleep(1)
            output = d.shell(f"dumpsys gfxinfo {current_package} framestats 2>/dev/null")
            if output.strip():
                result = _parse_gfxinfo_framestats(output, current_time)
                if result["fps"] > 0:
                    return result
        except Exception:
            pass

        # 方法2: SurfaceFlinger latency
        try:
            d.shell("dumpsys SurfaceFlinger --latency-clear 2>/dev/null")
            time.sleep(1)
            output = d.shell(f"dumpsys SurfaceFlinger --latency '{current_package}' 2>/dev/null")
            if output.strip() and "\n" in output:
                lines = output.strip().split('\n')
                frame_timestamps = []
                for line in lines[1:]:
                    parts = line.strip().split('\t')
                    if len(parts) >= 3:
                        try:
                            ts = int(parts[2])
                            if ts > 0 and ts != 0x7FFFFFFFFFFFFFFF:
                                frame_timestamps.append(ts)
                        except (ValueError, IndexError):
                            continue
                fps = len(frame_timestamps)
                if fps > 0:
                    return {
                        "type": "fps",
                        "fps": min(fps, 120),
                        "frames": [current_time + i * 0.001 for i in range(min(fps, 120))],
                        "time": current_time
                    }
        except Exception:
            pass

        return {"type": "fps", "fps": 0, "frames": [], "time": current_time}

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=20)


def _parse_gfxinfo_framestats(output: str, current_time: int) -> Dict:
    """解析 gfxinfo framestats 输出获取 FPS"""
    # 查找 PROFILEDATA 段
    frames = []
    in_profile = False
    for line in output.split('\n'):
        line = line.strip()
        if line.startswith("---PROFILEDATA---"):
            in_profile = not in_profile
            continue
        if in_profile and line and not line.startswith("Flags"):
            parts = line.split(',')
            if len(parts) >= 13:
                try:
                    flags = int(parts[0])
                    if flags == 0:  # 正常帧
                        frame_completed = int(parts[12])
                        if frame_completed > 0:
                            frames.append(frame_completed)
                except (ValueError, IndexError):
                    continue

    fps = len(frames)
    # 如果没有 PROFILEDATA，尝试 Total frames rendered
    if fps == 0:
        match = re.search(r'Total frames rendered:\s+(\d+)', output)
        if match:
            fps = min(int(match.group(1)), 120)

    return {
        "type": "fps",
        "fps": fps,
        "frames": [current_time + i * 0.001 for i in range(min(fps, 120))],
        "time": current_time
    }


def _parse_gfxinfo_fps(output: str) -> Dict:
    """解析 gfxinfo 输出获取 FPS（兼容旧版）"""
    current_time = int(time.time())
    if not output:
        return {"type": "fps", "fps": 0, "frames": [], "time": current_time}

    match = re.search(r'Total frames rendered:\s+(\d+)', output)
    total_frames = int(match.group(1)) if match else 0
    fps = min(total_frames, 60)

    return {
        "type": "fps",
        "fps": fps,
        "frames": [current_time + i * 0.001 for i in range(fps)],
        "time": current_time
    }


# ─────────────────────────── GPU 采集 ───────────────────────────

async def android_gpu(serial: str, pid: int = 0, package_name: str = "", **kwargs) -> Dict:
    """
    采集 Android GPU 使用率
    通过读取 /sys 节点或 dumpsys gpu 获取
    """
    def real_func():
        d = _get_device(serial)
        start_time = int(time.time())
        gpu_usage = None

        # 方法1: 尝试读取 Qualcomm GPU 节点
        gpu_paths = [
            "/sys/class/kgsl/kgsl-3d0/gpubusy",
            "/sys/class/kgsl/kgsl-3d0/gpu_busy_percentage",
            "/sys/devices/platform/kgsl-3d0.0/kgsl/kgsl-3d0/gpubusy",
        ]
        for path in gpu_paths:
            output = d.shell(f"cat {path} 2>/dev/null").strip()
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

        # 方法2: 尝试 Mali GPU
        if gpu_usage is None:
            mali_output = d.shell("cat /sys/devices/platform/*.gpu/utilisation 2>/dev/null").strip()
            if mali_output and "No such file" not in mali_output:
                try:
                    gpu_usage = float(mali_output.replace('%', '').strip())
                except ValueError:
                    pass

        # 方法3: dumpsys gpu
        if gpu_usage is None:
            gpu_dump = d.shell("dumpsys gpu 2>/dev/null | grep -i utilization")
            if gpu_dump.strip():
                match = re.search(r'(\d+\.?\d*)\s*%?', gpu_dump)
                if match:
                    gpu_usage = float(match.group(1))

        res = {"gpu": gpu_usage, "time": start_time}
        return res

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=15)


# ─────────────────────────── 进程信息 ───────────────────────────

async def android_process_info(serial: str, pid: int = 0, package_name: str = "", **kwargs) -> Dict:
    """采集 Android 进程的线程数等信息"""
    def real_func():
        d = _get_device(serial)
        start_time = int(time.time())
        target_pid = pid
        if not target_pid and package_name:
            pid_output = d.shell(f"pidof {package_name}").strip()
            if pid_output:
                parts = pid_output.split()
                target_pid = int(parts[0]) if parts[0].isdigit() else 0

        num_threads = 0
        if target_pid:
            # 获取线程数
            thread_output = d.shell(f"ls /proc/{target_pid}/task 2>/dev/null | wc -l").strip()
            num_threads = int(thread_output) if thread_output.isdigit() else 0

        # Android 没有 Windows 的 handle 概念，用 fd 数量代替
        num_fds = 0
        if target_pid:
            fd_output = d.shell(f"ls /proc/{target_pid}/fd 2>/dev/null | wc -l").strip()
            num_fds = int(fd_output) if fd_output.isdigit() else 0

        res = {"time": start_time, "num_threads": num_threads, "num_handles": num_fds}
        return res

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=15)


# ─────────────────────────── 磁盘 IO ───────────────────────────

async def android_disk_io(serial: str, pid: int = 0, package_name: str = "", **kwargs) -> Dict:
    """采集 Android 进程磁盘 I/O"""
    MB_CONVERSION = 1024 * 1024

    def real_func():
        d = _get_device(serial)
        target_pid = pid
        if not target_pid and package_name:
            pid_output = d.shell(f"pidof {package_name}").strip()
            if pid_output:
                parts = pid_output.split()
                target_pid = int(parts[0]) if parts[0].isdigit() else 0

        if not target_pid:
            return {"disk_read_rate": 0, "disk_write_rate": 0,
                    "disk_read": 0, "disk_write": 0, "time": int(time.time())}

        # 读取 /proc/pid/io 获取 IO 数据
        io_output1 = d.shell(f"cat /proc/{target_pid}/io 2>/dev/null").strip()
        time.sleep(1)
        io_output2 = d.shell(f"cat /proc/{target_pid}/io 2>/dev/null").strip()

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

async def android_network_io(serial: str, pid: int = 0, package_name: str = "", **kwargs) -> Dict:
    """
    采集 Android 设备网络 I/O
    优先使用 /proc/net/xt_qtaguid/stats 获取进程级网络流量，
    失败则回退到 /proc/net/dev 设备级统计
    """
    MB_CONVERSION = 1024 * 1024

    def real_func():
        d = _get_device(serial)
        start_time = int(time.time())

        # 尝试获取进程 UID（用于进程级网络统计）
        uid = None
        target_pid = pid
        if not target_pid and package_name:
            pid_output = d.shell(f"pidof {package_name}").strip()
            if pid_output:
                parts = pid_output.split()
                target_pid = int(parts[0]) if parts[0].isdigit() else 0

        if target_pid:
            uid_output = d.shell(f"cat /proc/{target_pid}/status 2>/dev/null | grep Uid").strip()
            match = re.search(r'Uid:\s+(\d+)', uid_output)
            if match:
                uid = int(match.group(1))

        def get_net_stats_by_uid(uid_val):
            """通过 UID 获取进程级网络统计"""
            output = d.shell("cat /proc/net/xt_qtaguid/stats 2>/dev/null").strip()
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

        def get_net_stats_device():
            """读取设备级网络统计"""
            rx_bytes = tx_bytes = 0
            output = d.shell("cat /proc/net/dev").strip()
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

        # 第一次采样
        if uid is not None:
            rx1, tx1 = get_net_stats_by_uid(uid)
            if rx1 is None:
                rx1, tx1 = get_net_stats_device()
        else:
            rx1, tx1 = get_net_stats_device()

        time.sleep(1)

        # 第二次采样
        if uid is not None:
            rx2, tx2 = get_net_stats_by_uid(uid)
            if rx2 is None:
                rx2, tx2 = get_net_stats_device()
        else:
            rx2, tx2 = get_net_stats_device()

        net_recv_rate = max(0, ((rx2 or 0) - (rx1 or 0)) / MB_CONVERSION)
        net_sent_rate = max(0, ((tx2 or 0) - (tx1 or 0)) / MB_CONVERSION)

        if net_recv_rate < 0.001:
            net_recv_rate = 0
        if net_sent_rate < 0.001:
            net_sent_rate = 0

        res = {
            "net_sent_rate": round(net_sent_rate, 4),
            "net_recv_rate": round(net_recv_rate, 4),
            "net_sent": tx2 or 0,
            "net_recv": rx2 or 0,
            "time": start_time
        }
        return res

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=20)


# ─────────────────────────── 截图 ───────────────────────────

async def android_screenshot(serial: str, save_dir: str = None, pid: int = 0, **kwargs):
    """Android 设备截图"""
    def real_func():
        d = _get_device(serial)
        from pathlib import Path
        from io import BytesIO

        # 使用 adbutils 的截图功能
        try:
            img = d.screenshot()
            if save_dir:
                dir_instance = Path(save_dir)
                screenshot_dir = dir_instance.joinpath("screenshot")
                screenshot_dir.mkdir(exist_ok=True)
                img.save(screenshot_dir.joinpath(str(int(time.time() + 0.5)) + ".png"), format="PNG")
            else:
                output_buffer = BytesIO()
                img.save(output_buffer, format='PNG')
                output_buffer.seek(0)
                return output_buffer.getvalue()
        except Exception as e:
            logger.error(f"Android 截图失败: {e}")
            return None

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=15)


# ─────────────────────────── 电池信息 ───────────────────────────

async def android_battery(serial: str, **kwargs) -> Dict:
    """采集 Android 设备电池信息（移动端特有指标）"""
    def real_func():
        d = _get_device(serial)
        output = d.shell("dumpsys battery")
        battery_info = {"time": int(time.time())}

        for line in output.strip().split('\n'):
            line = line.strip()
            if 'level' in line.lower() and ':' in line:
                match = re.search(r'level:\s*(\d+)', line, re.IGNORECASE)
                if match:
                    battery_info['battery_level'] = int(match.group(1))
            elif 'temperature' in line.lower() and ':' in line:
                match = re.search(r'temperature:\s*(\d+)', line, re.IGNORECASE)
                if match:
                    # 温度单位是 0.1°C
                    battery_info['battery_temperature'] = round(int(match.group(1)) / 10.0, 1)
            elif 'current now' in line.lower() and ':' in line:
                match = re.search(r'current now:\s*(-?\d+)', line, re.IGNORECASE)
                if match:
                    # 电流单位是 μA，转换为 mA
                    battery_info['battery_current'] = round(int(match.group(1)) / 1000.0, 2)

        # 确保有默认值
        battery_info.setdefault('battery_level', 0)
        battery_info.setdefault('battery_temperature', 0)
        battery_info.setdefault('battery_current', 0)

        return battery_info

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=15)


# ─────────────────────────── 性能采集入口 ───────────────────────────

async def android_perf(serial: str, package_name: str, pid: int, save_dir: str, include_child: bool = False):
    """
    Android 性能采集入口，与 PC 端 perf() 保持一致的 Monitor 结构
    """
    # 如果没有 pid，尝试通过包名获取
    if not pid and package_name:
        try:
            d = _get_device(serial)
            pid_output = d.shell(f"pidof {package_name}").strip()
            if pid_output:
                parts = pid_output.split()
                pid = int(parts[0]) if parts[0].isdigit() else 0
        except Exception:
            pid = 0

    monitors = {
        "cpu": Monitor(android_cpu,
                       serial=serial, pid=pid, package_name=package_name,
                       monitor_name="cpu",
                       key_value=["time", "cpu_usage(%)", "cpu_usage_all(%)", "cpu_core_num(个)"],
                       save_dir=save_dir),
        "memory": Monitor(android_memory,
                          serial=serial, pid=pid, package_name=package_name,
                          monitor_name="memory",
                          key_value=["time", "process_memory_usage(M)"],
                          save_dir=save_dir),
        "process_info": Monitor(android_process_info,
                                serial=serial, pid=pid, package_name=package_name,
                                monitor_name="process_info",
                                key_value=["time", "num_threads(个)", "num_handles(个)"],
                                save_dir=save_dir),
        "fps": Monitor(android_fps,
                       serial=serial, pid=pid, package_name=package_name,
                       monitor_name="fps",
                       key_value=["time", "fps(帧)", "frames"],
                       save_dir=save_dir),
        "gpu": Monitor(android_gpu,
                       serial=serial, pid=pid, package_name=package_name,
                       monitor_name="gpu",
                       key_value=["time", "gpu(%)"],
                       save_dir=save_dir),
        "disk_io": Monitor(android_disk_io,
                           serial=serial, pid=pid, package_name=package_name,
                           monitor_name="disk_io",
                           key_value=["time", "disk_read_rate(MB/s)", "disk_write_rate(MB/s)",
                                      "disk_read(字节)", "disk_write(字节)"],
                           save_dir=save_dir),
        "network_io": Monitor(android_network_io,
                              serial=serial, pid=pid, package_name=package_name,
                              monitor_name="network_io",
                              key_value=["time", "net_sent_rate(MB/s)", "net_recv_rate(MB/s)",
                                         "net_sent(字节)", "net_recv(字节)"],
                              save_dir=save_dir),
        "battery": Monitor(android_battery,
                           serial=serial,
                           monitor_name="battery",
                           key_value=["time", "battery_level(%)", "battery_temperature(℃)",
                                      "battery_current(mA)"],
                           save_dir=save_dir),
        "screenshot": Monitor(android_screenshot,
                              serial=serial,
                              save_dir=save_dir, is_out=False)
    }
    run_monitors = [monitor.run() for name, monitor in monitors.items()]
    await asyncio.gather(*run_monitors)

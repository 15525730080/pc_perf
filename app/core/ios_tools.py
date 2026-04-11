# coding:utf-8
"""
iOS 性能测试模块
go-ios 负责设备发现/tunnel/截图/电池，
py-ios-device 通过 Instruments DTX 协议采集 CPU/内存/网络/磁盘。

go-ios 需要先启动 tunnel (iOS 17+):
    ENABLE_GO_IOS_AGENT=user /path/to/ios tunnel start --userspace

可用命令:
    ios list                    设备列表
    ios info                    设备信息
    ios ps                      进程列表 (需要 tunnel)
    ios apps                    应用列表
    ios screenshot              截图
    ios batterycheck/batteryregistry  电池
    ios diskspace               磁盘空间
"""
import asyncio
import dataclasses
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import threading
from pathlib import Path
from typing import Optional, Dict, List

from app.log import log as logger
from app.core.monitor import Monitor

# ── py-ios-device (Instruments DTX 协议) ──────────────────────────────────
try:
    from ios_device.remote.remote_lockdown import RemoteLockdownClient
    from ios_device.cli.base import InstrumentsBase
    _PY_IOS_DEVICE_AVAILABLE = True
except ImportError:
    _PY_IOS_DEVICE_AVAILABLE = False
    logger.warning("py-ios-device 未安装，iOS 进程级指标不可用。pip install py-ios-device")

# ─────────────────────────── go-ios 路径 ───────────────────────────

# 按优先级查找 go-ios
# Downloads 里的版本优先（已验证支持 userspace tunnel）
# 环境变量 GO_IOS_PATH 可覆盖
# 从 tool/go-ios-bin 目录中选择合适的 ios 工具
def get_ios_tool_path():
    """根据当前平台返回合适的 ios 工具路径"""
    tool_dir = Path(__file__).parent.parent.parent.joinpath("tool", "go-ios-bin")
    
    if sys.platform == "win32":
        return tool_dir.joinpath("go-ios-win", "ios.exe")
    elif sys.platform == "darwin":
        return tool_dir.joinpath("go-ios-mac", "ios")
    elif sys.platform == "linux":
        # 根据架构选择
        if platform.machine() == "arm64":
            return tool_dir.joinpath("go-ios-linux", "ios-arm64")
        else:
            return tool_dir.joinpath("go-ios-linux", "ios-amd64")
    return None

_DOWNLOADS_IOS = str(get_ios_tool_path())
GO_IOS_PATH = (
    os.environ.get("GO_IOS_PATH")
    or (_DOWNLOADS_IOS if os.path.isfile(_DOWNLOADS_IOS) else None)
    or shutil.which("ios")
    or shutil.which("go-ios")
)

if not os.path.isfile(GO_IOS_PATH):
    GO_IOS_PATH = None
    logger.warning("go-ios 未找到，iOS 性能测试不可用")


def _go_ios_env() -> dict:
    """返回执行 go-ios 命令所需的环境变量（含 ENABLE_GO_IOS_AGENT=user 以连接 userspace tunnel）"""
    env = os.environ.copy()
    env.setdefault("ENABLE_GO_IOS_AGENT", "user")
    return env


def _run(args: list, timeout: int = 15) -> Optional[str]:
    """执行 go-ios 命令，返回有内容的输出（优先 stdout，其次 stderr）"""
    if not GO_IOS_PATH:
        return None
    try:
        result = subprocess.run(
            [GO_IOS_PATH] + args,
            capture_output=True, text=True, timeout=timeout,
            env=_go_ios_env(),
            encoding="utf-8"
        )
        # go-ios 有些命令数据走 stdout，有些走 stderr（logrus 格式）
        out = result.stdout.strip()
        if out:
            return out
        err = result.stderr.strip()
        if err:
            return err
        return None
    except subprocess.TimeoutExpired:
        logger.error(f"go-ios {' '.join(args)} 超时")
    except Exception as e:
        logger.error(f"go-ios {' '.join(args)} 异常: {e}")
    return None


def _run_json(args: list, timeout: int = 15):
    """执行 go-ios 命令，返回解析后的 JSON 或 None"""
    raw = _run(args, timeout)
    if not raw:
        return None
    # go-ios 输出可能有多行，每行一个 JSON，也可能前面有 warning 行
    # 找最后一个合法 JSON
    lines = raw.strip().split("\n")
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return None


# ─────────────────────────── Tunnel 管理 ───────────────────────────

class TunnelManager:
    """管理 go-ios tunnel"""
    _proc: Optional[subprocess.Popen] = None
    _tunnel_procs: List[subprocess.Popen] = []

    @classmethod
    def ensure_tunnel(cls, udid: str = "") -> bool:
        """确保 tunnel 已启动，返回是否可用"""
        info = cls.tunnel_info()
        if info:
            return True
        return cls.start(udid)

    @classmethod
    def tunnel_info(cls) -> Optional[list]:
        """查询已有 tunnel"""
        data = _run_json(["tunnel", "ls"])
        if isinstance(data, list) and data:
            return data
        return None

    @classmethod
    def start(cls, udid: str = "") -> bool:
        """启动 tunnel（后台进程）"""
        if not GO_IOS_PATH:
            return False
        args = [GO_IOS_PATH, "tunnel", "start", "--userspace"]
        if udid:
            args += ["--udid", udid]
        env = os.environ.copy()
        env["ENABLE_GO_IOS_AGENT"] = "user"
        try:
            proc = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, env=env, encoding="utf-8"
            )
            cls._proc = proc
            cls._tunnel_procs.append(proc)
            # 等待 tunnel 建立
            for _ in range(20):
                time.sleep(1)
                if cls.tunnel_info():
                    logger.info("go-ios tunnel 已启动")
                    return True
            logger.error("go-ios tunnel 启动超时")
        except Exception as e:
            logger.error(f"go-ios tunnel 启动失败: {e}")
        return False

    @classmethod
    def stop(cls):
        if cls._proc and cls._proc.poll() is None:
            cls._proc.terminate()
            cls._proc = None
        # 也尝试 stopagent
        _run(["tunnel", "stopagent"], timeout=5)

    @classmethod
    def stop_all_tunnels(cls):
        """停止所有 tunnel 进程"""
        for proc in cls._tunnel_procs:
            try:
                if proc.poll() is None:
                    proc.terminate()
            except Exception:
                pass
        cls._tunnel_procs.clear()
        cls._proc = None
        _run(["tunnel", "stopagent"], timeout=5)


# ─────────────────────────── 设备发现 ───────────────────────────

def get_ios_devices() -> List[Dict]:
    """获取已连接的 iOS 设备列表"""
    data = _run_json(["list"])
    if not data:
        return []
    udid_list = data.get("deviceList", []) if isinstance(data, dict) else []
    devices = []
    for udid in udid_list:
        info = _run_json(["info", "--udid", udid]) or {}
        devices.append({
            "udid": udid,
            "model": info.get("DeviceName", "Unknown"),
            "product_type": info.get("ProductType", "Unknown"),
            "ios_version": info.get("ProductVersion", "Unknown"),
            "status": "online",
            "device_type": "ios",
            # 统一字段，与 Android 保持一致
            "serial": udid,
            "name": info.get("DeviceName", "Unknown"),
        })
    return devices


def _first_udid() -> Optional[str]:
    """获取第一个设备的 UDID"""
    data = _run_json(["list"])
    if data:
        dl = data.get("deviceList", []) if isinstance(data, dict) else []
        if dl:
            return dl[0]
    return None


# ─────────────────────────── 自动获取前台应用 ───────────────────────────

def _get_foreground_app(udid: str) -> Optional[Dict]:
    """
    获取前台运行的应用信息 (pid + bundleId)
    通过 ps 列表中 IsApplication=true 且最近启动的应用判断
    """
    raw = _run(["ps", "--udid", udid])
    if not raw:
        return None
    # ps 输出是一个 JSON 数组
    lines = raw.strip().split("\n")
    for line in reversed(lines):
        try:
            processes = json.loads(line)
            if isinstance(processes, list):
                # 筛选 IsApplication=true 的进程，按 StartDate 倒序
                apps = [p for p in processes if p.get("IsApplication")]
                if apps:
                    apps.sort(key=lambda x: x.get("StartDate", ""), reverse=True)
                    return {
                        "pid": apps[0].get("Pid", 0),
                        "name": apps[0].get("Name", ""),
                        "bundle_id": _pid_to_bundle(udid, apps[0].get("Name", ""))
                    }
        except json.JSONDecodeError:
            continue
    return None


def _pid_to_bundle(udid: str, process_name: str) -> str:
    """通过进程名反查 bundle_id"""
    raw = _run(["apps", "--udid", udid])
    if not raw:
        return process_name
    lines = raw.strip().split("\n")
    for line in reversed(lines):
        try:
            apps = json.loads(line)
            if isinstance(apps, list):
                for app in apps:
                    exe = app.get("CFBundleExecutable", "")
                    if exe == process_name:
                        return app.get("CFBundleIdentifier", process_name)
        except json.JSONDecodeError:
            continue
    return process_name


def _find_pid_by_bundle(udid: str, bundle_id: str) -> int:
    """通过 bundle_id 查找 pid"""
    # 先查 executable name
    exe_name = bundle_id  # fallback
    raw_apps = _run(["apps", "--udid", udid])
    if raw_apps:
        for line in reversed(raw_apps.strip().split("\n")):
            try:
                apps = json.loads(line)
                if isinstance(apps, list):
                    for app in apps:
                        if app.get("CFBundleIdentifier") == bundle_id:
                            exe_name = app.get("CFBundleExecutable", bundle_id)
                            break
            except json.JSONDecodeError:
                continue

    raw_ps = _run(["ps", "--udid", udid])
    if raw_ps:
        for line in reversed(raw_ps.strip().split("\n")):
            try:
                processes = json.loads(line)
                if isinstance(processes, list):
                    for p in processes:
                        if p.get("Name") == exe_name:
                            return p.get("Pid", 0)
            except json.JSONDecodeError:
                continue
    return 0


# ─────────────────────────── 应用列表 ───────────────────────────

async def ios_apps(udid: str) -> List[Dict]:
    """获取已安装应用列表（异步，go-ios apps 可能较慢，超时 30 秒）"""
    def real_func():
        raw = _run(["apps", "--udid", udid], timeout=30)
        if not raw:
            return []
        lines = raw.strip().split("\n")
        for line in reversed(lines):
            try:
                apps = json.loads(line)
                if isinstance(apps, list):
                    result = []
                    for app in apps:
                        bid = app.get("CFBundleIdentifier", "")
                        if bid and app.get("ApplicationType") == "User":
                            result.append({
                                "bundle_id": bid,
                                "name": app.get("CFBundleDisplayName") or app.get("CFBundleName", bid),
                                "version": app.get("CFBundleShortVersionString", ""),
                                # 兼容 Android 字段
                                "package_name": bid,
                                "running": False,
                            })
                    return result
            except json.JSONDecodeError:
                continue
        return []

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=35)


# ─────────────────────────── 系统信息 ───────────────────────────

async def ios_sys_info(udid: str) -> Dict:
    """获取设备系统信息"""
    def real_func():
        info = _run_json(["info", "--udid", udid]) or {}
        disk = _run_json(["diskspace", "--udid", udid]) or {}
        return {
            "platform": "iOS",
            "computer_name": info.get("DeviceName", "Unknown"),
            "time": time.time(),
            "cpu_count": 0,
            "cpu_cores": 0,
            "cpu_name": info.get("CPUArchitecture", "Unknown"),
            "memory_total": 0,
            "ram": "Unknown",
            "rom": f"{round(disk.get('TotalBytes', 0) / (1024 ** 3), 1)}G",
            "disk_total": round(disk.get("TotalBytes", 0) / (1024 ** 3), 1),
            "product_type": info.get("ProductType", "Unknown"),
            "ios_version": info.get("ProductVersion", "Unknown"),
            "serial": udid,
        }
    return await asyncio.to_thread(real_func)


# ─────────────────────────── sysmontap 采集（CPU + 内存） ───────────────────────────

def _read_sysmontap_sample(udid: str, skip_count: int = 2) -> Optional[Dict]:
    """
    启动 sysmontap，读取第 skip_count 条有效数据后终止。
    sysmontap 输出字段（go-ios v1.0.x）:
      cpu_count, cpu_total_load, enabled_cpus,
      mem_free, mem_used, mem_total,
      net_bytes_in, net_bytes_out,
      disk_bytes_read, disk_bytes_written, ...
    返回原始 dict 或 None。
    """
    if not GO_IOS_PATH:
        return None
    try:
        proc = subprocess.Popen(
            [GO_IOS_PATH, "sysmontap", "--udid", udid],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True, bufsize=1, env=_go_ios_env(), encoding="utf-8"
        )
        count = 0
        result_data = None
        try:
            for line in iter(proc.stderr.readline, ''):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # 只要包含 cpu_total_load 就认为是有效数据
                if "cpu_total_load" in data:
                    count += 1
                    if count >= skip_count:
                        result_data = data
                        break
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
        return result_data
    except Exception as e:
        logger.error(f"iOS sysmontap 采集失败: {e}")
        return None


# ─────────────────────────── Instruments Session (py-ios-device) ───────────────────────────

def _get_tunnel_info() -> Optional[Dict]:
    """从 go-ios tunnel ls 获取当前 tunnel 的地址和端口"""
    raw = _run(["tunnel", "ls"], timeout=5)
    if not raw:
        return None
    # 先尝试整体解析（tunnel ls 输出格式化多行 JSON）
    try:
        tunnels = json.loads(raw.strip())
        if isinstance(tunnels, list) and tunnels:
            return tunnels[0]
    except Exception:
        pass
    # fallback：逐行找 JSON 数组行（单行输出格式）
    for line in reversed(raw.strip().split("\n")):
        line = line.strip()
        if line.startswith("["):
            try:
                tunnels = json.loads(line)
                if isinstance(tunnels, list) and tunnels:
                    return tunnels[0]
            except Exception:
                pass
    return None


class _InstrumentsSession:
    """
    通过 py-ios-device + go-ios tunnel 连接 Apple Instruments DTX 服务。

    【优化】后台持续采集模式：
      - start(pid) 启动后台线程，持续以 1s 间隔采集所有进程+系统数据
      - 各采集函数直接读缓存，响应时间 < 50ms
      - 连接断开后自动重连（最多 3 次）
      - stop() 停止后台线程并断开连接

    使用方式：
        session = _InstrumentsSession.get(udid)
        session.start(pid=66344)          # 首次调用时启动后台采集
        data = session.get_latest(pid)    # 立即返回最新缓存
    """

    # 进程级属性（有序列表，顺序决定 zip 映射）
    PROC_ATTRS = [
        'pid', 'name', 'cpuUsage',
        'physFootprint',        # 进程物理内存 bytes
        'diskBytesRead', 'diskBytesWritten',
        'threadCount',
    ]
    # 系统级属性
    SYS_ATTRS = [
        'vmUsedCount', 'vmFreeCount', 'physMemSize',
        'netBytesIn', 'netBytesOut',
        'diskBytesRead', 'diskBytesWritten',
    ]

    # 全局实例池（每个 udid 一个）
    _pool: Dict[str, "_InstrumentsSession"] = {}
    _pool_lock = threading.Lock()

    @classmethod
    def get(cls, udid: str) -> "_InstrumentsSession":
        with cls._pool_lock:
            if udid not in cls._pool:
                cls._pool[udid] = cls(udid)
            return cls._pool[udid]

    def __init__(self, udid: str):
        self.udid = udid
        self._lock = threading.Lock()
        self._start_lock = threading.Lock()   # 保证 start() 只执行一次
        self._stop_event = threading.Event()
        self._data_ready = threading.Event()  # 首次数据就绪信号
        self._bg_thread: Optional[threading.Thread] = None
        self._running = False

        # 缓存：{pid: {proc_data}, "sys": {sys_data}, "ts": float}
        self._cache: Dict = {"sys": {}, "procs": {}, "ts": 0.0}
        # graphics 缓存：{"fps": int, "gpu": float, "gpu_renderer": float, "gpu_tiler": float, "ts": float}
        self._graphics_cache: Dict = {"fps": 0, "gpu": 0.0, "gpu_renderer": 0.0, "gpu_tiler": 0.0, "ts": 0.0}
        self._graphics_ready = threading.Event()
        self._graphics_thread: Optional[threading.Thread] = None
        self._graphics_start_lock = threading.Lock()
        self._graphics_running = False

        # 已订阅的 pid 集合
        self._watched_pids: set = set()

        # 动态属性列表（首次连接后填充）
        self._proc_attrs: List[str] = []
        self._sys_attrs:  List[str] = []

    # ── 连接管理 ──────────────────────────────────────────────────

    def _make_lockdown(self):
        info = _get_tunnel_info()
        if not info:
            raise RuntimeError(
                "go-ios tunnel 未启动，请先运行: "
                "ENABLE_GO_IOS_AGENT=user ios tunnel start --userspace"
            )
        lockdown = RemoteLockdownClient(
            address=(info["address"], info["rsdPort"]),
            userspace_port=info.get("userspaceTunPort")
        )
        lockdown.connect()
        return lockdown

    # ── 后台采集线程 ──────────────────────────────────────────────

    def _bg_loop(self):
        """后台线程：持续采集，断线自动重连"""
        retry = 0
        max_retry = 5
        while not self._stop_event.is_set() and retry < max_retry:
            try:
                self._run_sysmontap_loop()
                retry = 0  # 正常退出（stop_event 触发）则重置重试计数
            except Exception as e:
                if self._stop_event.is_set():
                    break
                retry += 1
                logger.warning(f"[Instruments] 连接断开，{retry}/{max_retry} 次重连: {e}")
                time.sleep(min(2 ** retry, 10))
        with self._lock:
            self._running = False
        logger.info(f"[Instruments] 后台采集线程退出 udid={self.udid}")

    def _run_sysmontap_loop(self):
        """建立一次连接并持续采集，直到 stop_event 触发或连接断开。

        【关键】只用 InstrumentsBase 一个对象管理连接：
          - base.device_info  → 查询设备支持的属性（内部懒建 instruments_rcp）
          - base.sysmontap()  → 持续采集（复用同一个 instruments_rcp）
          不要额外创建 InstrumentServer / InstrumentDeviceInfo，否则会抢占
          lockdown 连接导致 socket 3s 后断开。
        """
        lockdown = self._make_lockdown()
        base = InstrumentsBase(lockdown=lockdown)

        # 查询设备支持的属性（取交集）
        available_proc = base.device_info.sysmonProcessAttributes()
        available_sys  = base.device_info.sysmonSystemAttributes()
        proc_attrs = [a for a in self.PROC_ATTRS if a in available_proc]
        sys_attrs  = [a for a in self.SYS_ATTRS  if a in available_sys]

        base.process_attributes = proc_attrs
        base.system_attributes  = sys_attrs

        with self._lock:
            self._proc_attrs = proc_attrs
            self._sys_attrs  = sys_attrs

        logger.info(f"[Instruments] proc_attrs={proc_attrs}")
        logger.info(f"[Instruments] sys_attrs={sys_attrs}")

        def callback(res):
            sel = res.selector
            # 过滤握手/配置包（dict 格式，如 {'k':0,'tv':65536}）
            if not isinstance(sel, list):
                return
            ts = time.time()
            new_procs = {}
            new_sys   = {}
            for row in sel:
                if not isinstance(row, dict):
                    continue
                # 系统数据
                if "System" in row:
                    raw = row["System"]
                    if isinstance(raw, (list, tuple)) and len(raw) == len(sys_attrs):
                        new_sys = dict(zip(sys_attrs, raw))
                    elif isinstance(raw, dict):
                        new_sys = {k: raw.get(k) for k in sys_attrs}
                # 进程数据（所有进程都缓存，按 pid 索引）
                if "Processes" in row:
                    for pid_key, vals in row["Processes"].items():
                        try:
                            p = int(pid_key)
                        except (ValueError, TypeError):
                            p = pid_key
                        if isinstance(vals, (list, tuple)) and len(vals) == len(proc_attrs):
                            new_procs[p] = dict(zip(proc_attrs, vals))
                        elif isinstance(vals, dict):
                            new_procs[p] = {k: vals.get(k) for k in proc_attrs}
            with self._lock:
                if new_sys:
                    self._cache["sys"] = new_sys
                if new_procs:
                    self._cache["procs"].update(new_procs)
                if new_sys or new_procs:
                    self._cache["ts"] = ts
                    self._data_ready.set()   # 通知等待方：首次数据已就绪

        logger.info(f"[Instruments] 开始持续采集 udid={self.udid}")
        base.sysmontap(callback=callback, time=1000, stopSignal=self._stop_event)

        try:
            base.instruments.stop()
        except Exception:
            pass

    # ── Graphics 后台采集（FPS + GPU）────────────────────────────

    def _run_graphics_loop(self):
        """建立独立连接持续采集 FPS / GPU，直到 stop_event 触发。"""
        lockdown = self._make_lockdown()
        base = InstrumentsBase(lockdown=lockdown)

        def callback(res):
            sel = res.selector
            if not isinstance(sel, dict):
                return
            fps  = sel.get("CoreAnimationFramesPerSecond", 0) or 0
            gpu  = sel.get("Device Utilization %", 0.0) or 0.0
            rend = sel.get("Renderer Utilization %", 0.0) or 0.0
            tile = sel.get("Tiler Utilization %", 0.0) or 0.0
            with self._lock:
                self._graphics_cache = {
                    "fps": int(fps),
                    "gpu": round(float(gpu), 2),
                    "gpu_renderer": round(float(rend), 2),
                    "gpu_tiler": round(float(tile), 2),
                    "ts": time.time(),
                }
                self._graphics_ready.set()

        logger.info(f"[Instruments] 开始采集 FPS/GPU udid={self.udid}")
        base.graphics(callback=callback, time=1000, stopSignal=self._stop_event)
        try:
            base.instruments.stop()
        except Exception:
            pass

    def _graphics_bg_loop(self):
        """FPS/GPU 后台线程，断线自动重连"""
        retry = 0
        max_retry = 5
        while not self._stop_event.is_set() and retry < max_retry:
            try:
                self._run_graphics_loop()
                retry = 0
            except Exception as e:
                if self._stop_event.is_set():
                    break
                retry += 1
                logger.warning(f"[Instruments/FPS] 连接断开，{retry}/{max_retry} 次重连: {e}")
                time.sleep(min(2 ** retry, 10))
        with self._lock:
            self._graphics_running = False
        logger.info(f"[Instruments/FPS] 后台线程退出 udid={self.udid}")

    def start_graphics(self):
        """启动 FPS/GPU 后台采集线程（幂等）。阻塞直到首次数据就绪（最多 5s）。"""
        with self._graphics_start_lock:
            if self._graphics_running:
                pass
            else:
                self._graphics_ready.clear()
                self._graphics_running = True
                self._graphics_thread = threading.Thread(
                    target=self._graphics_bg_loop, daemon=True,
                    name=f"instruments-fps-{self.udid[:8]}"
                )
                self._graphics_thread.start()
        got = self._graphics_ready.wait(timeout=5)
        if not got:
            logger.warning(f"[Instruments/FPS] 等待首次数据超时 udid={self.udid}")

    def get_graphics(self) -> Dict:
        """读取最新 FPS/GPU 缓存，若未启动则自动 start_graphics()。"""
        with self._lock:
            running = self._graphics_running
        if not running:
            self.start_graphics()
        with self._lock:
            return dict(self._graphics_cache)

    # ── 公开接口 ──────────────────────────────────────────────────

    def start(self, pid: int = 0):
        """启动后台采集线程（幂等，多线程并发安全）。
        阻塞直到首次数据就绪（最多 8s），之后立即返回。
        """
        with self._start_lock:
            if self._running:
                # 已在运行：锁外等待数据就绪（不持锁阻塞）
                pass
            else:
                if pid:
                    self._watched_pids.add(pid)
                self._stop_event.clear()
                self._data_ready.clear()
                self._running = True
                self._bg_thread = threading.Thread(
                    target=self._bg_loop, daemon=True, name=f"instruments-{self.udid[:8]}"
                )
                self._bg_thread.start()

        # 锁外等待首次数据就绪（最多 8 秒）
        # 无论是新启动还是已在运行，都在这里等，不持锁
        got = self._data_ready.wait(timeout=8)
        if not got:
            logger.warning(f"[Instruments] 等待首次数据超时 udid={self.udid}")

    def stop(self):
        """停止所有后台采集线程"""
        self._stop_event.set()
        if self._bg_thread and self._bg_thread.is_alive():
            self._bg_thread.join(timeout=5)
        if self._graphics_thread and self._graphics_thread.is_alive():
            self._graphics_thread.join(timeout=5)
        with self._lock:
            self._running = False
            self._graphics_running = False
            self._cache = {"sys": {}, "procs": {}, "ts": 0.0}
            self._graphics_cache = {"fps": 0, "gpu": 0.0, "gpu_renderer": 0.0, "gpu_tiler": 0.0, "ts": 0.0}

    def get_latest(self, pid: int = 0) -> Dict:
        """
        读取最新缓存数据。
        若后台线程未启动，则自动 start()（内部等待首次数据就绪）。
        返回: {"proc": {...}, "sys": {...}}
        """
        with self._lock:
            running = self._running

        if not running:
            self.start(pid)   # 阻塞直到首次数据就绪

        with self._lock:
            sys_data  = dict(self._cache.get("sys", {}))
            proc_data = dict(self._cache.get("procs", {}).get(pid, {})) if pid else {}
            cache_ts  = self._cache["ts"]

        # 缓存超过 5 秒认为连接已断
        if cache_ts > 0 and (time.time() - cache_ts) > 5:
            logger.warning(f"[Instruments] 缓存超时 {time.time()-cache_ts:.1f}s，数据可能过期")

        return {"proc": proc_data, "sys": sys_data}


# ── 全局管理：按 udid 获取 session ────────────────────────────────

def _get_instruments_session(udid: str) -> Optional["_InstrumentsSession"]:
    """获取（或创建）指定设备的 Instruments session"""
    if not _PY_IOS_DEVICE_AVAILABLE:
        return None
    return _InstrumentsSession.get(udid)


def ios_instruments_stop(udid: str):
    """主动停止指定设备的 Instruments 后台采集（设备断开时调用）"""
    with _InstrumentsSession._pool_lock:
        session = _InstrumentsSession._pool.pop(udid, None)
    if session:
        session.stop()
        logger.info(f"[Instruments] 已停止 udid={udid}")


# ─────────────────────────── CPU 采集 ───────────────────────────

async def ios_cpu(udid: str, pid: int = 0, **kwargs) -> Optional[Dict]:
    """
    采集 CPU 使用率。
    优先使用 py-ios-device Instruments（进程级 cpuUsage + 系统总负载）。
    fallback 到 go-ios sysmontap（仅系统总负载）。
    """

    def real_func():
        current_time = int(time.time())
        # ── Instruments 方案（读缓存，< 50ms）────────────────────────
        if _PY_IOS_DEVICE_AVAILABLE:
            try:
                data = _InstrumentsSession.get(udid).get_latest(pid)
                proc = data.get("proc", {})
                cpu_usage = round(float(proc.get("cpuUsage") or 0), 2)
                return {
                    "cpu_usage": cpu_usage,
                    "cpu_usage_all": cpu_usage,
                    "cpu_core_num": 0,
                    "time": current_time,
                }
            except Exception as e:
                logger.warning(f"Instruments CPU 采集失败，fallback go-ios: {e}")
        # ── fallback: go-ios sysmontap（仅系统总负载）──────────────
        data = _read_sysmontap_sample(udid, skip_count=2)
        if data:
            return {
                "cpu_usage": 0,
                "cpu_usage_all": round(data.get("cpu_total_load", 0), 2),
                "cpu_core_num": data.get("cpu_count", 0),
                "time": current_time,
            }
        return {"cpu_usage": 0, "cpu_usage_all": 0, "cpu_core_num": 0, "time": current_time}

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=25)


# ─────────────────────────── 内存采集 ───────────────────────────

async def ios_memory(udid: str, pid: int = 0, **kwargs) -> Optional[Dict]:
    """
    采集内存使用。
    使用 py-ios-device Instruments:
      - 进程内存: physFootprint (bytes) → MB
      - 系统总内存: physMemSize (pages * 16384) → MB
      - 系统空闲: vmFreeCount (pages * 16384) → MB
    """
    PAGE_SIZE = 16384  # iOS 页大小 16KB

    def real_func():
        current_time = int(time.time())
        if _PY_IOS_DEVICE_AVAILABLE:
            try:
                data = _InstrumentsSession.get(udid).get_latest(pid)
                proc = data.get("proc", {})
                sys  = data.get("sys", {})

                # 进程物理内存 (bytes → MB)
                phys = proc.get("physFootprint") or 0
                proc_mem_mb = round(phys / (1024 * 1024), 2)

                # 系统总内存 (pages → MB)
                phys_mem_pages = sys.get("physMemSize") or 0
                mem_total_mb = round(phys_mem_pages * PAGE_SIZE / (1024 * 1024), 2)

                return {
                    "process_memory_usage": proc_mem_mb,
                    "memory_total": mem_total_mb,
                    "time": current_time,
                }
            except Exception as e:
                logger.warning(f"Instruments Memory 采集失败: {e}")
        return {"process_memory_usage": 0, "memory_total": 0, "time": current_time}

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=25)


# ─────────────────────────── FPS 采集 ───────────────────────────

async def ios_fps(udid: str, pid: int = 0, **kwargs) -> Optional[Dict]:
    """
    采集 FPS（CoreAnimationFramesPerSecond）。
    通过 py-ios-device Instruments GraphicsOpengl channel 采集。
    手机屏幕亮起且有 UI 渲染时才有非零值。
    """
    def real_func():
        current_time = int(time.time())
        if _PY_IOS_DEVICE_AVAILABLE:
            try:
                g = _InstrumentsSession.get(udid).get_graphics()
                return {
                    "fps": g.get("fps", 0),
                    "frames": [],
                    "time": current_time,
                }
            except Exception as e:
                logger.warning(f"Instruments FPS 采集失败: {e}")
        return {"fps": 0, "frames": [], "time": current_time}

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=15)


# ─────────────────────────── GPU 采集 ───────────────────────────

async def ios_gpu(udid: str, pid: int = 0, **kwargs) -> Dict:
    """
    采集 GPU 使用率。
    通过 py-ios-device Instruments GraphicsOpengl channel 采集：
      - gpu:          Device Utilization %（整体 GPU 利用率）
      - gpu_renderer: Renderer Utilization %
      - gpu_tiler:    Tiler Utilization %
    """
    def real_func():
        current_time = int(time.time())
        if _PY_IOS_DEVICE_AVAILABLE:
            try:
                g = _InstrumentsSession.get(udid).get_graphics()
                return {
                    "gpu": g.get("gpu", 0.0),
                    "gpu_renderer": g.get("gpu_renderer", 0.0),
                    "gpu_tiler": g.get("gpu_tiler", 0.0),
                    "time": current_time,
                }
            except Exception as e:
                logger.warning(f"Instruments GPU 采集失败: {e}")
        return {"gpu": 0.0, "gpu_renderer": 0.0, "gpu_tiler": 0.0, "time": current_time}

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=15)


# ─────────────────────────── 进程信息 ───────────────────────────

async def ios_process_info(udid: str, bundle_id: str = "", pid: int = 0, **kwargs) -> Dict:
    """
    采集进程信息（线程数）。
    优先从 Instruments sysmontap 缓存读取 threadCount（< 1ms）。
    fallback 到 go-ios ps（较慢，超时 8s）。
    """
    def real_func():
        current_time = int(time.time())
        num_threads = 0

        # ── 优先：Instruments 缓存（threadCount 字段）────────────
        if _PY_IOS_DEVICE_AVAILABLE and pid:
            try:
                data = _InstrumentsSession.get(udid).get_latest(pid)
                tc = data.get("proc", {}).get("threadCount")
                if tc is not None:
                    return {"time": current_time, "num_threads": int(tc), "num_handles": 0}
            except Exception:
                pass

        # ── fallback：go-ios ps（超时 8s）────────────────────────
        if bundle_id:
            raw = _run(["ps", "--udid", udid], timeout=8)
            if raw:
                for line in reversed(raw.strip().split("\n")):
                    try:
                        processes = json.loads(line)
                        if isinstance(processes, list):
                            app_procs = [p for p in processes
                                         if bundle_id.split(".")[-1].lower() in p.get("Name", "").lower()]
                            num_threads = len(app_procs) if app_procs else 0
                            break
                    except json.JSONDecodeError:
                        continue

        return {"time": current_time, "num_threads": num_threads, "num_handles": 0}

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=12)


# ─────────────────────────── 网络 IO ───────────────────────────

# 全局网络IO状态缓存（用于计算速率）
_net_io_cache: Dict[str, Dict] = {}
_net_io_lock = threading.Lock()


async def ios_network_io(udid: str, pid: int = 0, **kwargs) -> Dict:
    """
    采集网络 I/O（系统级累计值 + 速率）。
    使用 py-ios-device Instruments 的 netBytesIn / netBytesOut。
    """
    MB = 1024 * 1024

    def real_func():
        current_time = int(time.time())
        net_in = net_out = 0

        if _PY_IOS_DEVICE_AVAILABLE:
            try:
                data = _InstrumentsSession.get(udid).get_latest(pid)
                sys_d = data.get("sys", {})
                net_in  = sys_d.get("netBytesIn")  or 0
                net_out = sys_d.get("netBytesOut") or 0
            except Exception as e:
                logger.warning(f"Instruments Network 采集失败: {e}")

        with _net_io_lock:
            cache = _net_io_cache.get(udid)
            if cache and net_in:
                dt = current_time - cache["time"]
                recv_rate = max(0, (net_in  - cache["net_in"])  / MB / dt) if dt > 0 else 0
                sent_rate = max(0, (net_out - cache["net_out"]) / MB / dt) if dt > 0 else 0
            else:
                recv_rate = sent_rate = 0
            if net_in or net_out:
                _net_io_cache[udid] = {"time": current_time, "net_in": net_in, "net_out": net_out}

        return {
            "net_sent_rate": round(sent_rate, 4),
            "net_recv_rate": round(recv_rate, 4),
            "net_sent": net_out,
            "net_recv": net_in,
            "time": current_time,
        }

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=25)


# ─────────────────────────── 磁盘 IO ───────────────────────────

# 全局磁盘IO状态缓存
_disk_io_cache: Dict[str, Dict] = {}
_disk_io_lock = threading.Lock()


async def ios_disk_io(udid: str, pid: int = 0, **kwargs) -> Dict:
    """
    采集磁盘 I/O（系统级累计值 + 速率）。
    使用 py-ios-device Instruments 的 diskBytesRead / diskBytesWritten。
    """
    MB = 1024 * 1024

    def real_func():
        current_time = int(time.time())
        disk_read = disk_write = 0

        if _PY_IOS_DEVICE_AVAILABLE:
            try:
                data = _InstrumentsSession.get(udid).get_latest(pid)
                sys_d = data.get("sys", {})
                disk_read  = sys_d.get("diskBytesRead")    or 0
                disk_write = sys_d.get("diskBytesWritten") or 0
            except Exception as e:
                logger.warning(f"Instruments DiskIO 采集失败: {e}")

        with _disk_io_lock:
            cache = _disk_io_cache.get(udid)
            if cache and disk_read:
                dt = current_time - cache["time"]
                read_rate  = max(0, (disk_read  - cache["disk_read"])  / MB / dt) if dt > 0 else 0
                write_rate = max(0, (disk_write - cache["disk_write"]) / MB / dt) if dt > 0 else 0
            else:
                read_rate = write_rate = 0
            if disk_read or disk_write:
                _disk_io_cache[udid] = {"time": current_time, "disk_read": disk_read, "disk_write": disk_write}

        return {
            "disk_read_rate": round(read_rate, 4),
            "disk_write_rate": round(write_rate, 4),
            "disk_read": disk_read,
            "disk_write": disk_write,
            "time": current_time,
        }

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=25)


# ─────────────────────────── 电池信息 ───────────────────────────

async def ios_battery(udid: str, **kwargs) -> Dict:
    """
    采集电池信息
    优先使用 batteryregistry（含电流、温度、电量），
    失败则回退到 batterycheck（仅电量）。
    """
    def real_func():
        # 优先 batteryregistry：InstantAmperage(mA), Temperature(0.01°C), CurrentCapacity(%)
        data = _run_json(["batteryregistry", "--udid", udid]) or {}
        if data.get("CurrentCapacity") is not None:
            # Temperature 单位是 0.01°C（如 3659 = 36.59°C）
            temp = round(data.get("Temperature", 0) / 100.0, 2)
            # InstantAmperage 单位是 mA（正值=充电，负值=放电）
            current = round(data.get("InstantAmperage", 0) / 1.0, 2)
            return {
                "time": int(time.time()),
                "battery_level": data.get("CurrentCapacity", 0),
                "battery_temperature": temp,
                "battery_current": current,
            }
        # 回退 batterycheck
        data2 = _run_json(["batterycheck", "--udid", udid]) or {}
        return {
            "time": int(time.time()),
            "battery_level": data2.get("BatteryCurrentCapacity", 0),
            "battery_temperature": 0,
            "battery_current": 0,
        }

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=15)


# ─────────────────────────── 截图 ───────────────────────────

async def ios_screenshot(udid: str, save_dir: str = None, **kwargs):
    """设备截图"""
    def real_func():
        if not GO_IOS_PATH:
            return None
        if save_dir:
            screenshot_dir = Path(save_dir) / "screenshot"
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            out_path = str(screenshot_dir / f"{int(time.time())}.png")
        else:
            out_path = f"/tmp/ios_screenshot_{int(time.time())}.png"

        # go-ios screenshot 成功信息输出到 stderr，直接执行并检查文件
        try:
            subprocess.run(
                [GO_IOS_PATH, "screenshot", "--udid", udid, "--output", out_path],
                capture_output=True, timeout=15, encoding="utf-8"
            )
        except Exception as e:
            logger.error(f"iOS 截图失败: {e}")
            return None

        if os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
            if not save_dir:
                with open(out_path, "rb") as f:
                    data = f.read()
                os.remove(out_path)
                return data
            return True  # save_dir 模式下文件已保存
        return None

    return await asyncio.wait_for(asyncio.to_thread(real_func), timeout=20)


# ─────────────────────────── 性能采集入口 ───────────────────────────

async def ios_perf(udid: str, bundle_id: str, pid: int, save_dir: str, include_child: bool = False):
    """
    iOS 性能采集入口
    udid/bundle_id/pid 由上层传入，bundle_id 和 pid 可以自动获取

    支持的指标（py-ios-device Instruments + go-ios）：
    - CPU 使用率（Instruments sysmontap，进程级）
    - 内存使用（Instruments sysmontap，physFootprint）
    - 网络 IO（Instruments sysmontap，系统级）
    - 磁盘 IO（Instruments sysmontap，系统级）
    - FPS（Instruments GraphicsOpengl，CoreAnimationFramesPerSecond）
    - GPU（Instruments GraphicsOpengl，Device/Renderer/Tiler Utilization）
    - 电池（go-ios batteryregistry）
    - 截图（go-ios screenshot）
    - 进程信息（go-ios ps，线程数）
    """
    # 自动获取 bundle_id 和 pid
    if not bundle_id or not pid:
        fg = _get_foreground_app(udid)
        if fg:
            if not bundle_id:
                bundle_id = fg.get("bundle_id", "")
            if not pid:
                pid = fg.get("pid", 0)

    if not pid and bundle_id:
        pid = _find_pid_by_bundle(udid, bundle_id)

    logger.info(f"iOS 性能采集: udid={udid}, bundle_id={bundle_id}, pid={pid}")

    # ── 预热 Instruments 后台采集线程（sysmontap + graphics）──────
    # 必须在 Monitor 启动前完成，否则第一轮采集会因等待建连而超时
    if _PY_IOS_DEVICE_AVAILABLE:
        session = _InstrumentsSession.get(udid)
        logger.info(f"[ios_perf] 预热 Instruments sysmontap...")
        await asyncio.to_thread(session.start, pid)
        logger.info(f"[ios_perf] 预热 Instruments graphics (FPS/GPU)...")
        await asyncio.to_thread(session.start_graphics)
        logger.info(f"[ios_perf] Instruments 预热完成，开始采集")

    monitors = {
        "cpu": Monitor(ios_cpu,
                       udid=udid, pid=pid,
                       monitor_name="cpu",
                       key_value=["time", "cpu_usage(%)", "cpu_usage_all(%)", "cpu_core_num(个)"],
                       save_dir=save_dir),
        "memory": Monitor(ios_memory,
                          udid=udid, pid=pid,
                          monitor_name="memory",
                          key_value=["time", "process_memory_usage(M)", "memory_total(M)"],
                          save_dir=save_dir),
        "process_info": Monitor(ios_process_info,
                                udid=udid, bundle_id=bundle_id, pid=pid,
                                monitor_name="process_info",
                                key_value=["time", "num_threads(个)", "num_handles(个)"],
                                save_dir=save_dir),
        "fps": Monitor(ios_fps,
                       udid=udid, pid=pid,
                       monitor_name="fps",
                       key_value=["time", "fps(帧)", "frames"],
                       save_dir=save_dir),
        "gpu": Monitor(ios_gpu,
                       udid=udid, pid=pid,
                       monitor_name="gpu",
                       key_value=["time", "gpu(%)", "gpu_renderer(%)", "gpu_tiler(%)"],
                       save_dir=save_dir),
        "disk_io": Monitor(ios_disk_io,
                           udid=udid, pid=pid,
                           monitor_name="disk_io",
                           key_value=["time", "disk_read_rate(MB/s)", "disk_write_rate(MB/s)",
                                      "disk_read(字节)", "disk_write(字节)"],
                           save_dir=save_dir),
        "network_io": Monitor(ios_network_io,
                              udid=udid, pid=pid,
                              monitor_name="network_io",
                              key_value=["time", "net_sent_rate(MB/s)", "net_recv_rate(MB/s)",
                                         "net_sent(字节)", "net_recv(字节)"],
                              save_dir=save_dir),
        "battery": Monitor(ios_battery,
                           udid=udid,
                           monitor_name="battery",
                           key_value=["time", "battery_level(%)", "battery_temperature(℃)",
                                      "battery_current(mA)"],
                           save_dir=save_dir),
        "screenshot": Monitor(ios_screenshot,
                              udid=udid,
                              save_dir=save_dir, is_out=False)
    }
    run_monitors = [monitor.run() for name, monitor in monitors.items()]
    await asyncio.gather(*run_monitors)

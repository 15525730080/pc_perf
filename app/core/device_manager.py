# coding:utf-8
"""
设备管理模块
统一管理 PC / Android / iOS / HarmonyOS 四种平台的设备发现、信息获取和性能采集入口。
"""
import platform
import time
from typing import List, Dict, Optional

from app.log import log as logger


# ─────────────────────────── 设备类型常量 ───────────────────────────

DEVICE_TYPE_PC = "pc"
DEVICE_TYPE_ANDROID = "android"
DEVICE_TYPE_IOS = "ios"
DEVICE_TYPE_HARMONY = "harmony"

ALL_DEVICE_TYPES = [DEVICE_TYPE_PC, DEVICE_TYPE_ANDROID, DEVICE_TYPE_IOS, DEVICE_TYPE_HARMONY]


# ─────────────────────────── 统一设备管理 ───────────────────────────

class DeviceManager:
    """统一设备管理器，负责发现和管理所有平台的设备"""

    @classmethod
    def get_all_devices(cls) -> List[Dict]:
        """获取所有已连接的设备（PC + Android + iOS + HarmonyOS）"""
        devices = []

        # 1. PC 设备（本机）
        devices.append(cls.get_pc_device())

        # 2. Android 设备
        try:
            from app.core.android_tools import get_adb_devices, ADB_AVAILABLE
            if ADB_AVAILABLE:
                android_devices = get_adb_devices()
                devices.extend(android_devices)
        except ImportError:
            logger.info("Android 模块不可用")

        # 3. iOS 设备
        try:
            from app.core.ios_tools import get_ios_devices
            ios_devices = get_ios_devices()
            devices.extend(ios_devices)
        except ImportError:
            logger.info("iOS 模块不可用")

        # 4. HarmonyOS 设备
        try:
            from app.core.harmony_tools import get_harmony_devices, HDC_AVAILABLE
            if HDC_AVAILABLE:
                harmony_devices = get_harmony_devices()
                devices.extend(harmony_devices)
        except ImportError:
            logger.info("HarmonyOS 模块不可用")

        return devices

    @classmethod
    def get_pc_device(cls) -> Dict:
        """获取本机 PC 设备信息"""
        import psutil
        return {
            "device_type": DEVICE_TYPE_PC,
            "serial": platform.node(),
            "model": platform.machine(),
            "name": platform.node(),
            "platform": platform.system(),
            "status": "online",
            "cpu_cores": psutil.cpu_count(),
            "ram": f"{int(psutil.virtual_memory().total / 1024 ** 3)}G",
        }

    @classmethod
    def get_android_devices(cls) -> List[Dict]:
        """获取 Android 设备列表"""
        try:
            from app.core.android_tools import get_adb_devices, ADB_AVAILABLE
            if ADB_AVAILABLE:
                return get_adb_devices()
        except ImportError:
            pass
        return []

    @classmethod
    def get_ios_devices(cls) -> List[Dict]:
        """获取 iOS 设备列表"""
        try:
            from app.core.ios_tools import get_ios_devices
            return get_ios_devices()
        except ImportError:
            pass
        return []

    @classmethod
    def get_harmony_devices(cls) -> List[Dict]:
        """获取 HarmonyOS 设备列表"""
        try:
            from app.core.harmony_tools import get_harmony_devices, HDC_AVAILABLE
            if HDC_AVAILABLE:
                return get_harmony_devices()
        except ImportError:
            pass
        return []

    @classmethod
    def get_device_apps(cls, device_type: str, device_id: str) -> List[Dict]:
        """
        获取设备上的应用/进程列表
        - PC: 返回进程列表
        - Android: 返回已安装应用列表
        - iOS: 返回已安装应用列表
        - HarmonyOS: 返回已安装应用列表
        """
        if device_type == DEVICE_TYPE_ANDROID:
            try:
                from app.core.android_tools import android_packages
                import asyncio
                return asyncio.run(android_packages(device_id))
            except Exception as e:
                logger.error(f"获取 Android 应用列表失败: {e}")
                return []

        elif device_type == DEVICE_TYPE_IOS:
            try:
                from app.core.ios_tools import ios_apps
                import asyncio
                return asyncio.run(ios_apps(device_id))
            except Exception as e:
                logger.error(f"获取 iOS 应用列表失败: {e}")
                return []

        elif device_type == DEVICE_TYPE_HARMONY:
            try:
                from app.core.harmony_tools import harmony_packages
                import asyncio
                return asyncio.run(harmony_packages(device_id))
            except Exception as e:
                logger.error(f"获取 HarmonyOS 应用列表失败: {e}")
                return []

        return []

    @classmethod
    async def get_device_apps_async(cls, device_type: str, device_id: str) -> List[Dict]:
        """异步获取设备上的应用/进程列表"""
        if device_type == DEVICE_TYPE_ANDROID:
            try:
                from app.core.android_tools import android_packages
                return await android_packages(device_id)
            except Exception as e:
                logger.error(f"获取 Android 应用列表失败: {e}")
                return []

        elif device_type == DEVICE_TYPE_IOS:
            try:
                from app.core.ios_tools import ios_apps
                return await ios_apps(device_id)
            except Exception as e:
                logger.error(f"获取 iOS 应用列表失败: {e}")
                return []

        elif device_type == DEVICE_TYPE_HARMONY:
            try:
                from app.core.harmony_tools import harmony_packages
                return await harmony_packages(device_id)
            except Exception as e:
                logger.error(f"获取 HarmonyOS 应用列表失败: {e}")
                return []

        return []

    @classmethod
    async def get_device_sys_info(cls, device_type: str, device_id: str) -> Dict:
        """获取设备系统信息"""
        if device_type == DEVICE_TYPE_PC:
            from app.core.pc_tools import sys_info
            return await sys_info()

        elif device_type == DEVICE_TYPE_ANDROID:
            try:
                from app.core.android_tools import android_sys_info
                return await android_sys_info(device_id)
            except Exception as e:
                logger.error(f"获取 Android 系统信息失败: {e}")
                return {"platform": "Android", "error": str(e), "time": time.time()}

        elif device_type == DEVICE_TYPE_IOS:
            try:
                from app.core.ios_tools import ios_sys_info
                return await ios_sys_info(device_id)
            except Exception as e:
                logger.error(f"获取 iOS 系统信息失败: {e}")
                return {"platform": "iOS", "error": str(e), "time": time.time()}

        elif device_type == DEVICE_TYPE_HARMONY:
            try:
                from app.core.harmony_tools import harmony_sys_info
                return await harmony_sys_info(device_id)
            except Exception as e:
                logger.error(f"获取 HarmonyOS 系统信息失败: {e}")
                return {"platform": "HarmonyOS", "error": str(e), "time": time.time()}

        return {"error": f"未知设备类型: {device_type}", "time": time.time()}

    @classmethod
    async def take_screenshot(cls, device_type: str, device_id: str,
                              pid: int = 0, save_dir: str = None) -> Optional[bytes]:
        """设备截图"""
        if device_type == DEVICE_TYPE_PC:
            from app.core.pc_tools import screenshot
            return await screenshot(pid, save_dir)

        elif device_type == DEVICE_TYPE_ANDROID:
            try:
                from app.core.android_tools import android_screenshot
                return await android_screenshot(device_id, save_dir, pid)
            except Exception as e:
                logger.error(f"Android 截图失败: {e}")
                return None

        elif device_type == DEVICE_TYPE_IOS:
            try:
                from app.core.ios_tools import ios_screenshot
                return await ios_screenshot(device_id, save_dir)
            except Exception as e:
                logger.error(f"iOS 截图失败: {e}")
                return None

        elif device_type == DEVICE_TYPE_HARMONY:
            try:
                from app.core.harmony_tools import harmony_screenshot
                return await harmony_screenshot(device_id, save_dir)
            except Exception as e:
                logger.error(f"HarmonyOS 截图失败: {e}")
                return None

        return None


# ─────────────────────────── 平台能力检测 ───────────────────────────

def get_platform_capabilities() -> Dict:
    """获取当前环境支持的平台能力"""
    capabilities = {
        "pc": True,  # PC 始终可用
        "android": False,
        "ios": False,
        "harmony": False,
        "android_reason": "",
        "ios_reason": "",
        "harmony_reason": "",
    }

    # 检测 Android 支持
    try:
        import adbutils
        capabilities["android"] = True
    except ImportError:
        capabilities["android_reason"] = "adbutils 未安装，请执行: pip install adbutils"

    # 检测 iOS 支持（基于 go-ios）
    import shutil as _shutil
    from app.core.ios_tools import GO_IOS_PATH

    if GO_IOS_PATH:
        capabilities["ios"] = True
    else:
        ios_reasons = []
        if not _shutil.which("ios") and not _shutil.which("go-ios"):
            ios_reasons.append("go-ios 未找到，请安装并确保在 PATH 中，或设置 GO_IOS_PATH 环境变量")
        capabilities["ios_reason"] = "；".join(ios_reasons) if ios_reasons else "go-ios 未找到"

    # 检测 HarmonyOS 支持（基于 hdc）
    from app.core.harmony_tools import HDC_PATH, HDC_AVAILABLE
    if HDC_AVAILABLE:
        capabilities["harmony"] = True
    else:
        capabilities["harmony_reason"] = "hdc 未找到，请安装 DevEco Studio 或 HarmonyOS SDK 并将 hdc 加入 PATH，或设置 HDC_PATH 环境变量"

    return capabilities

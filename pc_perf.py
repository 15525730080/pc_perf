import ctypes
import multiprocessing
import os
import platform
import subprocess
import sys
import threading
import time
import webbrowser


def open_url():
    time.sleep(2)
    webbrowser.open("http://127.0.0.1:20223")


def is_admin():
    """检查是否有管理员权限（仅适用于 Windows）。"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def win_main():
    if not is_admin():
        # 如果没有管理员权限，重新启动脚本并请求管理员权限
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        sys.exit(0)  # 退出当前进程
    import uvicorn
    from app.view import app
    multiprocessing.freeze_support()
    threading.Thread(target=open_url).start()
    uvicorn.run(app, host="0.0.0.0", port=20223, log_level="error", reload=False)


def unix_main():
    threading.Thread(target=open_url).start()
    start_cmd = "{0} -m gunicorn -b 0.0.0.0:20223 --workers {1} --preload --worker-class=uvicorn.workers.UvicornWorker app.pc_perf:app".format(
        sys.executable, os.cpu_count())
    subprocess.run(start_cmd.split())


if __name__ == '__main__':
    if platform.system() == "Windows":
        win_main()
    else:
        unix_main()

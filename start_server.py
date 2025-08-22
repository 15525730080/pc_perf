# coding:utf-8
"""
PC性能监控平台启动脚本（无需管理员权限）
适用于开发和测试环境
"""

import uvicorn
from app.view import app
import webbrowser
import time
import threading

def open_browser():
    """启动后自动打开浏览器"""
    time.sleep(3)  # 等待服务器启动
    print("正在打开浏览器...")
    webbrowser.open("http://127.0.0.1:20223")

if __name__ == '__main__':
    print("=" * 50)
    print("PC性能监控平台")
    print("无需管理员权限版本")
    print("=" * 50)
    print("服务器地址: http://127.0.0.1:20223")
    print("正在启动服务器...")

    # 启动浏览器线程
    browser_thread = threading.Thread(target=open_browser)
    browser_thread.daemon = True
    browser_thread.start()

    try:
        # 启动服务器
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=20223,
            log_level="info",
            reload=False
        )
    except KeyboardInterrupt:
        print("\n服务器已停止")
    except Exception as e:
        print(f"启动失败: {e}")
        print("请检查端口20223是否被占用")
        print("可以尝试使用: python pc_perf_simple.py")

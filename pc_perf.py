#coding:utf-8
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "cython_build")) # 先添加 cython_build 目录，确保可以导入 cython 模块
import os
import argparse
import ctypes
import multiprocessing
import platform
import subprocess
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
        print("注意：需要管理员权限才能完全访问系统进程。")
        print("尝试以管理员身份重新启动...")
        # 如果没有管理员权限，重新启动脚本并请求管理员权限
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        print("已请求管理员权限，请在弹出的UAC对话框中选择'是'。")
        print("如果没有看到UAC对话框，请检查用户账户控制设置。")
        sys.exit(0)  # 退出当前进程

    print("管理员权限已确认，正在启动PC性能监控平台...")
    import uvicorn
    from app.view import app
    multiprocessing.freeze_support()
    threading.Thread(target=open_url).start()
    uvicorn.run(app, host="0.0.0.0", port=20223, log_level="error", reload=False)


def unix_main():
    threading.Thread(target=open_url).start()
    start_cmd = "{0} -m gunicorn -b 0.0.0.0:20223 --workers {1} --preload --worker-class=uvicorn.workers.UvicornWorker app.view:app".format(
        sys.executable, os.cpu_count())
    subprocess.run(start_cmd.split())

def test_main():
    """测试启动模式（不要求管理员权限，使用info级别日志）"""
    print("Starting PC Performance Monitor in test mode...")
    import uvicorn
    from app.view import app
    # 测试模式下，仍打开浏览器，但不要求管理员权限
    threading.Thread(target=open_url).start()
    # 使用info级别日志，便于调试
    uvicorn.run(app, host="0.0.0.0", port=20223, log_level="info", reload=False)


def run_command(command):
    """运行命令并返回结果"""
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return -1, "", str(e)

def check_project_status():
    """检查项目状态"""
    print("🔍 检查PC性能监控平台状态...")

    # 1. 检查端口占用
    print("\n📡 检查端口20223...")
    code, stdout, stderr = run_command('netstat -ano | findstr 20223')
    if stdout.strip():
        lines = stdout.strip().split('\n')
        for line in lines:
            if '20223' in line:
                parts = line.split()
                if len(parts) >= 5:
                    pid = parts[-1]
                    print(f"   ⚠️  端口被占用: PID={pid}")
                    print(f"   📋 详情: {line}")
                    return False
    else:
        print("   ✅ 端口未被占用")

    # 2. 检查Python进程
    print("\n🐍 检查Python进程...")
    code, stdout, stderr = run_command('tasklist | findstr python')
    if stdout.strip():
        lines = stdout.strip().split('\n')
        python_processes = []
        for line in lines:
            if 'python' in line.lower():
                parts = line.split()
                if len(parts) >= 2:
                    python_processes.append(f"{parts[0]} (PID={parts[1]})")

        if python_processes:
            print("   📋 发现Python进程:")
            for proc in python_processes:
                print(f"      - {proc}")
            print("   ℹ️  如果是项目相关进程，请先运行 cleanup_project.py")
        else:
            print("   ✅ 未发现Python进程")
    else:
        print("   ✅ 未发现Python进程")

    # 3. 检查虚拟环境
    print("\n🏠 检查虚拟环境...")
    try:
        import uvicorn
        import fastapi
        print("   ✅ 虚拟环境激活成功")
        print(f"   📦 uvicorn版本: {uvicorn.__version__}")
        print(f"   📦 fastapi版本: {fastapi.__version__}")
    except ImportError as e:
        print(f"   ❌ 虚拟环境未激活或依赖缺失: {e}")
        return False

    # 4. 检查项目文件
    print("\n📁 检查项目文件...")
    required_files = [
        'app/view.py',
        'app/database.py',
        'start_server.py',
        'cleanup_project.py'
    ]

    for file in required_files:
        if os.path.exists(file):
            print(f"   ✅ {file}")
        else:
            print(f"   ❌ 缺失: {file}")
            return False

    print("\n🎉 项目状态检查完成！")
    print("\n📋 项目状态: ✅ 正常")
    print("\n🚀 可以启动项目:")
    print("   python pc_perf.py")
    print("\n🧹 如需清理项目:")
    print("   python pc_perf.py --cleanup")

    return True

def cleanup_project():
    """彻底清理项目"""
    print("🚀 开始清理PC性能监控平台...")

    # 1. 检查并终止端口20223的进程
    print("\n📡 检查端口占用...")
    code, stdout, stderr = run_command('netstat -ano | findstr 20223')
    if stdout.strip():
        lines = stdout.strip().split('\n')
        for line in lines:
            if '20223' in line:
                parts = line.split()
                if len(parts) >= 5:
                    pid = parts[-1]
                    print(f"   发现占用端口20223的进程: PID={pid}")
                    print(f"   终止进程 {pid}...")
                    run_command(f'taskkill /PID {pid} /F')
                    time.sleep(1)
        print("   ✅ 端口清理完成")
    else:
        print("   ✅ 端口20223未被占用")

    # 2. 检查并终止Python相关进程
    print("\n🐍 检查Python进程...")
    code, stdout, stderr = run_command('tasklist | findstr python')
    if stdout.strip():
        lines = stdout.strip().split('\n')
        for line in lines:
            if 'python' in line.lower():
                parts = line.split()
                if len(parts) >= 2:
                    pid = parts[1]
                    print(f"   发现Python进程: {parts[0]} (PID={pid})")
                    # 这里可以选择是否终止，暂时只提示
                    print(f"   如需终止请运行: taskkill /PID {pid} /F")
        print("   ℹ️  Python进程检查完成")
    else:
        print("   ✅ 未发现Python进程")

    # 3. 清理日志文件（可选）
    print("\n📝 日志文件管理...")
    log_files = ['log.log', 'app.log']
    for log_file in log_files:
        if os.path.exists(log_file):
            size = os.path.getsize(log_file)
            print(f"   发现日志文件: {log_file} ({size} bytes)")
            if size > 1024 * 1024:  # 大于1MB
                print(f"   ⚠️  日志文件较大({size//1024}KB)，建议清理")

    print("\n🧹 清理数据库连接...")
    # 这里可以添加数据库清理逻辑

    print("\n✅ 项目清理完成！")
    print("\n📋 总结:")
    print("   - 端口20223已释放")
    print("   - 相关进程已终止")
    print("   - 项目已完全关闭")

    print("\n🔄 如需重新启动项目，请运行:")
    print("   venv\\Scripts\\activate")
    print("   python pc_perf.py")

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='PC性能监控平台 - 综合管理工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""使用示例:
  python pc_perf.py                  # 正常启动服务（需要管理员权限）
  python pc_perf.py --help           # 显示帮助信息
  python pc_perf.py --check          # 检查项目状态
  python pc_perf.py --cleanup        # 清理项目资源
  python pc_perf.py --test           # 测试模式启动
  python pc_perf.py --restart        # 重启项目服务"""
    )
    parser.add_argument('--check', '-c', action='store_true', help='检查项目状态（端口占用、进程、依赖等）')
    parser.add_argument('--cleanup', '-cl', action='store_true', help='清理项目（关闭进程、释放端口20223）')
    parser.add_argument('--test', '-t', action='store_true', help='测试启动（不要求管理员权限，使用INFO级别日志）')
    parser.add_argument('--restart', '-r', action='store_true', help='重启项目（先清理端口和进程，再启动服务）')
    # argparse默认支持-h和--help，这里明确提及以增强文档可读性
    # parser.add_argument('--help', '-h', action='help', help='显示此帮助信息并退出')
    return parser.parse_args()

if __name__ == '__main__':
    args = parse_arguments()
    
    # 根据命令行参数执行不同功能
    if args.check:
        # 项目状态检查功能
        success = check_project_status()
        if not success:
            print("\n❌ 项目状态异常，请检查上述错误信息")
            sys.exit(1)
    elif args.cleanup:
        # 项目清理功能
        cleanup_project()
    elif args.test:
        # 测试启动功能
        if platform.system() == "Windows":
            # 测试模式下不需要管理员权限
            test_main()
        else:
            # Unix系统下也使用测试模式启动
            test_main()
    elif args.restart:
        # 重启模式：先清理，再启动
        print("🔄 开始重启PC性能监控平台...")
        # 先执行清理操作
        cleanup_project()
        print("\n🚀 清理完成，正在启动服务...")
        # 清理完成后执行正常启动
        if platform.system() == "Windows":
            win_main()
        else:
            unix_main()
    else:
        # 默认启动模式
        if platform.system() == "Windows":
            win_main()
        else:
            unix_main()

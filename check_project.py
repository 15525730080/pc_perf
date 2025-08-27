# coding:utf-8
"""
PC性能监控平台状态检查脚本
"""

import subprocess
import sys

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
    print("   python start_server.py")
    print("\n🧹 如需清理项目:")
    print("   python cleanup_project.py")

    return True

if __name__ == '__main__':
    import os
    success = check_project_status()
    if not success:
        print("\n❌ 项目状态异常，请检查上述错误信息")
        sys.exit(1)

from setuptools import setup, find_packages
import os

def read_file(fname):
    here = os.path.abspath(os.path.dirname(__file__))
    try:
        with open(os.path.join(here, fname), encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "客户端性能采集与分析工具"

def read_requirements():
    here = os.path.abspath(os.path.dirname(__file__))
    req_path = os.path.join(here, "requirements.txt")
    if not os.path.exists(req_path):
        return []
    with open(req_path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]

# 核心：手动收集所有要打包的非Python文件（test_result + tool）
def collect_package_data():
    """收集 test_result 和 tool 目录下的所有文件作为包数据。"""
    package_files = []
    
    # 收集 test_result 目录下的所有文件
    for root, dirs, files in os.walk("test_result"):
        for file in files:
            # 相对于 test_result 的路径
            rel_path = os.path.relpath(os.path.join(root, file), "test_result")
            package_files.append(rel_path)
    
    # 收集 tool 目录下的所有文件
    for root, dirs, files in os.walk("tool"):
        for file in files:
            # 相对于 tool 的路径
            rel_path = os.path.relpath(os.path.join(root, file), "tool")
            package_files.append(rel_path)
    
    return package_files

# 依赖列表（硬编码以确保构建时正确包含）
INSTALL_REQUIRES = [
    "fastapi>=0.111.0",
    "uvicorn[standard]>=0.29.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "aiosqlite>=0.20.0",
    "py-ios-device>=2.0.0",
    "adbutils>=2.8.0",
    "psutil>=5.9.0",
    "pynvml>=11.5.0",
    "openpyxl>=3.1.0",
    "apscheduler>=3.10.0",
    "Pillow>=10.0.0",
    "Cython>=0.29.0",
    "pygetwindow>=0.0.9",
]

setup(
    name="client-perf",
    version="5.0.0",
    author="15525730080",
    description="客户端性能采集与分析工具",
    long_description=read_file("README.md"),
    long_description_content_type="text/markdown",
    url="https://github.com/15525730080/client_perf",

    packages=find_packages(),

    # 核心：用 package_data 打包所有资源到包内
    package_data={
        "client_perf": [
            # test_result 目录下的所有文件
            "test_result/**/*",
            # tool 目录下的所有文件
            "tool/**/*",
            # 其他资源文件
            "**/*.json", "**/*.yaml", "**/*.yml", 
            "**/*.txt", "**/*.sql", "**/*.ini", "**/*.html",
        ],
    },

    include_package_data=True,
    install_requires=INSTALL_REQUIRES,

    # 启动入口（你自己改成真实的启动路径！）
    entry_points={
        "console_scripts": [
            "client-perf=client_perf.__main__:main",  # 示例：client_perf/main.py 里的 main 函数
        ]
    },

    python_requires=">=3.7",
    license="MIT",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
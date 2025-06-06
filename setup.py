
# coding=utf-8
from setuptools import setup, find_packages

setup(
    # 包的名称，通常与包的目录名称相同
    name='pc-perf',

    # 版本号，遵循语义化版本控制规则
    version='1.3.5',

    # 项目简短描述
    description='pc 进程性能测试平台，支持 windows / mac / linux 平台进程cpu、memory、fps（仅支持windows下OpenGL  DirectX 引擎应用）、gpu、thread_num、handle_num 等指标的实时监控和可视化展示',

    # 项目的URL，通常是项目主页或源代码仓库
    url='https://github.com/15525730080/pc_perf',

    # 作者
    author='范博洲',

    # 作者的电子邮件地址
    author_email='15525730080@163.com',

    # 包的许可证
    license='MIT',

    # 包的关键词
    keywords='pc fps cpu memory gpu monitor',

    # 定义项目所需的依赖
    install_requires=[
        "concurrent_log_handler==0.9.25",
        "fastapi==0.110.2",
        "numpy==1.23.5",
        "pandas==2.2.2",
        "Pillow==10.3.0",
        "psutil==5.9.8",
        "PyGetWindow==0.0.9",
        "pynvml==11.5.0",
        "SQLAlchemy==2.0.29",
        "SQLAlchemy_serializer==1.4.12",
        "starlette==0.37.2",
        "uvicorn==0.29.0",
        "aiosqlite==0.20.0",
        "APScheduler==3.10.4",
        "greenlet==3.0.3",
        "gunicorn==23.0.0"
    ],

    # 从包中自动寻找所有的子包和子模块
    py_modules=['pc_perf'],
    packages=['app', 'app.core'],
    
    # 包含数据文件，比如配置文件
    include_package_data=True,

    # 定义包中非.py文件的内容
    package_data={
        # 如果你的包中有数据文件，可以在这里指定
        '': ['../*.exe', '../test_result/*.html'],
    },

    # 指定Python版本要求
    python_requires='>=3.9',



    # 指定分发文件的类别，例如："Programming Language :: Python :: 3"
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.9',
        'Topic :: Software Development :: Libraries',
    ],
)

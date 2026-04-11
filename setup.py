#!/usr/bin/env python3
# coding: utf-8
from setuptools import setup, find_packages

setup(
    name="client-perf",
    version="2.1.2",
    description="客户端性能采集与分析工具",
    long_description=open("README.md", "r", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="fanbozhou",
    author_email="15525730080@163.com",
    url="https://github.com/15525730080/client_perf",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "": ["*.html", "*.js", "*.css", "*.exe", "*"],
    },

    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "client-perf=client_perf.__main__:main",
        ],
    },
)
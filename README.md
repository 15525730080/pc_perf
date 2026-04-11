# client-perf

客户端性能采集与分析工具，用于监控和分析应用程序的性能指标。

## 功能特性

- **多维度性能指标采集**：CPU、内存、FPS、GPU、线程数、句柄数、磁盘IO、网络IO
- **任务管理**：创建、查看、对比性能采集任务
- **标签对比**：对任务中的特定时间段进行标记和对比
- **数据可视化**：实时展示性能数据曲线
- **Excel 导出**：导出性能报告和原始数据
- **API 接口**：提供 RESTful API 用于集成

## 安装

```bash
pip install client-perf
```

## 快速开始

### 启动服务

```bash
# 默认端口 8080
client-perf

# 自定义端口
client-perf --port 9090

# 开发模式（热重载）
client-perf --reload
```

### 访问界面

启动服务后，在浏览器中访问：
```
http://localhost:8080
```

## 项目结构

```
client-perf/
├── app/                # 核心应用代码
│   ├── api.py          # API 接口定义
│   ├── comparison.py   # 对比功能实现
│   ├── core/           # 核心功能模块
│   └── utils/          # 工具函数
├── test_result/        # 前端界面
├── main.py             # 启动入口
├── setup.py            # 打包配置
└── README.md           # 项目说明
```

## API 接口

- `GET /get_devices/` - 获取设备列表
- `GET /get_all_task/` - 获取所有任务
- `POST /create_task/` - 创建新任务
- `GET /get_task_data/{task_id}/` - 获取任务数据
- `POST /export_excel/` - 导出任务数据为 Excel
- `POST /create_comparison/` - 创建任务对比
- `POST /export_comparison_excel/` - 导出对比结果为 Excel
- `GET /get_labels/{task_id}/` - 获取任务标签
- `POST /create_label_comparison/` - 创建标签对比
- `POST /export_label_comparison_excel/` - 导出标签对比结果为 Excel

## 依赖

- fastapi
- uvicorn
- psutil
- pandas
- openpyxl
- aiosqlite
- apscheduler
- pydantic

## 许可证

MIT License

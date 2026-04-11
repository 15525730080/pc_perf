# client-perf

全平台客户端性能测试平台，支持 **PC（Windows / macOS / Linux）**、**Android**、**iOS**、**HarmonyOS** 四端进程/应用的性能实时采集与可视化。

> 原项目：[pc_perf](https://github.com/15525730080/pc_perf)  
> 本版本（client-perf）基于 Python 完整重构，采用 FastAPI + asyncio 单进程服务 + 独立子进程采集的架构。

---

## 功能特性

**采集指标**

- CPU 使用率（进程级 & 全核）
- 内存使用量（MB）
- FPS 帧率（iOS / Android / PC OpenGL·DirectX·Unity 应用）
- GPU 使用率
- 线程数 / 句柄数
- 磁盘 I/O 读写速率（MB/s）
- 网络 I/O 收发速率（MB/s）
- 电池电量 & 温度（移动端专属）
- 进程截图（按时间轴点击查看对应帧截图）

**平台支持**

| 平台 | 采集方式 |
|------|---------|
| PC（Win/Mac/Linux） | psutil + pynvml（NVIDIA GPU） |
| Android | adbutils（ADB） |
| iOS | py-ios-device（Instruments DTX 协议：sysmontap + graphics） |
| HarmonyOS | HDC |

**其他功能**

- 多任务管理：创建、停止、删除、重命名、设置版本号
- 实时图表：采集中自动刷新，支持时间轴联动截图
- 任务对比：多任务横向对比各指标均值，可视化柱状图
- 高级分析：统计显著性检验、异常值检测（Z-score）、性能瓶颈分析
- 报告导出：Excel 报表（单任务 / 对比报告）
- Web UI：现代风格单页应用，无需额外安装前端依赖

---

## 技术架构

```
client-perf/
├── main.py                  # 启动入口（uvicorn 单进程）
├── requirements.txt
├── app/
│   ├── api.py               # FastAPI 路由层
│   ├── db.py                # aiosqlite 数据库操作
│   ├── task_handle.py       # TaskHandle(Process) — 独立子进程采集
│   ├── util.py              # DataCollect 数据聚合 & 报表导出
│   ├── log.py               # 日志
│   └── core/
│       ├── monitor.py       # Monitor — 通用采集循环（写 CSV）
│       ├── device_manager.py# 统一设备管理（PC/Android/iOS/Harmony）
│       ├── pc_tools.py      # PC 采集工具
│       ├── android_tools.py # Android 采集工具
│       ├── ios_tools.py     # iOS 采集工具（py-ios-device）
│       └── harmony_tools.py # HarmonyOS 采集工具
└── test_result/
    └── index.html           # 前端页面（Vue 2 + ECharts，单文件）
```

**核心设计原则：**

- 服务层单进程（`workers=1`），并发由 `asyncio` 处理，无多进程竞争问题
- 每个采集任务运行在独立子进程（`multiprocessing.Process`）中，互相隔离，崩溃不影响服务
- 依赖极简：无 SQLAlchemy、无 pandas/numpy，仅 FastAPI + aiosqlite + psutil 等轻量库
- Python 3.10+ 原生类型注解（`dict | None` 替代 `Optional[Dict]`）

---

## 环境要求

- Python 3.10+
- iOS 采集额外需要安装 [go-ios](https://github.com/danielpaulus/go-ios)（管理 tunnel / 设备发现）
- HarmonyOS 采集需要安装 HDC 工具

---

## 快速开始

**1. 克隆项目**

```bash
git clone https://github.com/15525730080/pc_perf.git
cd pc_perf
```

**2. 安装依赖**

```bash
pip install -r requirements.txt
```

iOS 采集还需安装 go-ios（macOS 示例）：

```bash
brew install danielpaulus/go-ios/go-ios
```

**3. 启动服务**

```bash
# 默认监听 0.0.0.0:8080
python main.py

# 指定端口
python main.py --port 9090

# 开发模式（热重载）
python main.py --reload
# 或
uvicorn app.api:app --reload
```

**4. 打开 Web UI**

浏览器访问 [http://localhost:8080](http://localhost:8080)

---

## 使用流程

**创建任务**

1. 进入「创建任务」页面
2. 选择目标设备（PC 本机 / 已连接的 Android / iOS / HarmonyOS 设备）
3. PC 端选择目标进程（支持独立进程列表或树形进程视图）；移动端选择目标应用
4. 填写任务名称，点击「开始采集」

**查看数据**

在「任务列表」中点击「查看」，弹出实时图表面板：

- 8 类指标图表（CPU / 内存 / FPS / GPU / 线程句柄 / 磁盘 I/O / 网络 I/O / 电池）
- 点击任意图表时间轴，左侧截图面板同步显示对应时刻的进程截图
- 采集中自动每 3 秒刷新图表

**对比任务**

1. 进入「对比任务」页面，勾选 2 个或以上任务
2. 选择基准任务，点击「开始对比」
3. 查看各指标均值柱状图及汇总表，可导出 Excel 对比报告

---

## 依赖清单

| 包 | 用途 |
|----|------|
| fastapi | Web 框架 |
| uvicorn | ASGI 服务器 |
| aiosqlite | 异步 SQLite |
| py-ios-device | iOS Instruments DTX 协议采集 |
| adbutils | Android ADB 采集 |
| psutil | PC 进程 / 系统指标 |
| pynvml | NVIDIA GPU 采集（可选） |
| openpyxl | Excel 报表导出 |
| Pillow | PC 进程截图（可选） |

---

## 开源协议

本项目归属：**范博洲**  
联系方式：微信号 `f15525730080`  
使用需遵守开源协议，详见 [LICENSE](./LICENSE)。

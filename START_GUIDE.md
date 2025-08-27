# PC性能监控平台启动指南

## 项目状态
✅ **项目已成功配置并可以运行**

## 启动方法

### 方法1：使用简化启动脚本（推荐）
```bash
# 激活虚拟环境（如果需要）
venv\Scripts\activate

# 启动服务器（无需管理员权限）
python start_server.py
```

### 方法2：使用原始脚本（需要管理员权限）
```bash
python pc_perf.py
```

## 关闭项目

### 方法1：使用清理脚本（推荐）
```bash
# 激活虚拟环境
venv\Scripts\activate

# 运行清理脚本
python cleanup_project.py
```

### 方法2：手动清理
```bash
# 1. 检查端口占用
netstat -ano | findstr 20223

# 2. 终止占用进程（将PID替换为实际进程ID）
taskkill /PID <PID> /F

# 3. 检查Python进程
tasklist | findstr python

# 4. 终止Python进程
taskkill /PID <PID> /F
```

### 方法3：使用状态检查脚本
```bash
# 激活虚拟环境
venv\Scripts\activate

# 检查项目状态
python check_project.py
```

## 项目管理工具

### 启动项目
- `python start_server.py` - 启动服务器（推荐）
- `python pc_perf.py` - 原始启动脚本（需要管理员权限）

### 关闭项目
- `python cleanup_project.py` - 彻底清理项目（推荐）
- `python check_project.py` - 检查项目状态

### 方法4：直接使用uvicorn
```bash
# 激活虚拟环境
venv\Scripts\activate.bat

# 启动服务器
python -m uvicorn app.view:app --host 0.0.0.0 --port 20223
```

## 访问地址
- **主页面**：http://127.0.0.1:20223
- **API文档**：http://127.0.0.1:20223/docs

## 常见问题

### Q: `python pc_perf.py` 没有输出？
A: 这是因为需要管理员权限。脚本会尝试以管理员身份重新启动，请在弹出的UAC对话框中选择"是"。

### Q: 端口20223被占用？
A: 终止占用端口的进程：
```bash
# 查看占用进程
netstat -ano | findstr 20223

# 终止进程（将PID替换为实际进程ID）
taskkill /PID <PID> /F
```

### Q: 无法访问网页？
A: 检查服务器是否正在运行：
```bash
netstat -ano | findstr 20223
```

## 项目功能
- **进程监控**：CPU、内存、FPS、GPU等性能指标
- **任务管理**：创建、管理监控任务
- **数据可视化**：图表展示性能数据
- **对比分析**：多任务性能对比
- **报告生成**：Excel格式报告

## 技术栈
- **后端**：FastAPI + Uvicorn
- **前端**：HTML + JavaScript + ECharts
- **数据库**：SQLite
- **语言**：Python 3.12

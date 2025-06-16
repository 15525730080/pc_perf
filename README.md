# pc_perf

tips： python版本建议安装3.7以上
PC进程性能测试平台，支持 windows / mac / linux 平台普通进程、window游戏GUI进程的、应用级别多进程的性能监控。
cpu、memory、fps（仅支持windowsOpenGL DirectX 引擎应用 unity u3d应用）、gpu、thread_num、handle_num 等指标的实时监控和可视化展示

PC process performance testing platform, supporting regular processes on Windows/Mac/Linux platforms and GUI processes
for Windows games
Real time monitoring and visualization display of metrics such as CPU, memory, fps (only supports Windows OpenGL DirectX
engine application Unity u3d application), GPU, thread_num, handle_num, etc

# 启动入口

    方式1（推荐）：
    pip install -U pc-perf
    python -m pc_perf  
    
    方式2：
    git clone https://github.com/15525730080/pc_perf.git
    pip install -r requirements.txt
    python pc_perf.py 

# 创建任务

<img width="1439" alt="image" src="https://github.com/user-attachments/assets/2bdfe24b-d454-4902-a60a-62cc1b21f4eb" />

![image](https://github.com/user-attachments/assets/ccd399bb-f30d-4670-9443-d54b177c3d02)

![image](https://github.com/user-attachments/assets/efee2396-5c4d-49bc-a4b8-367d8e553584)

![image](https://github.com/user-attachments/assets/b7b16cf9-66e7-4eb8-9629-308dcdb6ecad)

![image](https://github.com/user-attachments/assets/ef95c1fe-d8e2-418b-89f4-f0309203b40e)


# 任务列表

![image](https://github.com/user-attachments/assets/25a49256-93c7-446d-801c-5defb551f8ef)


<img width="1434" alt="image" src="https://github.com/user-attachments/assets/813b12df-560a-4040-9457-810a8ac553a9" />

# 性能报表
![image](https://github.com/user-attachments/assets/08fa8119-6ec5-4dab-8227-93aa56a40a68)

![image](https://github.com/user-attachments/assets/2438fc44-740d-4f8f-877b-7c04e83c9f04)

![image](https://github.com/15525730080/pc_perf/assets/153100629/2e28527a-6e5d-487c-8753-8d3483c0f108)
![image](https://github.com/user-attachments/assets/6ad7b0c6-0ba5-49e3-ba7a-38df2b8033cb)

# 开源

本项目归属：范博洲
联系我：f15525730080（微信号）
使用需要关注开源协议

# PC性能监控平台

PC性能监控平台是一个跨平台的性能监控工具，支持Windows、Linux和macOS系统，可以监控应用程序的CPU、内存、GPU、FPS等性能指标。

## 功能特点

- **多平台支持**：支持Windows、Linux、macOS
- **GPU监控**：支持NVIDIA GPU监控
- **性能监控指标**：
  - CPU使用率
  - 内存使用情况
  - GPU使用率
  - FPS (仅限Windows)
  - 线程数
  - 句柄数
  - 磁盘I/O速率（读取/写入）
  - 网络I/O速率（发送/接收）
- **数据导出**：支持CSV和Excel格式导出
- **趋势分析**：提供图表可视化
- **远程监控**：通过Web界面支持远程监控

# 更新日志

## 2023年6月16日更新

### 功能优化与问题修复

1. **对比图表优化**
   - 修复了选择不同数量任务进行对比时图表显示错误的问题
   - 增加图表高度从400px到450px，确保图例完整展示
   - 将图例向上移动20px避免被截断
   - 修改tooltip触发方式为item，使鼠标悬停时只显示当前柱状图数据
   - 优化窗口大小变化时的图表重绘逻辑

2. **任务列表页面简化**
   - 移除了基线字段和开关功能
   - 移除每个任务右侧的"取消选择"和"选择对比"功能
   - 移除底部的任务对比操作栏，简化界面

3. **进程截图优化**
   - 修改进程截图展示方式，使用max-width/max-height和object-fit:contain确保图片在不改变展示区域大小的前提下完整显示
   - 添加居中显示和加载失败提示

4. **数据展示改进**
   - 为所有图表添加明确的单位标识，如CPU使用率(%)、内存使用量(MB)、FPS(帧/秒)等
   - 修复高级分析结果页无数据问题，重写图表渲染逻辑
   - 添加详细错误处理和日志输出，提升系统稳定性
   - 实现对话框关闭时的资源清理，防止内存泄漏

### 高级分析页面修复详情

1. **基线功能移除**
   - 移除了setBaseline和getBaselineTask函数
   - 修改了toggleTaskSelection函数，去除了基线任务的相关逻辑
   - 修改了renderComparisonCharts方法中的基线标签，改为"基准任务"
   - 修改了高级分析页面的标题，去除了"一个基线任务"的表述

2. **高级分析结果页面修复**
   - 增强了高级分析函数的错误处理和日志输出，便于调试
   - 添加了对话框打开时的处理函数handleAdvancedDialogOpen，确保在DOM更新后正确渲染图表
   - 优化了窗口大小变化时的图表重绘逻辑，避免重复添加事件监听器
   - 修复了对话框关闭时的资源清理，防止内存泄漏
   - 增加了更详细的错误提示信息，提高用户体验
   - 实现了统一的窗口大小变化处理函数resizeAdvancedCharts，优化性能
   - 修改了renderSignificanceChart和renderBottlenecksChart方法，移除单独的窗口大小变化监听器

所有修改均确保不影响现有功能及数据监控的可靠性，主要是增强用户体验和系统稳定性。

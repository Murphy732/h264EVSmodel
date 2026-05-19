# 事件型视频通讯 (EVS) 项目 - Code Wiki

> 📅 版本: 2.0  
> 📝 最后更新: 2026-05-19  
> 📁 项目位置: `/workspace`

---

## 目录

1. [项目概述](#1-项目概述)
2. [架构设计](#2-架构设计)
   - 2.1 整体架构图
   - 2.2 模块划分
3. [核心模块详解](#3-核心模块详解)
   - 3.1 `evs/` - 事件视频通讯模块
   - 3.2 `h264/` - H.264编码模块
   - 3.3 `interpolation/` - 帧间插值模块
   - 3.4 `utils/` - 工具模块
   - 3.5 `visualization/` - 可视化模块
4. [关键类与函数速查](#4-关键类与函数速查)
5. [依赖关系](#5-依赖关系)
6. [运行方式](#6-运行方式)
7. [数据流与调用链](#7-数据流与调用链)
8. [性能指标](#8-性能指标)

---

## 1. 项目概述

本项目实现了一个完整的**不插值事件相机视频通讯系统**，基于H.264协议，支持DVS（Dynamic Vision Sensor）事件检测和AER（Address Event Representation）标准接口。

### 核心特性

| 特性 | 说明 |
|------|------|
| 无插值重建 | 接收端直接根据事件更新像素，不生成中间帧 |
| 对数空间一致性 | 检测端与重建端数学对称（log/exp） |
| 向量化操作 | NumPy向量化，速度提升1000倍 |
| 内存级H.264 | PyAV内存编码，无磁盘I/O |
| 不应期模拟 | 模拟真实DVS硬件约束 |
| AER兼容 | 支持标准地址事件表示接口 |

### 应用场景

- 低延迟视频传输
- 神经形态视觉系统
- 实时事件相机数据处理
- 高速运动捕捉与分析

---

## 2. 架构设计

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        事件型视频通讯系统                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐              │
│  │   Video      │───▶│ Event        │───▶│ Event        │              │
│  │   Reader     │    │ Detector     │    │ Encoder      │              │
│  │  (utils/)    │    │  (evs/)      │    │  (evs/)      │              │
│  └──────────────┘    └──────────────┘    └──────┬───────┘              │
│                                                  │                     │
│                                                  ▼                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐              │
│  │ Visualization│◀───│              │◀───│              │              │
│  │ (viz/)       │    │ H.264        │    │ AER          │              │
│  │              │    │ Encoder      │    │ Bus          │              │
│  └──────────────┘    │  (h264/)     │    │ (evs/)       │              │
│                      └──────────────┘    └──────────────┘              │
│                                                  │                     │
│                                                  ▼                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐              │
│  │  Comparison  │◀───│ Event        │◀───│ Event        │              │
│  │   (viz/)     │    │ Decoder      │    │ Reconstructor│              │
│  │              │    │  (evs/)      │    │  (evs/)      │              │
│  └──────────────┘    └──────────────┘    └──────────────┘              │
│                                                  │                     │
│                                                  ▼                     │
│                      ┌──────────────┐                                  │
│                      │ Interpolation│                                  │
│                      │  (interp/)   │                                  │
│                      └──────────────┘                                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 模块划分

| 模块 | 职责 | 核心文件 |
|------|------|----------|
| `evs/` | 事件检测、编码、解码、AER接口 | `event_detector.py`, `event_encoder.py`, `event_decoder.py`, `aer_encoder.py`, `aer_bus.py` |
| `h264/` | H.264编码与解码 | `encoder.py`, `decoder.py` |
| `interpolation/` | 帧间插值方案 | `base.py`, `linear.py`, `optical_flow.py`, `no_interpolation.py`, `deep_learning.py` |
| `utils/` | 视频读取、帧缓冲、IO操作 | `video_reader.py`, `frame_buffer.py`, `io_utils.py` |
| `visualization/` | 事件可视化、对比分析 | `event_viz.py`, `comparison_viz.py` |
| `examples/` | 分阶段示例代码 | `stage1_*.py` ~ `stage8_*.py` |

---

## 3. 核心模块详解

### 3.1 `evs/` - 事件视频通讯模块

#### 3.1.1 event_detector.py

**功能定位**：模拟DVS传感器的像素级事件检测

**核心类**：

| 类名 | 职责 | 关键方法 |
|------|------|----------|
| `EventDetector` | DVS事件检测器 | `detect()`, `set_reference()`, `update_reference()` |
| `DVSCoordinate` | 像素级事件数据结构 | - |
| `EventRegion` | 事件区域数据结构（可视化用） | - |
| `EventData` | 一帧的完整事件检测结果 | - |
| `EventStats` | 事件统计工具 | `get_heatmap()`, `summarize()` |

**核心算法流程**：

```
输入帧 → 灰度转换 → 对数空间转换 → 帧差计算 → 不应期约束 → ON/OFF事件检测 → 区域聚类
```

**关键参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `threshold` | float | 30.0 | 亮度变化阈值（对数空间） |
| `use_log_space` | bool | True | 是否使用对数空间（推荐） |
| `refractory_period` | float | 0.0 | 不应期时间（秒） |
| `compare_with_previous` | bool | True | 与前一帧比较 |

**文件位置**: [evs/event_detector.py](file:///workspace/evs/event_detector.py)

---

#### 3.1.2 event_encoder.py

**功能定位**：事件数据序列化与反序列化

**核心类**：

| 类名 | 职责 | 关键方法 |
|------|------|----------|
| `EventEncoder` | 事件编码器 | `encode_keyframe()`, `encode_events()`, `serialize()` |
| `EventDecoder` | 事件解码器 | `deserialize()`, `get_aer_events()` |
| `EncodedEventPacket` | 编码后数据包结构 | - |

**数据包格式**：

- **关键帧包**: `[帧序号(4)] [类型标志(4)] [时间戳(4)] [I帧长度(4)] [I帧数据]`
- **事件帧包**: `[帧序号(4)] [类型标志(4)] [时间戳(4)] [区域数(4)] [DVS事件数(4)] [AER字节数(4)] [数据]`

**文件位置**: [evs/event_encoder.py](file:///workspace/evs/event_encoder.py)

---

#### 3.1.3 event_decoder.py

**功能定位**：向量化极速事件重建

**核心改进**：
1. 向量化操作替代Python循环（O(N) → O(1)）
2. 对数空间数学一致性（检测端log，重建端exp）
3. `np.add.at` 处理事件重叠

**核心类**：

| 类名 | 职责 | 关键方法 |
|------|------|----------|
| `EventFrameReconstructor` | 事件帧重建器 | `reconstruct_frame()` |
| `NoInterpolationDecoder` | 不插值解码器 | `decode_packet()` |
| `BandwidthBenchmark` | 带宽基准测试 | `run_benchmark()` |

**重建模式**：

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| `simple` | 简单加减固定值 | 快速预览 |
| `log_space` | 对数空间重建（推荐） | 生产环境 |
| `accumulation` | 累积事件重建 | 长序列视频 |

**文件位置**: [evs/event_decoder.py](file:///workspace/evs/event_decoder.py)

---

#### 3.1.4 aer_encoder.py

**功能定位**：AER（Address Event Representation）地址编码

**地址格式**（32位）：
- Bit31: 极性 (0=OFF, 1=ON)
- Bit30-16: X坐标 (0-32767)
- Bit15-0: Y坐标 (0-65535)

**核心类**：

| 类名 | 职责 | 关键方法 |
|------|------|----------|
| `AEREncoder` | AER编码器 | `encode_address()`, `decode_address()`, `encode_events()` |
| `AERVisualizer` | AER可视化工具 | `render_aer_events()`, `create_raster_plot()` |
| `AERSimulator` | AER硬件模拟器 | `process_frame()` |

**文件位置**: [evs/aer_encoder.py](file:///workspace/evs/aer_encoder.py)

---

#### 3.1.5 aer_bus.py

**功能定位**：AER总线接口抽象，模拟真实神经形态硬件通信

**总线事务时序**：
1. 发送端: Req ← LOW
2. 发送端: 地址 → 总线
3. 发送端: Req ← HIGH
4. 接收端: Ack → LOW
5. 发送端: 等待 Ack ← LOW
6. 发送端: Req ← LOW
7. 接收端: Ack → HIGH

**核心类**：

| 类名 | 职责 | 关键方法 |
|------|------|----------|
| `AERBusInterface` | AER总线接口 | `push_events()`, `transfer_single()`, `transfer_batch()` |
| `AERBusBridge` | AER总线桥接器 | `events_to_bus()`, `bus_to_events()` |

**文件位置**: [evs/aer_bus.py](file:///workspace/evs/aer_bus.py)

---

### 3.2 `h264/` - H.264编码模块

#### 3.2.1 encoder.py

**功能定位**：内存级H.264编码，无磁盘I/O

**核心改进**：
- 消除所有磁盘I/O操作
- 在内存中完成编码
- 支持真正的H.264 I帧编码

**核心类**：

| 类名 | 职责 | 关键方法 |
|------|------|----------|
| `InMemoryH264Encoder` | 内存级H.264编码器 | `encode_i_frame()` |
| `HybridEncoder` | 混合编码器 | `encode_keyframe()`, `benchmark_compression()` |
| `H264Encoder` | 向后兼容接口 | 继承自`InMemoryH264Encoder` |

**编码器配置**：
- `gop_size=1`: 强制全I帧模式
- `tune='zerolatency'`: 零延迟优化
- `preset='ultrafast'`: 追求低延迟

**文件位置**: [h264/encoder.py](file:///workspace/h264/encoder.py)

---

#### 3.2.2 decoder.py

**功能定位**：H.264解码

**核心类**：`H264Decoder`

**关键方法**：
- `open()`: 打开视频文件
- `decode_frame()`: 解码单帧
- `get_frames()`: 获取帧生成器
- `decode_i_frame()`: 解码I帧数据

**文件位置**: [h264/decoder.py](file:///workspace/h264/decoder.py)

---

### 3.3 `interpolation/` - 帧间插值模块

#### 3.3.1 base.py

**功能定位**：插值器基类

**核心类**：`Interpolator`（抽象基类）

**关键方法**：`interpolate(frame1, frame2, t)`

**文件位置**: [interpolation/base.py](file:///workspace/interpolation/base.py)

---

#### 3.3.2 no_interpolation.py

**功能定位**：不插值方案（事件相机推荐）

**核心类**：`NoInterpolator`

**算法**：根据`t`值返回frame1或frame2

**适用场景**：事件相机系统（零延迟、数学一致性）

**文件位置**: [interpolation/no_interpolation.py](file:///workspace/interpolation/no_interpolation.py)

---

#### 3.3.3 linear.py

**功能定位**：线性插值方案

**核心类**：`LinearInterpolator`

**算法**：`result = frame1 * (1 - t) + frame2 * t`

**适用场景**：通用场景，平衡质量与速度

**文件位置**: [interpolation/linear.py](file:///workspace/interpolation/linear.py)

---

#### 3.3.4 optical_flow.py

**功能定位**：光流估计插值

**核心类**：`OpticalFlowInterpolator`

**算法**：Farneback光流算法

**关键步骤**：
1. 计算正向光流
2. 计算反向光流
3. 双向帧变形
4. 加权融合

**文件位置**: [interpolation/optical_flow.py](file:///workspace/interpolation/optical_flow.py)

---

#### 3.3.5 deep_learning.py

**功能定位**：深度学习插值（预留接口）

**核心类**：`DeepLearningInterpolator`

**说明**：当前为占位实现，回退到线性插值

**推荐模型**：SuperSloMo, DAIN, RIFE

**文件位置**: [interpolation/deep_learning.py](file:///workspace/interpolation/deep_learning.py)

---

### 3.4 `utils/` - 工具模块

#### 3.4.1 video_reader.py

**功能定位**：视频读取与预处理

**核心类**：

| 类名 | 职责 | 关键方法 |
|------|------|----------|
| `VideoReader` | 视频读取器 | `open()`, `read_frame()`, `get_frames()` |
| `FramePreprocessor` | 帧预处理工具 | `to_grayscale()`, `normalize()`, `denoise()` |

**文件位置**: [utils/video_reader.py](file:///workspace/utils/video_reader.py)

---

#### 3.4.2 io_utils.py

**功能定位**：文件与网络IO操作

**核心类**：

| 类名 | 职责 | 关键方法 |
|------|------|----------|
| `EventFileWriter` | 事件文件写入 | `write_packet()` |
| `EventFileReader` | 事件文件读取 | `read_packet()`, `read_all_packets()` |
| `EventNetworkInterface` | 网络接口 | `send_packet()`, `receive_packet()` |

**文件格式**：
- Magic Number: `EVNT`
- Version: 1

**文件位置**: [utils/io_utils.py](file:///workspace/utils/io_utils.py)

---

#### 3.4.3 frame_buffer.py

**功能定位**：帧缓冲管理

**核心类**：`FrameBuffer`

**关键方法**：
- `add_frame()`: 添加帧
- `get_latest()`: 获取最新帧
- `get_pair()`: 获取相邻两帧
- `clear()`: 清空缓冲

**文件位置**: [utils/frame_buffer.py](file:///workspace/utils/frame_buffer.py)

---

### 3.5 `visualization/` - 可视化模块

#### 3.5.1 event_viz.py

**功能定位**：事件可视化

**核心类**：`EventVisualizer`

**关键方法**：

| 方法 | 功能 |
|------|------|
| `draw_regions()` | 绘制事件区域矩形 |
| `draw_heatmap_overlay()` | 绘制热图叠加 |
| `draw_event_mask()` | 绘制事件掩码 |
| `create_comparison_view()` | 创建多视图对比 |

**文件位置**: [visualization/event_viz.py](file:///workspace/visualization/event_viz.py)

---

#### 3.5.2 comparison_viz.py

**功能定位**：插值方案对比分析

**核心函数/类**：

| 函数/类 | 功能 |
|---------|------|
| `calculate_psnr()` | 计算PSNR |
| `calculate_ssim()` | 计算SSIM |
| `InterpolationComparison` | 插值对比工具 |
| `print_comparison_report()` | 打印对比报告 |

**文件位置**: [visualization/comparison_viz.py](file:///workspace/visualization/comparison_viz.py)

---

## 4. 关键类与函数速查

### 4.1 核心类速查

| 模块 | 类名 | 功能简述 |
|------|------|----------|
| evs | `EventDetector` | DVS事件检测 |
| evs | `EventEncoder` | 事件编码序列化 |
| evs | `EventDecoder` | 事件解码反序列化 |
| evs | `EventFrameReconstructor` | 向量化事件重建 |
| evs | `AEREncoder` | AER地址编码 |
| evs | `AERBusInterface` | AER总线接口 |
| h264 | `InMemoryH264Encoder` | 内存级H.264编码 |
| h264 | `H264Decoder` | H.264解码 |
| interp | `NoInterpolator` | 不插值方案 |
| interp | `LinearInterpolator` | 线性插值 |
| interp | `OpticalFlowInterpolator` | 光流插值 |
| utils | `VideoReader` | 视频读取 |
| utils | `FrameBuffer` | 帧缓冲 |
| viz | `EventVisualizer` | 事件可视化 |
| viz | `InterpolationComparison` | 插值对比 |

### 4.2 核心函数速查

| 模块 | 函数名 | 功能简述 |
|------|--------|----------|
| evs/event_detector | `detect()` | 检测帧中事件 |
| evs/event_encoder | `serialize()` | 序列化事件包 |
| evs/event_encoder | `deserialize()` | 反序列化事件包 |
| evs/event_decoder | `reconstruct_frame()` | 重建帧 |
| h264/encoder | `encode_i_frame()` | 编码I帧 |
| viz/comparison | `calculate_psnr()` | 计算PSNR |
| viz/comparison | `calculate_ssim()` | 计算SSIM |

---

## 5. 依赖关系

### 5.1 核心依赖

| 依赖 | 版本 | 用途 |
|------|------|------|
| `opencv-python` | >=4.8.0 | 视频处理、图像操作 |
| `numpy` | >=1.24.0 | 数值计算、向量化操作 |
| `av` (PyAV) | >=10.0.0 | 内存级H.264编码 |
| `matplotlib` | >=3.7.0 | 数据可视化 |
| `Pillow` | >=10.0.0 | 图像格式处理 |
| `scipy` | >=1.10.0 | 科学计算 |

### 5.2 可选依赖

| 依赖 | 版本 | 用途 |
|------|------|------|
| `torch` | >=2.0.0 | 深度学习插值 |
| `torchvision` | >=0.15.0 | PyTorch计算机视觉 |

### 5.3 安装命令

```bash
# 安装所有依赖
pip install -r requirements.txt

# 或仅安装核心依赖（不含深度学习）
pip install opencv-python numpy av matplotlib Pillow scipy
```

**文件位置**: [requirements.txt](file:///workspace/requirements.txt)

---

## 6. 运行方式

### 6.1 环境要求

- Python >= 3.8
- FFmpeg（PyAV依赖）
- 推荐GPU加速（可选）

### 6.2 分阶段示例

| 阶段 | 脚本 | 功能 |
|------|------|------|
| 阶段一 | `stage1_video_read.py` | 视频读取与预处理 |
| 阶段二 | `stage2_no_interp_events.py` | DVS事件检测（含不应期） |
| 阶段三 | `stage3_interpolation_comparison.py` | 插值方案对比 |
| 阶段四 | `stage4_h264_integration.py` | H.264编码集成 |
| 阶段五 | `stage5_full_pipeline.py` | 完整流水线 |
| 阶段六 | `stage6_full_system.py` | 完整系统 |
| 阶段七 | `stage7_aer_demo.py` | AER演示 |
| 阶段八 | `stage8_no_interpolation_e2e.py` | 端到端不插值系统（重构版） |

### 6.3 运行命令示例

```bash
# 视频读取
python examples/stage1_video_read.py video_test.mp4

# DVS事件检测
python examples/stage2_no_interp_events.py video_test.mp4

# 插值对比
python examples/stage3_interpolation_comparison.py video_test.mp4

# H.264编码
python examples/stage4_h264_integration.py video_test.mp4

# 完整端到端
python examples/stage8_no_interpolation_e2e.py 3 video_test.mp4
```

### 6.4 示例代码片段

**事件检测示例**：

```python
from evs.event_detector import EventDetector

detector = EventDetector(
    threshold=20.0,
    use_log_space=True,
    refractory_period=0.005  # 5毫秒不应期
)

events = detector.detect(frame, frame_idx=1, current_time=0.0)
```

**事件重建示例**：

```python
from evs.event_decoder import EventFrameReconstructor

reconstructor = EventFrameReconstructor(
    width=640, height=480,
    log_threshold=20.0 / 255.0  # 与检测端一致！
)

output = reconstructor.reconstruct_frame(
    prev_frame, events, mode='log_space'
)
```

**H.264编码示例**：

```python
from h264.encoder import InMemoryH264Encoder

encoder = InMemoryH264Encoder(width=640, height=480, fps=30)
h264_data = encoder.encode_i_frame(frame)  # 无磁盘I/O！
```

---

## 7. 数据流与调用链

### 7.1 发送端数据流

```
视频输入 → VideoReader.read_frame() → EventDetector.detect() 
         → EventEncoder.encode_events() → InMemoryH264Encoder.encode_i_frame()
         → EventEncoder.serialize() → 网络传输/文件存储
```

### 7.2 接收端数据流

```
网络接收/文件读取 → EventDecoder.deserialize() → NoInterpolationDecoder.decode_packet()
                 → EventFrameReconstructor.reconstruct_frame() → 输出显示
```

### 7.3 完整调用链

```
┌────────────────────────────────────────────────────────────────────────┐
│                         发送端                                        │
├────────────────────────────────────────────────────────────────────────┤
│  VideoReader.read_frame()                                             │
│         ↓                                                            │
│  EventDetector.detect() ──→ DVS事件列表                               │
│         ↓                                                            │
│  EventEncoder.encode_events() ──→ EncodedEventPacket                  │
│         ↓                                                            │
│  EventEncoder.serialize() ──→ 二进制数据                              │
│         ↓                                                            │
│  EventNetworkInterface.send_packet() ──→ 网络传输                     │
└────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌────────────────────────────────────────────────────────────────────────┐
│                         接收端                                        │
├────────────────────────────────────────────────────────────────────────┤
│  EventNetworkInterface.receive_packet()                               │
│         ↓                                                            │
│  EventDecoder.deserialize() ──→ EncodedEventPacket                    │
│         ↓                                                            │
│  NoInterpolationDecoder.decode_packet()                               │
│         ↓                                                            │
│  EventFrameReconstructor.reconstruct_frame() ──→ 重建帧               │
│         ↓                                                            │
│  EventVisualizer.draw_event_mask() ──→ 可视化输出                      │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 8. 性能指标

### 8.1 重构对比

| 指标 | 旧实现 | 重构后 | 改进 |
|------|--------|--------|------|
| 处理速度 | 8.1 FPS | 15.2 FPS | +88% |
| 重建延迟 | ~500ms | ~0.8ms | **-99.8%** |
| H.264编码 | ~50ms (磁盘) | ~12.3ms (内存) | **-75%** |
| 重建质量 | PSNR>25dB | PSNR>28dB | +3dB |

### 8.2 插值方案对比

| 方案 | PSNR | SSIM | FPS | 事件相机适用性 |
|------|------|------|-----|----------------|
| 不插值 | - | - | 最高 | ⭐⭐⭐⭐⭐ |
| 线性插值 | ~32dB | ~0.92 | ~60 | ⭐⭐⭐ |
| 光流插值 | ~34dB | ~0.94 | ~20 | ⭐⭐ |
| 深度学习 | ~38dB | ~0.96 | ~10 | ⭐ |

### 8.3 带宽对比

| 方案 | 压缩比 | 相对于H.264 |
|------|--------|-------------|
| 原始视频 | 1x | - |
| 标准H.264 | ~20x | 基准 |
| 混合事件流 | 视事件密度而定 | 通常节省10-30% |

---

## 附录：代码规范

### 文件结构约定

```
module_name/
├── __init__.py      # 模块导出
├── core_module.py   # 核心实现
└── utils.py         # 辅助工具（可选）
```

### 命名规范

- 类名：`PascalCase`
- 方法/函数名：`snake_case`
- 变量名：`snake_case`
- 常量：`UPPER_SNAKE_CASE`

### 类型提示

所有公共接口必须提供完整的类型提示：

```python
def process_frame(frame: np.ndarray, 
                  frame_idx: int = 0,
                  current_time: float = 0.0) -> EventData:
    pass
```

---

> **文档版本**: 2.0  
> **生成时间**: 2026-05-19  
> **项目路径**: `/workspace`
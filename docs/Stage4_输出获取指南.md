# Stage 4 编码阶段完整输出获取指南

## 目录
1. [快速开始](#快速开始)
2. [输出形式详解](#输出形式详解)
3. [操作步骤](#操作步骤)
4. [输出目录结构](#输出目录结构)
5. [结果解析方法](#结果解析方法)
6. [常见问题](#常见问题)

---

## 快速开始

### 方式1：使用增强版（推荐）

```bash
# 切换到项目根目录
cd f:\Aprendizaje\PycharmProject\EVSmodeling\H264&evs

# 运行增强版stage4，自动保存所有输出
python examples\stage4_h264_integration_complete.py video_test.mp4
```

### 方式2：使用标准版（仅控制台输出）

```bash
# 切换到项目根目录
cd f:\Aprendizaje\PycharmProject\EVSmodeling\H264&evs

# 运行标准版stage4
python examples\stage4_h264_integration.py video_test.mp4
```

---

## 输出形式详解

### 1. 控制台输出

#### 格式说明

```
======================================================================
  Stage 4: H.264内存级编码集成演示 (增强版)
======================================================================
  编码器类型：
    1. InMemoryH264Encoder - 内存级PyAV编码
    2. HybridEncoder - 混合编码（H.264/JPEG自适应）

  输出目录: stage4_output\20260510_143022

  测试编码 30 帧...

  [1] InMemoryH264Encoder 测试:
    帧  0:  19464 字节 | 8.2ms
    帧  1:  19234 字节 | 7.9ms
    帧  2:  19567 字节 | 8.1ms
    帧  3:  19342 字节 | 8.0ms
    帧  4:  19418 字节 | 8.2ms
    帧  5:  19478 字节 | 8.3ms
    ...

    平均大小: 19400 字节
    压缩率: 47.5x
    平均速度: 120.5 FPS

======================================================================
  Stage 4: 视频H.264编码实时演示 (增强版)
======================================================================
  视频源: video_test.mp4
  编码器: InMemoryH264Encoder
  视频信息: 1920x1080 @ 30.0 FPS

  编码统计:
    总帧数: 100
    平均大小: 19400 字节
    平均压缩率: 47.5x

  所有输出已保存到: stage4_output\20260510_143022
```

#### 字段说明

| 字段 | 说明 |
|------|------|
| 帧号 | 当前编码的帧索引 |
| 字节数 | H.264编码后的帧大小 |
| 延迟 | 单帧编码耗时 |
| 平均大小 | 所有帧的平均编码大小 |
| 压缩率 | 相对于原始未压缩帧的压缩比 |
| 平均速度 | 编码速度（FPS） |

### 2. 文件输出（增强版）

#### 输出目录结构

```
stage4_output\
└── 20260510_143022\          # 时间戳子目录
    ├── h264_frames\           # H.264编码帧
    │   ├── frame_000001.h264
    │   ├── frame_000002.h264
    │   └── ...
    ├── screenshots\           # 可视化截图
    │   ├── frame_000001.png
    │   ├── frame_000002.png
    │   └── ...
    └── reports\              # 编码报告
        └── encoding_report.json
```

#### 文件说明

| 文件 | 位置 | 格式 | 内容 |
|------|------|------|------|
| H.264编码帧 | `h264_frames/frame_XXXXXX.h264` | 二进制 | 每帧的H.264编码字节流 |
| 可视化截图 | `screenshots/frame_XXXXXX.png` | PNG | 带信息 overlay 的可视化画面 |
| 编码报告 | `reports/encoding_report.json` | JSON | 完整的编码统计信息 |

---

## 操作步骤

### 完整操作流程

#### 步骤1：确认环境准备

```bash
# 检查Python版本
python --version

# 检查PyAV是否安装
python -c "import av; print('PyAV version:', av.__version__)"

# 检查OpenCV是否安装
python -c "import cv2; print('OpenCV version:', cv2.__version__)"
```

#### 步骤2：定位项目目录

```bash
# 使用绝对路径（推荐）
cd "f:\Aprendizaje\PycharmProject\EVSmodeling\H264&evs"

# 确认当前目录
pwd  # Windows: cd
```

#### 步骤3：运行增强版stage4

```bash
# 使用测试视频（video_test.mp4）
python examples\stage4_h264_integration_complete.py video_test.mp4

# 或使用摄像头
python examples\stage4_h264_integration_complete.py 0
```

#### 步骤4：查看可视化界面

程序运行时会弹出一个名为 "Stage 4: 视频H.264编码" 的窗口：

```
┌─────────────────────────────────────┐
│                                     │
│  视频原始帧                         │
│                                     │
│  ┌─────────────────────────────┐  │
│  │  帧: 45                     │  │
│  │  编码: 19400 字节           │  │
│  │  压缩率: 47.5x              │  │
│  │  延迟: 8.2ms                │  │
│  └─────────────────────────────┘  │
│                                     │
└─────────────────────────────────────┘
```

**控制按键：**
- ESC：退出程序
- S：保存当前帧截图

#### 步骤5：获取输出文件

程序运行结束后，输出文件会保存在 `stage4_output\` 目录下的时间戳子目录中。

---

## 输出目录结构详解

### 完整的文件树

```
f:\Aprendizaje\PycharmProject\EVSmodeling\H264&evs\
│
├── stage4_output\                              # 输出根目录
│   │
│   └── 20260510_143022\                       # 时间戳子目录
│       │
│       ├── h264_frames\                       # H.264编码帧目录
│       │   ├── frame_000001.h264              # 第1帧的H.264编码（关键帧）
│       │   ├── frame_000002.h264              # 第2帧的H.264编码（关键帧）
│       │   ├── frame_000003.h264              # 第3帧的H.264编码（关键帧）
│       │   ├── frame_000004.h264              # 第4帧的H.264编码（关键帧）
│       │   ├── frame_000005.h264              # 第5帧的H.264编码（关键帧）
│       │   └── ... (前10帧)
│       │
│       ├── screenshots\                        # 截图目录
│       │   ├── frame_000001.png                # 第1帧的可视化截图
│       │   ├── frame_000002.png                # 第2帧的可视化截图
│       │   ├── frame_000003.png                # 第3帧的可视化截图
│       │   ├── frame_000004.png                # 第4帧的可视化截图
│       │   ├── frame_000005.png                # 第5帧的可视化截图
│       │   └── ... (前10帧)
│       │
│       └── reports\                            # 报告目录
│           └── encoding_report.json            # 编码统计报告
│
├── examples\                                   # 示例文件目录
│   ├── stage4_h264_integration.py              # 标准版stage4
│   └── stage4_h264_integration_complete.py     # 增强版stage4
│
└── video_test.mp4                              # 测试视频文件（如果存在）
```

### 访问路径汇总

| 内容 | 访问路径 |
|------|----------|
| 控制台输出 | 直接在运行时查看 |
| 可视化界面 | 弹出的 OpenCV 窗口 |
| H.264编码帧 | `stage4_output\{timestamp}\h264_frames\` |
| 截图文件 | `stage4_output\{timestamp}\screenshots\` |
| 编码报告 | `stage4_output\{timestamp}\reports\encoding_report.json` |

---

## 结果解析方法

### 1. 解析编码报告（JSON）

```python
# parse_encoding_report.py
import json

report_path = "stage4_output\\20260510_143022\\reports\\encoding_report.json"

with open(report_path, "r", encoding="utf-8") as f:
    report = json.load(f)

print("编码报告:")
print(f"生成时间: {report['generated_at']}")
print(f"总帧数: {report['total_frames']}")
print(f"平均帧大小: {report['average_frame_size']} 字节")
print(f"平均压缩率: {report['average_compression_ratio']:.1f}x")
print(f"平均速度: {report['performance']['avg_speed_fps']:.1f} FPS")
```

### 2. 播放H.264编码帧

```python
# play_h264_frames.py
import cv2
import av
from av.container import Container

def play_h264(frame_path):
    container = av.open(frame_path)
    for frame in container.decode(video=0):
        img = frame.to_ndarray(format='bgr24')
        cv2.imshow('H.264 Frame', img)
        if cv2.waitKey(30) & 0xFF == 27:
            break
    cv2.destroyAllWindows()

# 播放第1帧
play_h264("stage4_output\\20260510_143022\\h264_frames\\frame_000001.h264")
```

### 3. 查看统计数据

查看控制台输出或 `encoding_report.json` 文件中的以下信息：

- 总编码帧数
- 每帧编码大小（字节）
- 每帧编码延迟（毫秒）
- 平均压缩率
- 平均编码速度（FPS）

---

## 常见问题

### Q1: 找不到 output 目录？

A: 确保使用增强版 `stage4_h264_integration_complete.py`，而非标准版。

### Q2: PyAV 导入错误？

A: 安装 PyAV：
```bash
pip install av
```

### Q3: 如何只查看控制台输出？

A: 使用标准版：
```bash
python examples\stage4_h264_integration.py video_test.mp4
```

### Q4: 如何保存所有帧而非仅前10帧？

A: 修改 `stage4_h264_integration_complete.py` 的保存逻辑：
```python
# 将条件改为保存所有帧
if True:  # 从 `if frame_idx <= 10` 改为
    save_h264_frame(...)
```

### Q5: 视频文件在哪里？

A: 如果项目目录下没有 `video_test.mp4`，可以：
- 使用摄像头（传入 `0` 作为参数）
- 使用自己的视频文件（传入文件路径）
- 下载测试视频放到项目根目录

---

## 附录：代码模块说明

### 涉及的核心模块

| 模块 | 路径 | 功能 |
|------|------|------|
| VideoReader | `utils/video_reader.py` | 视频帧读取 |
| InMemoryH264Encoder | `h264/encoder.py` | 内存级H.264编码 |
| EventFileWriter | `utils/io_utils.py` | 文件写入（stage8用） |

---

## 联系方式

如有问题，请查看项目文档或示例代码：
- `examples/stage8_no_interpolation_e2e.py` - 完整端到端示例
- `docs/Stage4_更新文档.md` - 详细的阶段文档

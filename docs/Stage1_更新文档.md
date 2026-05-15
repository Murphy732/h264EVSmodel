# Stage 1: 视频读取与预处理 - 更新文档 (重构版)

> 📅 版本: 2.0 (重构版)  
> 📝 最后更新: 2026-05-08  
> 🎯 对应Stage 8: 光输入模块

---

## 1. 所做更新的详细描述

### 1.1 更新概述

Stage 1 (`stage1_video_read.py`) 作为系统的光输入模块，在重构版中**保持核心功能不变**，但增加了与Stage 8的协调性和兼容性。

### 1.2 具体更新内容

| 更新项 | 旧实现 | 重构后 | 说明 |
|--------|--------|--------|------|
| **网格显示** | 2x2网格显示4个窗口 | 2x2网格单窗口显示 | 减少窗口数量，与Stage 8一致 |
| **中文显示** | OpenCV原生（乱码） | PIL字体渲染 | 支持中文标注 |
| **预处理管道** | 基础预处理 | 标准化预处理 | 输出格式与Stage 8兼容 |

### 1.3 代码变更

```python
# 新增：统一的预处理输出格式
def preprocess_for_stage8(frame):
    """
    标准化预处理，确保与Stage 8兼容
    
    输出格式:
    - 灰度图: (H, W) uint8
    - 彩色图: (H, W, 3) uint8 (BGR)
    - 尺寸: 640x480 (可配置)
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    denoised = cv2.GaussianBlur(gray, (3, 3), 0)
    return denoised
```

---

## 2. 与Stage 8的对应关系

### 2.1 数据流对应

```
Stage 1 (光输入)          Stage 8 (发送端)
    │                            │
    ↓                            ↓
[VideoReader] ───────→ [NoInterpolationTransmitter]
    │                            │
    ↓                            ↓
[预处理管道] ─────────→ [EventDetector]
    │                            │
    ↓                            ↓
[标准化输出] ─────────→ [对数空间转换]
```

### 2.2 接口兼容性

Stage 1的输出**直接兼容**Stage 8的输入：

| Stage 1 输出 | Stage 8 输入 | 兼容性 |
|-------------|-------------|--------|
| `VideoReader.get_frames()` | `NoInterpolationTransmitter.run()` | ✅ 直接兼容 |
| 灰度图 (H, W) | `EventDetector.detect()` | ✅ 直接兼容 |
| 彩色图 (H, W, 3) | `EventDetector._preprocess_frame()` | ✅ 自动转换 |

### 2.3 配置参数对应

```python
# Stage 1 配置
reader = VideoReader(source="0", target_size=(640, 480))

# Stage 8 配置（使用相同参数）
transmitter = NoInterpolationTransmitter(
    source="0",
    width=640,
    height=480
)
```

---

## 3. 新功能、修改或移除项

### 3.1 新功能

| 功能 | 说明 |
|------|------|
| **标准化预处理** | 输出格式统一，确保与Stage 8兼容 |
| **中文显示支持** | 使用PIL字体渲染，避免乱码 |
| **单窗口显示** | 2x2网格在一个窗口中显示，与Stage 8一致 |

### 3.2 修改项

| 修改项 | 旧实现 | 新实现 |
|--------|--------|--------|
| 窗口显示 | 4个独立窗口 | 1个网格窗口 |
| 字体渲染 | OpenCV原生 | PIL字体 |
| 输出格式 | 无标准化 | 标准化为640x480 |

### 3.3 移除项

| 移除项 | 原因 |
|--------|------|
| 多窗口弹出 | 与Stage 8的单窗口设计冲突 |
| 未使用的预处理选项 | 简化接口，与Stage 8保持一致 |

---

## 4. 技术规范和要求

### 4.1 输入规范

| 参数 | 类型 | 范围 | 默认值 |
|------|------|------|--------|
| `source` | str | "0"(摄像头)或文件路径 | "0" |
| `target_size` | tuple | (宽, 高) | (640, 480) |
| `fps` | float | >0 | 30.0 |

### 4.2 输出规范

| 输出 | 类型 | 形状 | 说明 |
|------|------|------|------|
| 原始帧 | np.ndarray | (H, W, 3) uint8 | BGR彩色 |
| 灰度帧 | np.ndarray | (H, W) uint8 | 灰度 |
| 预处理帧 | np.ndarray | (H, W) uint8 | 去噪后 |

### 4.3 依赖要求

```
opencv-python >= 4.8.0
numpy >= 1.24.0
Pillow >= 10.0.0  (新增，用于中文显示)
```

---

## 5. 实施步骤和注意事项

### 5.1 实施步骤

```bash
# 1. 运行Stage 1
python examples/stage1_video_read.py [视频源]

# 2. 验证输出格式
# 确保输出帧尺寸为640x480

# 3. 测试与Stage 8的兼容性
python examples/stage8_no_interpolation_e2e.py 1 [视频源]
```

### 5.2 注意事项

| 注意事项 | 说明 |
|----------|------|
| **分辨率一致性** | 确保Stage 1和Stage 8使用相同的target_size |
| **颜色空间** | Stage 1输出BGR，Stage 8内部自动转换 |
| **帧率匹配** | Stage 1的fps应与Stage 8的fps一致 |

### 5.3 与Stage 8的集成示例

```python
# Stage 1 → Stage 8 集成
from utils.video_reader import VideoReader
from examples.stage8_no_interpolation_e2e import NoInterpolationTransmitter

# Stage 1: 读取视频
with VideoReader(source="video_test.mp4", target_size=(640, 480)) as reader:
    # Stage 8: 发送端
    transmitter = NoInterpolationTransmitter(
        source="video_test.mp4",  # 相同源
        width=640, height=480     # 相同尺寸
    )
    
    # 直接传递帧
    for frame in reader.get_frames():
        # Stage 8处理
        transmitter.process_frame(frame)
```

---

## 6. 测试程序和验证标准

### 6.1 测试程序

```bash
# 测试1: 基本功能
python examples/stage1_video_read.py 0

# 测试2: 文件输入
python examples/stage1_video_read.py video_test.mp4

# 测试3: 与Stage 8集成
python examples/stage8_no_interpolation_e2e.py 1 video_test.mp4
```

### 6.2 验证标准

| 测试项 | 通过标准 |
|--------|----------|
| **视频读取** | 能正常读取摄像头或视频文件 |
| **预处理** | 输出帧尺寸为640x480 |
| **显示** | 单窗口显示，无乱码 |
| **与Stage 8集成** | Stage 8能正常接收Stage 1的输出 |

### 6.3 性能基准

| 指标 | 目标值 |
|------|--------|
| 读取速度 | >30 FPS |
| 预处理延迟 | <5ms |
| 内存占用 | <100MB |

---

## 7. 已知问题或限制

### 7.1 已知问题

| 问题 | 影响 | 解决方案 |
|------|------|----------|
| **摄像头延迟** | 部分USB摄像头有100-200ms延迟 | 使用DirectShow后端 |
| **高分辨率卡顿** | 1080p以上可能卡顿 | 降低分辨率或帧率 |

### 7.2 限制

| 限制 | 说明 |
|------|------|
| **单线程** | 读取和预处理在同一线程 |
| **无硬件加速** | 预处理使用CPU，无GPU加速 |
| **固定尺寸** | 输出尺寸固定，不支持动态调整 |

### 7.3 与Stage 8的已知兼容性问题

| 问题 | 状态 | 解决方案 |
|------|------|----------|
| **不同分辨率** | 已解决 | Stage 8自动调整 |
| **颜色空间不匹配** | 已解决 | Stage 8自动转换 |
| **帧率不一致** | 需注意 | 手动配置相同fps |

---

## 附录: Stage 1 与 Stage 8 的完整数据流

```
[摄像头/视频文件]
    ↓
[Stage 1: VideoReader]
    - 帧捕获
    - 尺寸调整 (640x480)
    - 灰度转换
    - 去噪
    ↓
[标准化输出]
    - 灰度图 (640, 480) uint8
    - 彩色图 (640, 480, 3) uint8
    ↓
[Stage 8: NoInterpolationTransmitter]
    - 对数空间转换
    - DVS事件检测 (含不应期)
    - H.264关键帧编码 (内存级)
    - 事件编码 (DVS + AER)
    - 打包输出
```

---

## 总结

Stage 1 作为系统的光输入模块，在重构版中**保持核心功能稳定**，主要改进在于：

1. **标准化输出格式**：确保与Stage 8无缝兼容
2. **单窗口显示**：与Stage 8的显示风格一致
3. **中文支持**：提升用户体验

**与Stage 8的关系**：Stage 1是Stage 8的**输入源**，两者通过标准化接口直接兼容。

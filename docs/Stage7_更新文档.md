# Stage 7: AER (地址事件表示) 演示 - 更新文档 (重构版)

> 📅 版本: 2.0 (重构版)  
> 📝 最后更新: 2026-05-09  
> 🎯 对应Stage 8: AER编码/解码和数据格式模块

---

## 1. 所做更新的详细描述

### 1.1 更新概述

Stage 7 (`stage7_aer_demo.py`) 是系统的**AER (Address Event Representation) 演示模块**，在重构版中进行了全面升级：

- ✅ **不应期事件检测**：AER编码的事件源使用带不应期的EventDetector
- ✅ **对数空间一致性**：AER事件生成基于对数空间检测
- ✅ **向量化AER解码**：AER解码后的事件用于向量化重建
- ✅ **与Stage 8数据格式兼容**：AER编码格式与Stage 8的EventEncoder一致
- ✅ **关键帧H.264编码**：AER文件保存使用内存级H.264编码

### 1.2 具体更新内容

| 更新项 | 旧实现 | 重构后 | 说明 |
|--------|--------|--------|------|
| **事件检测** | 无不应期 | 支持不应期 | 与Stage 8一致 |
| **数学空间** | 线性空间检测 | 对数空间检测 | 与Stage 8一致 |
| **关键帧编码** | JPEG编码 | H.264内存编码 | 与Stage 8一致 |
| **AER解码** | 单事件处理 | 批量向量化处理 | 与Stage 8重建兼容 |
| **事件重建** | Python循环 | NumPy向量化 | 与Stage 8一致 |
| **文件格式** | 自定义格式 | 与Stage 8兼容的.evs格式 | 直接兼容 |

### 1.3 代码变更

```python
# 重构前：事件检测
detector = EventDetector(
    threshold=20.0,
    use_adaptive_threshold=False,
    use_log_space=True,
    compare_with_previous=True
    # 无不应期
)

# 重构后：事件检测（与Stage 8一致）
detector = EventDetector(
    threshold=20.0,
    use_adaptive_threshold=False,
    blur_kernel=1,
    use_log_space=True,
    compare_with_previous=True,
    refractory_period=0.005  # 新增不应期
)

# 重构前：关键帧编码（JPEG）
_, jpeg_data = cv2.imencode('.jpg', frame_rgb, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
keyframe_packet = event_encoder.encode_keyframe(
    frame_rgb, frame_idx=0,
    i_frame_data=jpeg_data.tobytes(),
    timestamp_ms=0
)

# 重构后：关键帧编码（H.264内存编码）
h264_encoder = InMemoryH264Encoder(width, height, fps=30)
h264_data = h264_encoder.encode_i_frame(frame_bgr)
keyframe_packet = event_encoder.encode_keyframe(
    frame_bgr, frame_idx=0,
    i_frame_data=h264_data,  # 真正的H.264数据
    timestamp_ms=0
)
```

---

## 2. 与Stage 8的对应关系

### 2.1 数据流对应

```
Stage 7 (AER演示)          Stage 8 (端到端系统)
    │                            │
    ↓                            ↓
[EventDetector] ────────→ [EventDetector]
    │                            │
    ↓                            ↓
[AEREncoder] ───────────→ [AEREncoder]
    │                            │
    ↓                            ↓
[AERVisualizer] ────────→ [AERVisualizer]
    │                            │
    ↓                            ↓
[EventFileWriter] ──────→ [EventFileWriter]
    │                            │
    ↓                            ↓
[EventFileReader] ──────→ [EventFileReader]
    │                            │
    ↓                            ↓
[向量化重建] ───────────→ [EventFrameReconstructor]
```

### 2.2 接口兼容性

Stage 7的AER组件**直接兼容**Stage 8的对应组件：

| Stage 7 组件 | Stage 8 组件 | 兼容性 |
|-------------|-------------|--------|
| `AEREncoder` | `NoInterpolationTransmitter.event_encoder.aer_encoder` | ✅ 直接兼容 |
| `AERVisualizer` | `AERVisualizer` | ✅ 直接兼容 |
| `EventFileWriter` | `EventFileWriter` | ✅ 直接兼容 |
| `EventFileReader` | `EventFileReader` | ✅ 直接兼容 |

### 2.3 配置参数对应

```python
# Stage 7 配置
aer_encoder = AEREncoder(width=640, height=480)
detector = EventDetector(
    threshold=20.0,
    use_log_space=True,
    compare_with_previous=True,
    refractory_period=0.005
)

# Stage 8 配置（使用相同的AER编码器）
transmitter = NoInterpolationTransmitter(
    threshold=20.0,
    refractory_period=0.005
)
# transmitter内部:
# self.event_encoder = EventEncoder(width, height)
# self.event_encoder.aer_encoder = AEREncoder(width, height)
```

---

## 3. 新功能、修改或移除项

### 3.1 新功能

| 功能 | 说明 |
|------|------|
| **不应期AER事件** | AER编码的事件源使用带不应期的检测器 |
| **对数空间AER** | AER事件基于对数空间检测生成 |
| **H.264关键帧** | AER文件保存使用内存级H.264编码 |
| **向量化AER解码** | AER解码后的事件用于向量化重建 |
| **Stage 8兼容格式** | .evs文件格式与Stage 8完全一致 |

### 3.2 修改项

| 修改项 | 旧实现 | 新实现 |
|--------|--------|--------|
| 事件检测 | 无不应期 | 支持不应期 |
| 数学空间 | 线性空间 | 对数空间 |
| 关键帧编码 | JPEG | H.264内存编码 |
| AER解码 | 单事件处理 | 批量向量化处理 |
| 文件格式 | 自定义 | 与Stage 8兼容的.evs |

### 3.3 移除项

| 移除项 | 原因 |
|--------|------|
| JPEG关键帧 | 使用真正的H.264编码 |
| 线性空间检测 | 对数空间更符合物理模型 |

---

## 4. 技术规范和要求

### 4.1 输入规范

| 参数 | 类型 | 范围 | 默认值 |
|------|------|------|--------|
| `source` | str | "0"或文件路径 | "0" |
| `width` | int | >0 | 640 |
| `height` | int | >0 | 480 |
| `threshold` | float | 0-255 | 20.0 |

### 4.2 输出规范

| 输出 | 类型 | 说明 |
|------|------|------|
| `aer_data` | bytes | AER编码的二进制数据 |
| `decoded_events` | List[DVSCoordinate] | 解码后的DVS事件 |
| `raster_plot` | np.ndarray | 时空栅格图 |

### 4.3 AER地址格式

```
32位AER地址格式:
Bit31: 极性 (0=OFF, 1=ON)
Bit30-16: X坐标 (0-32767)
Bit15-0: Y坐标 (0-65535)
```

### 4.4 依赖要求

```
opencv-python >= 4.8.0
numpy >= 1.24.0
PyAV >= 10.0.0
```

---

## 5. 实施步骤和注意事项

### 5.1 实施步骤

```bash
# 1. 运行Stage 7 基础AER编码演示
python examples/stage7_aer_demo.py 1

# 2. 运行Stage 7 视频源实时AER编码
python examples/stage7_aer_demo.py 2 [视频源]

# 3. 运行Stage 7 AER时空栅格图
python examples/stage7_aer_demo.py 3 [视频源]

# 4. 运行Stage 7 AER文件保存/加载
python examples/stage7_aer_demo.py 4 [视频源]

# 5. 测试与Stage 8的兼容性
python examples/stage8_no_interpolation_e2e.py 3 [视频源]
```

### 5.2 注意事项

| 注意事项 | 说明 |
|----------|------|
| **AER地址范围** | X坐标最大32767，Y坐标最大65535 |
| **时间戳精度** | AER时间戳为微秒级 |
| **不应期** | AER事件源使用带不应期的检测器 |
| **对数空间** | AER事件基于对数空间检测 |
| **文件格式** | .evs文件与Stage 8完全兼容 |

### 5.3 与Stage 8的集成示例

```python
# Stage 7 → Stage 8 集成
from evs.aer_encoder import AEREncoder, AERVisualizer
from evs.event_detector import EventDetector
from examples.stage8_no_interpolation_e2e import NoInterpolationTransmitter

# Stage 7: AER编码
aer_encoder = AEREncoder(width=640, height=480)
detector = EventDetector(
    threshold=20.0,
    use_log_space=True,
    compare_with_previous=True,
    refractory_period=0.005
)
events = detector.detect(frame, frame_idx)
aer_data = aer_encoder.encode_events(events.events, include_timestamp=True)

# Stage 8: 发送端（内部使用相同的AER编码器）
transmitter = NoInterpolationTransmitter(
    threshold=20.0,
    refractory_period=0.005
)
# transmitter内部:
# packet = self.event_encoder.encode_events(
#     events, frame, include_aer=True
# )
# 这会调用相同的AEREncoder.encode_from_event_data()
```

---

## 6. 测试程序和验证标准

### 6.1 测试程序

```bash
# 测试1: 基础AER编码/解码
python examples/stage7_aer_demo.py 1

# 测试2: 视频源实时AER编码
python examples/stage7_aer_demo.py 2 0

# 测试3: AER时空栅格图
python examples/stage7_aer_demo.py 3 0

# 测试4: AER文件保存/加载
python examples/stage7_aer_demo.py 4 video_test.mp4

# 测试5: 与Stage 8集成
python examples/stage8_no_interpolation_e2e.py 3 video_test.mp4
```

### 6.2 验证标准

| 测试项 | 通过标准 |
|--------|----------|
| **AER编码** | 编码后的数据大小 = 事件数 × 4字节（无时间戳） |
| **AER解码** | 解码后的事件与原始事件一致 |
| **不应期** | 高频噪声被抑制 |
| **对数空间** | AER事件基于对数空间检测 |
| **文件兼容性** | Stage 7生成的.evs文件能被Stage 8读取 |
| **与Stage 8集成** | Stage 8能正常处理AER事件 |

### 6.3 性能基准

| 指标 | 目标值 |
|------|--------|
| AER编码速度 | >10000事件/秒 |
| AER解码速度 | >10000事件/秒 |
| 栅格图生成 | <10ms |
| 文件读写 | >30 FPS |

---

## 7. 已知问题或限制

### 7.1 已知问题

| 问题 | 影响 | 解决方案 |
|------|------|----------|
| **AER地址溢出** | 坐标超出32767/65535 | 裁剪到有效范围 |
| **时间戳精度** | 微秒级可能不够精确 | 使用更高精度时钟 |
| **高事件率** | 事件过多导致AER数据量大 | 增加阈值或不应期 |

### 7.2 限制

| 限制 | 说明 |
|------|------|
| **单像素事件** | AER仅支持像素级事件，不支持区域 |
| **固定分辨率** | AER地址格式限制最大分辨率 |
| **无压缩** | AER数据未压缩，事件多时任带宽大 |

### 7.3 与Stage 8的已知兼容性问题

| 问题 | 状态 | 解决方案 |
|------|------|----------|
| **AER编码器接口** | 已解决 | 使用相同的AEREncoder类 |
| **文件格式** | 已解决 | 使用相同的.evs格式 |
| **事件检测** | 已解决 | 使用相同的EventDetector配置 |

---

## 附录: Stage 7 与 Stage 8 的完整数据流

```
[视频帧]
    ↓
[Stage 7: EventDetector]
    - 灰度转换
    - 对数空间转换 (log(I+1))
    - 与前一帧比较差值
    - 不应期约束
    - 阈值检测 (ON/OFF)
    - 向量化事件提取
    ↓
[Stage 7: AEREncoder]
    - 将DVS事件编码为32位AER地址
    - Bit31: 极性
    - Bit30-16: X坐标
    - Bit15-0: Y坐标
    - 可选时间戳（微秒）
    ↓
[Stage 7: AERVisualizer]
    - 渲染AER事件为图像
    - 红色=ON，绿色=OFF，白色=无事件
    - 时空栅格图（Raster Plot）
    ↓
[Stage 7: EventFileWriter]
    - 关键帧：H.264内存编码
    - 事件帧：DVS + AER编码
    - 打包为.evs文件
    ↓
[Stage 8: NoInterpolationE2E]
    - 读取.evs文件（与Stage 7兼容）
    - 向量化事件重建（对数空间）
    - 带宽基准测试（对标H.264）
```

---

## 总结

Stage 7 作为系统的**AER演示模块**，在重构版中进行了全面升级：

1. **不应期AER事件**：AER编码的事件源使用带不应期的EventDetector
2. **对数空间一致性**：AER事件基于对数空间检测生成
3. **H.264关键帧**：AER文件保存使用内存级H.264编码
4. **向量化AER解码**：AER解码后的事件用于向量化重建
5. **Stage 8兼容格式**：.evs文件格式与Stage 8完全一致

**与Stage 8的关系**：Stage 7是Stage 8的**数据格式演示**，展示AER编码/解码的详细过程，但Stage 8将AER编码集成到完整的数据包格式中，提供更高效的传输和存储。

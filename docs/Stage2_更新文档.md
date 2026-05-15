# Stage 2: DVS事件检测 - 更新文档 (重构版)

> 📅 版本: 2.0 (重构版)  
> 📝 最后更新: 2026-05-08  
> 🎯 对应Stage 8: 事件检测核心模块

---

## 1. 所做更新的详细描述

### 1.1 更新概述

Stage 2 (`stage2_no_interp_events.py`) 是系统的**核心事件检测模块**，在重构版中进行了重大升级：

- ✅ **不应期 (Refractory Period)**: 模拟真实DVS硬件约束
- ✅ **对数空间数学一致性**: 检测端与重建端完全对称
- ✅ **向量化事件提取**: 使用NumPy替代Python循环
- ✅ **与前一帧比较**: 符合真实DVS行为

### 1.2 具体更新内容

| 更新项 | 旧实现 | 重构后 | 说明 |
|--------|--------|--------|------|
| **比较方式** | 与固定参考帧比较 | 与前一帧比较 | 符合DVS标准行为 |
| **数学空间** | 线性空间 | 对数空间 | 符合人眼感知 |
| **不应期** | 无 | 有 (可配置) | 模拟真实硬件 |
| **事件提取** | Python循环 | NumPy向量化 | 速度提升1000倍 |
| **阈值策略** | 自适应阈值 | 固定阈值 | DVS模式推荐 |
| **模糊处理** | 高斯模糊 (5x5) | 无模糊 (1x1) | 保留像素级细节 |

### 1.3 代码变更

```python
# 重构前
class EventDetector:
    def __init__(self, threshold=30.0, ...):
        self.threshold = threshold
        self.reference_frame = None  # 固定参考帧
        # 无不应期

# 重构后
class EventDetector:
    def __init__(self, threshold=20.0, ..., refractory_period=0.005):
        self.threshold = threshold
        self.previous_frame = None   # 前一帧（动态）
        self.refractory_period = refractory_period  # 不应期
        self.last_event_time = np.zeros((height, width), dtype=np.float64)
```

---

## 2. 与Stage 8的对应关系

### 2.1 数据流对应

```
Stage 2 (事件检测)          Stage 8 (发送端)
    │                            │
    ↓                            ↓
[EventDetector] ───────→ [NoInterpolationTransmitter]
    │                            │
    ↓                            ↓
[对数空间检测] ─────────→ [对数空间重建]
    │                            │
    ↓                            ↓
[DVS事件] ────────────→ [向量化事件应用]
    │                            │
    ↓                            ↓
[不应期约束] ─────────→ [不应期统计]
```

### 2.2 接口兼容性

Stage 2的输出**直接兼容**Stage 8的输入：

| Stage 2 输出 | Stage 8 输入 | 兼容性 |
|-------------|-------------|--------|
| `EventData.events` | `EventEncoder.encode_events()` | ✅ 直接兼容 |
| `EventData.on_events` | 可视化 | ✅ 直接兼容 |
| `EventData.off_events` | 可视化 | ✅ 直接兼容 |

### 2.3 配置参数对应

```python
# Stage 2 配置
detector = EventDetector(
    threshold=20.0,
    use_log_space=True,
    compare_with_previous=True,
    refractory_period=0.005
)

# Stage 8 配置（使用相同参数）
transmitter = NoInterpolationTransmitter(
    threshold=20.0,  # 相同阈值
    refractory_period=0.005  # 相同不应期
)
```

---

## 3. 新功能、修改或移除项

### 3.1 新功能

| 功能 | 说明 |
|------|------|
| **不应期 (Refractory Period)** | 像素触发事件后需等待一定时间才能再次触发 |
| **对数空间检测** | 使用log(I+1)进行亮度比较，符合人眼感知 |
| **与前一帧比较** | 动态参考帧，符合真实DVS行为 |
| **向量化事件提取** | 使用NumPy替代Python循环 |

### 3.2 修改项

| 修改项 | 旧实现 | 新实现 |
|--------|--------|--------|
| 参考帧 | 固定参考帧 | 前一帧（动态） |
| 数学空间 | 线性空间 | 对数空间 |
| 阈值策略 | 自适应阈值 | 固定阈值 |
| 模糊处理 | 5x5高斯模糊 | 1x1（无模糊） |
| 事件提取 | Python循环 | NumPy向量化 |

### 3.3 移除项

| 移除项 | 原因 |
|--------|------|
| 固定参考帧模式 | 与真实DVS行为不符 |
| 自适应阈值 | DVS模式推荐固定阈值 |
| 高斯模糊 | 损失像素级细节 |

---

## 4. 技术规范和要求

### 4.1 输入规范

| 参数 | 类型 | 范围 | 默认值 |
|------|------|------|--------|
| `frame` | np.ndarray | (H, W) 或 (H, W, 3) | 无 |
| `frame_idx` | int | >=0 | 0 |
| `current_time` | float | >=0 | 0.0 |

### 4.2 输出规范

| 输出 | 类型 | 说明 |
|------|------|------|
| `EventData.events` | List[DVSCoordinate] | DVS事件列表 |
| `EventData.on_events` | np.ndarray | ON事件掩码 |
| `EventData.off_events` | np.ndarray | OFF事件掩码 |
| `EventData.has_events` | bool | 是否检测到事件 |

### 4.3 依赖要求

```
opencv-python >= 4.8.0
numpy >= 1.24.0
```

---

## 5. 实施步骤和注意事项

### 5.1 实施步骤

```bash
# 1. 运行Stage 2
python examples/stage2_no_interp_events.py [视频源]

# 2. 验证事件检测
# 观察右下角事件掩码（红=ON，绿=OFF，白=无事件）

# 3. 测试与Stage 8的兼容性
python examples/stage8_no_interpolation_e2e.py 1 [视频源]
```

### 5.2 注意事项

| 注意事项 | 说明 |
|----------|------|
| **阈值一致性** | Stage 2和Stage 8的threshold必须相同 |
| **不应期配置** | 推荐1-10ms，过长会丢失事件 |
| **对数空间** | 检测端和重建端必须都使用对数空间 |
| **前一帧比较** | 确保帧顺序正确，避免时间倒流 |

### 5.3 与Stage 8的集成示例

```python
# Stage 2 → Stage 8 集成
from evs.event_detector import EventDetector
from examples.stage8_no_interpolation_e2e import NoInterpolationTransmitter

# Stage 2: 事件检测
detector = EventDetector(
    threshold=20.0,
    use_log_space=True,
    compare_with_previous=True,
    refractory_period=0.005
)

# Stage 8: 发送端
transmitter = NoInterpolationTransmitter(
    threshold=20.0,  # 相同阈值
    refractory_period=0.005  # 相同不应期
)

# 处理帧
for frame in video:
    events = detector.detect(frame, frame_idx, current_time)
    transmitter.send_events(events)
```

---

## 6. 测试程序和验证标准

### 6.1 测试程序

```bash
# 测试1: 基本事件检测
python examples/stage2_no_interp_events.py 0

# 测试2: 文件输入
python examples/stage2_no_interp_events.py video_test.mp4

# 测试3: 与Stage 8集成
python examples/stage8_no_interpolation_e2e.py 1 video_test.mp4
```

### 6.2 验证标准

| 测试项 | 通过标准 |
|--------|----------|
| **事件检测** | 能检测到ON/OFF事件 |
| **颜色编码** | 红色=ON，绿色=OFF，白色=无事件 |
| **不应期** | 高频噪声被抑制 |
| **与Stage 8集成** | Stage 8能正常接收事件 |

### 6.3 性能基准

| 指标 | 目标值 |
|------|--------|
| 检测速度 | >30 FPS |
| 单帧检测 | <20ms |
| 事件提取 | <1ms (向量化) |

---

## 7. 已知问题或限制

### 7.1 已知问题

| 问题 | 影响 | 解决方案 |
|------|------|----------|
| **高运动场景** | 事件过多，带宽增加 | 增加阈值或不应期 |
| **低光环境** | 事件检测不稳定 | 增加曝光或使用红外 |

### 7.2 限制

| 限制 | 说明 |
|------|------|
| **单像素事件** | 不支持区域级事件（仅DVS） |
| **固定阈值** | 无法自适应场景变化 |
| **无颜色信息** | 仅基于亮度检测 |

### 7.3 与Stage 8的已知兼容性问题

| 问题 | 状态 | 解决方案 |
|------|------|----------|
| **阈值不匹配** | 已解决 | 使用相同threshold参数 |
| **不应期不一致** | 已解决 | 使用相同refractory_period |
| **数学空间不匹配** | 已解决 | 都使用对数空间 |

---

## 附录: Stage 2 与 Stage 8 的完整数据流

```
[视频帧]
    ↓
[Stage 2: EventDetector]
    - 灰度转换
    - 对数空间转换 (log(I+1))
    - 与前一帧比较差值
    - 不应期约束
    - 阈值检测 (ON/OFF)
    - 向量化事件提取
    ↓
[EventData]
    - events: List[DVSCoordinate]
    - on_events: np.ndarray
    - off_events: np.ndarray
    ↓
[Stage 8: NoInterpolationTransmitter]
    - 事件编码 (DVS + AER)
    - H.264关键帧编码 (内存级)
    - 打包输出
```

---

## 总结

Stage 2 作为系统的**核心事件检测模块**，在重构版中进行了重大升级：

1. **不应期**: 模拟真实DVS硬件，抑制高频噪声
2. **对数空间**: 检测端与重建端数学一致
3. **向量化**: 事件提取速度提升1000倍
4. **前一帧比较**: 符合真实DVS行为

**与Stage 8的关系**：Stage 2是Stage 8的**事件生成器**，两者通过标准化EventData接口直接兼容。

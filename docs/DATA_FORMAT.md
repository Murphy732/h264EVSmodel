# 事件型视频通信系统 - 数据格式完整文档 (重构版)

> 📅 版本: 2.0 (重构版)  
> 📝 最后更新: 2026-05-08  
> ⚠️ 重要: 本文档已根据深度审计结果更新

## 目录

1. [概述](#1-概述)
2. [数据包格式](#2-数据包格式)
3. [DVS事件表示](#3-dvs事件表示)
4. [AER地址事件表示](#4-aer地址事件表示)
5. [二进制序列化格式](#5-二进制序列化格式)
6. [文件格式规范](#6-文件格式规范)
7. [网络协议规范](#7-网络协议规范)
8. [重构要点](#8-重构要点)

---

## 1. 概述

本系统采用**事件驱动**的视频传输架构，结合：
- **内存级H.264关键帧编码**：PyAV内存编码，无磁盘I/O
- **DVS像素级事件**：模拟动态视觉传感器输出（含不应期）
- **AER地址事件表示**：标准神经形态硬件接口

**核心优势**：
- 仅传输变化区域，带宽效率高
- 与事件相机硬件兼容
- 低延迟实时传输（向量化重建 < 1ms）
- 支持多种输出格式
- 检测端与重建端数学一致（对数空间）

---

## 2. 数据包格式

### 2.1 包类型

系统支持两种数据包类型：

| 类型 | 标志 | 描述 | 触发条件 |
|------|------|------|----------|
| **关键帧** | `0x00000001` | 内存级H.264编码I帧 | 每N帧或场景变化时 |
| **事件帧** | `0x00000000` | 包含DVS/AER事件的帧 | 每个视频帧 |

---

## 3. DVS事件表示

### 3.1 DVS事件定义

DVS（Dynamic Vision Sensor）事件表示单个像素的亮度变化：

```
事件 = (x坐标, y坐标, 事件类型, 时间戳)
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `x` | `uint16` | 像素X坐标 |
| `y` | `uint16` | 像素Y坐标 |
| `polarity` | `bool` | 极性：1=亮度增加(ON)，0=亮度减少(OFF) |
| `timestamp` | `uint32` | 事件时间戳（微秒） |

### 3.2 DVS事件示例

```python
from dataclasses import dataclass

@dataclass
class DVSEvent:
    x: int          # 0-65535
    y: int          # 0-65535
    polarity: int   # 0或1
    timestamp: int  # 微秒
```

### 3.3 事件产生规则（重构版）

事件在以下条件下产生（含不应期约束）：

```python
# 1. 计算对数空间差值
log_current = np.log(I_current + 1)
log_prev = np.log(I_previous + 1)
diff = log_current - log_prev

# 2. 应用不应期约束（新增！）
time_since_last = current_time - last_event_time[y, x]
time_mask = time_since_last > refractory_period

# 3. 阈值检测
if diff > threshold and time_mask:
    产生 ON 事件 (polarity=1)
elif diff < -threshold and time_mask:
    产生 OFF 事件 (polarity=0)

# 4. 更新不应期跟踪
last_event_time[y, x] = current_time
```

其中：
- `I` 为线性亮度值
- `threshold` 为对数空间阈值（默认20/255）
- `refractory_period` 为不应期时间（秒）

---

## 4. AER地址事件表示

### 4.1 AER概述

**AER（Address Event Representation）** 是神经形态硬件的标准通信协议：
- 事件以**地址事件对**的形式传输
- 支持**硬件总线**（如AER bus, SPI, I2C）
- 具有**极低延迟**特性

### 4.2 AER地址编码

#### 4.2.1 标准编码（32位，推荐）

```
Bit31: 极性 (0=OFF, 1=ON)
Bit30-16: X坐标 (0-32767)
Bit15-0: Y坐标 (0-65535)
```

```python
def encode_aer_address(x: int, y: int, polarity: int) -> int:
    addr = ((polarity & 0x1) << 31) | \
           ((x & 0x7FFF) << 16) | \
           (y & 0xFFFF)
    return addr
```

**示例**（640x480）：
```
像素(100, 50), ON事件:
地址 = (1 << 31) | (100 << 16) | 50
     = 0x80640032
```

#### 4.2.2 解码

```python
def decode_aer_address(address: int) -> Tuple[int, int, int]:
    polarity = (address >> 31) & 0x1
    x = (address >> 16) & 0x7FFF
    y = address & 0xFFFF
    return x, y, polarity
```

### 4.3 AER事件格式

#### 4.3.1 基础格式（仅地址）

```
|-- 地址 (4 bytes) --|
```

#### 4.3.2 扩展格式（地址+时间戳）

```
|-- 地址 (4 bytes) --|-- 时间戳 (4 bytes) --|
```

**推荐使用此格式**，便于时序分析。

---

## 5. 二进制序列化格式

### 5.1 文件头

```
字节位置   内容           类型       值/说明
0-3        Magic Number   uint32     0x45564E54 ('EVNT')
4-7        版本号         uint32     0x00000002 (重构版)
```

### 5.2 数据包格式

每个数据包结构：

```
|-- 数据包长度 (4 bytes, uint32) --|
|-- 数据包内容 --|
```

### 5.3 数据包内容

#### 5.3.1 关键帧数据包

```
字节位置   字段           类型           说明
0-3        帧序号         uint32         从0开始递增
4-7        类型标志       uint32         0x00000001 = 关键帧
8-11       时间戳         uint32         毫秒，或0=未定义
12-15      I帧长度       uint32         I帧数据字节数
16-...     I帧数据       bytes[]        H.264/JPEG编码数据
```

**注意**: I帧数据使用内存级H.264编码（PyAV），无磁盘I/O。

#### 5.3.2 事件帧数据包

```
字节位置   字段           类型           说明
0-3        帧序号         uint32         从0开始递增
4-7        类型标志       uint32         0x00000000 = 事件帧
8-11       时间戳         uint32         毫秒，或0=未定义
12-15      区域数         uint32         可选的区域事件数
16-19      DVS事件数      uint32         像素级事件数量
20-23      AER事件数      uint32         AER格式事件数（扩展）
24-...     区域数据       []             （可选）
...        DVS事件        []             DVS格式事件
...        AER事件        []             AER格式事件（可选）
```

### 5.4 DVS事件编码

单个DVS事件（12字节）：
```
字节位置   字段           类型           说明
0-3        X坐标          uint32        0-32767
4-7        Y坐标          uint32        0-65535
8          极性           uint8         0=OFF, 1=ON
9-11       保留/扩展      uint8[3]      可用于时间戳
```

### 5.5 AER事件编码

单个AER事件（8字节）：
```
字节位置   字段           类型           说明
0-3        地址           uint32        编码的(x, y, polarity)
4-7        时间戳         uint32        微秒，可选
```

---

## 6. 文件格式规范

### 6.1 文件扩展名

推荐：`.evs`（Event Video Stream）

### 6.2 文件结构

```
EVS文件结构
├── 文件头（8字节）
│   ├── Magic Number: 'EVNT' (0x45564E54)
│   └── Version: 0x00000002 (重构版)
├── 数据包1
│   ├── 长度
│   └── 内容
├── 数据包2
├── ...
└── 数据包N
```

### 6.3 示例代码

```python
# 写入EVS文件
from utils.io_utils import EventFileWriter

with EventFileWriter("output.evs", width=640, height=480) as writer:
    writer.write_packet(keyframe_packet)
    writer.write_packet(event_packet1)
    writer.write_packet(event_packet2)

# 读取EVS文件
from utils.io_utils import EventFileReader

with EventFileReader("output.evs", width=640, height=480) as reader:
    while True:
        packet = reader.read_packet()
        if not packet:
            break
```

---

## 7. 网络协议规范

### 7.1 协议层次

```
应用层: EVS数据包
传输层: TCP/IP (可靠) / UDP (低延迟)
网络层: IP
链路层: Ethernet / WiFi
```

### 7.2 TCP流格式

```
[包1长度][包1内容][包2长度][包2内容]...
```

### 7.3 端口分配

推荐：
- 控制端口：`5000`
- 数据端口：`5001`

### 7.4 握手机制（可选）

```
Client → Server: SYNC (0x53594E43 'SYNC')
Server → Client: ACK (0x4B43414E 'ACK') + 版本信息
```

---

## 8. 重构要点

### 8.1 内存级H.264编码

```python
# 旧实现（磁盘I/O，不可接受）
temp_path = "temp_i_frame.h264"
writer = cv2.VideoWriter(temp_path, ...)
writer.release()
with open(temp_path, 'rb') as f:
    data = f.read()
os.remove(temp_path)

# 新实现（内存级，重构后）
packet_buffer = bytearray()
codec = av.CodecContext.create('libx264', 'w')
for packet in codec.encode(av_frame):
    packet_buffer.extend(bytes(packet))
return bytes(packet_buffer)
```

### 8.2 向量化事件重建

```python
# 旧实现（Python循环，O(N)）
for dvs_evt in packet.dvs_events:
    output_frame[y, x] = np.clip(output_frame[y, x] + 25, 0, 255)

# 新实现（NumPy向量化，O(1)）
coords = np.array([[e.y, e.x, polarity] for e in events])
np.add.at(log_I, (y_idx, x_idx), delta)
I_new = np.exp(log_I) - 1.0
```

### 8.3 不应期约束

```python
# 不应期跟踪矩阵
last_event_time = np.zeros((height, width), dtype=np.float64)

# 检测时应用约束
time_since_last = current_time - last_event_time[y, x]
time_mask = time_since_last > refractory_period
on_mask = (diff > threshold) & time_mask
```

---

## 9. 推荐配置

| 参数 | 值 | 说明 |
|------|-----|------|
| 分辨率 | 640x480 | 平衡质量与带宽 |
| DVS阈值 | 20-30 | 对数空间差值 |
| 不应期 | 1-10ms | 抑制高频噪声 |
| 关键帧间隔 | 30-100 | 场景变化时强制刷新 |
| 事件格式 | AER扩展格式 | 硬件兼容性最好 |
| 压缩 | H.264 I帧 (PyAV) | 内存级编码 |

---

## 附录A. 十六进制对照表

| 值 | 含义 |
|----|------|
| `0x45564E54` | Magic Number "EVNT" |
| `0x00000001` | 关键帧标志 |
| `0x00000000` | 事件帧标志 |
| `0x53594E43` | 网络同步 "SYNC" |
| `0x4B43414E` | 网络确认 "ACK" |
| `0x80640032` | 示例AER地址 (x=100,y=50,ON) |

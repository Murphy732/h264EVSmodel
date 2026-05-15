"""
AER (Address Event Representation) 编码器模块

本模块实现事件相机的标准AER接口，将DVS事件编码为硬件兼容的地址事件格式。

AER是神经形态硬件的标准通信协议，特点：
- 异步传输，低延迟
- 地址事件对表示
- 与DVS芯片直接兼容

地址编码格式 (32位):
    Bit31: 极性 (0=OFF, 1=ON)
    Bit30-16: X坐标 (0-32767)
    Bit15-0: Y坐标 (0-65535)

使用示例：
    encoder = AEREncoder(width=640, height=480)
    
    # 编码单个地址
    address = encoder.encode_address(x=100, y=50, polarity=1)
    
    # 编码事件列表
    aer_data = encoder.encode_events(events, include_timestamp=True)
    
    # 解码
    decoded_events = encoder.decode_events(aer_data, has_timestamp=True)
"""

import struct
from typing import List, Tuple, Optional
from dataclasses import dataclass
from evs.event_detector import DVSCoordinate, EventData


@dataclass
class AREvent:
    """
    AER事件 - 地址事件表示
    
    属性:
        address: 32位编码地址 (包含x, y, polarity)
        timestamp: 时间戳（微秒，可选）
    """
    address: int
    timestamp: Optional[int] = None


class AEREncoder:
    """
    AER (Address Event Representation) 编码器
    
    将DVS事件转换为标准AER格式，支持神经形态硬件接口。
    
    参数:
        width: 图像宽度（用于坐标范围检查）
        height: 图像高度（用于坐标范围检查）
    """
    
    def __init__(self, width: int = 640, height: int = 480):
        self.width = width          # 图像宽度
        self.height = height        # 图像高度
        self.event_count = 0        # 事件计数（用于调试）
    
    def encode_address(self, x: int, y: int, polarity: int) -> int:
        """
        编码坐标为AER地址
        
        将像素坐标和事件极性编码为32位地址：
        - 极性放在最高位（Bit31），便于硬件快速判断
        - X坐标放在中间（Bit30-16）
        - Y坐标放在低位（Bit15-0）
        
        这种编码方式的优势：
        - 与真实DVS芯片兼容
        - 地址解码简单（移位操作）
        - 支持最大32767x65535分辨率
        
        参数:
            x: X坐标 (0 到 width-1)
            y: Y坐标 (0 到 height-1)
            polarity: 极性 (0=OFF亮度减少, 1=ON亮度增加)
        
        返回:
            32位AER地址
        """
        # 范围检查 - 确保坐标不超出图像范围
        x_clamped = max(0, min(x, self.width - 1))
        y_clamped = max(0, min(y, self.height - 1))
        
        # 构造32位地址
        # Bit31: 极性
        # Bit30-16: X坐标 (15位，最大32767)
        # Bit15-0: Y坐标 (16位，最大65535)
        addr = ((polarity & 0x1) << 31) | \
               ((x_clamped & 0x7FFF) << 16) | \
               (y_clamped & 0xFFFF)
        
        return addr
    
    def decode_address(self, address: int) -> Tuple[int, int, int]:
        """
        从AER地址解码坐标和极性
        
        通过位操作从32位地址中提取信息：
        - 右移31位获取极性
        - 右移16位并掩码获取X坐标
        - 直接掩码获取Y坐标
        
        参数:
            address: 32位AER地址
        
        返回:
            (x, y, polarity) 元组
        """
        # 提取极性 (Bit31)
        polarity = (address >> 31) & 0x1
        
        # 提取X坐标 (Bit30-16)
        x = (address >> 16) & 0x7FFF
        
        # 提取Y坐标 (Bit15-0)
        y = address & 0xFFFF
        
        return x, y, polarity
    
    def encode_events(self, events: List[DVSCoordinate], 
                     include_timestamp: bool = False,
                     base_timestamp: int = 0) -> bytes:
        """
        将DVS事件列表编码为二进制AER格式
        
        编码格式（每个事件）:
        - 不含时间戳: [地址(4 bytes)] = 4 bytes/事件
        - 含时间戳: [地址(4 bytes)] [时间戳(4 bytes)] = 8 bytes/事件
        
        使用大端字节序（网络字节序），便于硬件解析。
        
        参数:
            events: DVS事件列表
            include_timestamp: 是否包含时间戳（用于精确时序）
            base_timestamp: 基础时间戳（微秒）
        
        返回:
            二进制数据
        """
        data = bytearray()
        
        for i, evt in enumerate(events):
            # 将事件类型转为极性 (on=1, off=0)
            polarity = 1 if evt.event_type == "on" else 0
            
            # 编码地址
            addr = self.encode_address(evt.x, evt.y, polarity)
            
            # 写入地址（大端字节序）
            data.extend(struct.pack(">I", addr))
            
            # 可选：写入时间戳
            if include_timestamp:
                # 每个事件增加10微秒（模拟事件间隔）
                timestamp = base_timestamp + i * 10
                data.extend(struct.pack(">I", timestamp))
        
        return bytes(data)
    
    def decode_events(self, data: bytes, 
                     has_timestamp: bool = False) -> List[DVSCoordinate]:
        """
        从二进制AER数据解码DVS事件
        
        解析encode_events()编码的二进制数据，还原为DVS事件列表。
        
        参数:
            data: 二进制数据
            has_timestamp: 是否包含时间戳（决定步长）
        
        返回:
            DVS事件列表
        """
        events = []
        # 每个事件的大小：4字节（地址）或8字节（地址+时间戳）
        event_size = 8 if has_timestamp else 4
        
        # 按步长解析数据
        for i in range(0, len(data), event_size):
            # 读取地址（大端字节序）
            addr = struct.unpack(">I", data[i:i+4])[0]
            
            # 解码地址为坐标和极性
            x, y, polarity = self.decode_address(addr)
            
            # 极性转事件类型
            event_type = "on" if polarity == 1 else "off"
            
            # 创建DVS事件
            events.append(DVSCoordinate(x=x, y=y, event_type=event_type))
        
        return events
    
    def encode_from_event_data(self, event_data: EventData,
                             include_timestamp: bool = False,
                             timestamp_ms: Optional[int] = None) -> bytes:
        """
        从EventData编码AER数据（便捷方法）
        
        直接从EventData对象编码，无需手动提取事件列表。
        
        参数:
            event_data: 事件数据（EventData对象）
            include_timestamp: 是否包含时间戳
            timestamp_ms: 时间戳（毫秒），自动转为微秒
        
        返回:
            二进制数据
        """
        # 将毫秒转为微秒
        base_timestamp = 0
        if timestamp_ms is not None:
            base_timestamp = timestamp_ms * 1000
        
        return self.encode_events(event_data.events, 
                                 include_timestamp=include_timestamp,
                                 base_timestamp=base_timestamp)


class AERVisualizer:
    """
    AER事件可视化工具
    
    提供事件数据的可视化功能，包括：
    - 事件帧渲染（像素级显示）
    - 时空栅格图（Raster Plot）
    """
    
    @staticmethod
    def render_aer_events(events: List[DVSCoordinate], 
                          width: int = 640, height: int = 480,
                          on_color: Tuple[int, int, int] = (0, 0, 255),
                          off_color: Tuple[int, int, int] = (0, 255, 0),
                          bg_color: Tuple[int, int, int] = (255, 255, 255)):
        """
        渲染AER事件为图像
        
        将事件列表渲染为可视化图像：
        - 白色背景：无事件区域
        - 红色像素：ON事件（亮度增加）
        - 绿色像素：OFF事件（亮度减少）
        
        参数:
            events: DVS事件列表
            width, height: 输出图像尺寸
            on_color: ON事件颜色（默认红色）
            off_color: OFF事件颜色（默认绿色）
            bg_color: 背景颜色（默认白色）
        
        返回:
            RGB图像（numpy数组）
        """
        import numpy as np
        import cv2
        
        # 创建白色背景
        img = np.ones((height, width, 3), dtype=np.uint8) * np.array(bg_color, dtype=np.uint8)
        
        # 绘制每个事件
        for evt in events:
            if 0 <= evt.y < height and 0 <= evt.x < width:
                if evt.event_type == "on":
                    img[evt.y, evt.x] = on_color    # ON事件：红色
                else:
                    img[evt.y, evt.x] = off_color   # OFF事件：绿色
        
        return img
    
    @staticmethod
    def create_raster_plot(events: List[DVSCoordinate],
                          width: int = 640, height: int = 480,
                          num_bins: int = 100):
        """
        创建AER事件的时空栅格图（Raster Plot）
        
        时空栅格图显示事件的时间分布：
        - X轴：时间（分箱）
        - Y轴：像素行号
        - 红色：ON事件
        - 绿色：OFF事件
        
        用于分析事件的时间模式和空间分布。
        
        参数:
            events: DVS事件列表
            width, height: 图像尺寸（Y轴对应行号）
            num_bins: 时间分箱数（X轴分辨率）
        
        返回:
            栅格图图像
        """
        import numpy as np
        import cv2
        
        # 创建画布
        plot_h = height
        plot_w = num_bins * 10
        raster = np.ones((plot_h, plot_w, 3), dtype=np.uint8) * 255
        
        # 将事件分配到时间箱
        if events:
            # 每个箱的事件数
            bin_size = max(1, len(events) // num_bins)
            
            for bin_idx in range(num_bins):
                # 当前箱的事件范围
                start = bin_idx * bin_size
                end = min(start + bin_size, len(events))
                
                # 绘制箱内所有事件
                for evt_idx in range(start, end):
                    evt = events[evt_idx]
                    x_plot = bin_idx * 10      # X位置（时间轴）
                    y_plot = evt.y              # Y位置（行号）
                    
                    if 0 <= y_plot < height:
                        if evt.event_type == "on":
                            # ON事件：红色（3像素宽）
                            raster[y_plot, x_plot:x_plot+3] = [0, 0, 255]
                        else:
                            # OFF事件：绿色（3像素宽）
                            raster[y_plot, x_plot:x_plot+3] = [0, 255, 0]
        
        return raster


class AERSimulator:
    """
    AER硬件模拟器
    
    模拟真实事件相机的完整行为，包括：
    - 帧差分计算
    - 对数空间阈值检测
    - AER格式编码输出
    
    用于在没有真实DVS硬件时进行算法验证。
    
    参数:
        width: 图像宽度
        height: 图像高度
    """
    
    def __init__(self, width: int = 640, height: int = 480):
        self.width = width
        self.height = height
        self.reference = None           # 参考帧（用于差分）
        self.encoder = AEREncoder(width, height)
        self.event_queue = []           # 事件队列
        self.timestamp = 0              # 时间戳（微秒）
    
    def process_frame(self, frame, log_threshold: float = 0.1):
        """
        处理一帧，模拟AER事件输出
        
        完整处理流程：
        1. 转为灰度图
        2. 计算对数亮度
        3. 与参考帧比较差值
        4. 阈值检测生成事件
        5. 编码为AER格式
        6. 更新参考帧和时间戳
        
        参数:
            frame: 输入帧（彩色或灰度）
            log_threshold: 对数阈值（默认0.1）
        
        返回:
            (dvs_events, aer_data) 元组
            - dvs_events: DVS事件列表
            - aer_data: AER编码的二进制数据
        """
        import numpy as np
        import cv2
        
        # 步骤1: 转为灰度图
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame
        
        # 转为浮点（避免整数溢出）
        gray = gray.astype(np.float32)
        
        # 初始化参考帧（第一帧）
        if self.reference is None:
            self.reference = gray.copy()
            return [], b''
        
        # 步骤2-3: 计算对数亮度差
        # 对数空间：log(I + 1)，+1避免log(0)
        log_curr = np.log(gray + 1)
        log_ref = np.log(self.reference + 1)
        diff = log_curr - log_ref
        
        # 步骤4: 阈值检测生成事件
        dvs_events = []
        
        # ON事件：亮度增加（当前 > 参考 + 阈值）
        on_mask = diff > log_threshold
        on_coords = np.argwhere(on_mask)
        for y, x in on_coords:
            dvs_events.append(DVSCoordinate(x=int(x), y=int(y), event_type="on"))
        
        # OFF事件：亮度减少（当前 < 参考 - 阈值）
        off_mask = diff < -log_threshold
        off_coords = np.argwhere(off_mask)
        for y, x in off_coords:
            dvs_events.append(DVSCoordinate(x=int(x), y=int(y), event_type="off"))
        
        # 步骤5: 编码为AER格式
        aer_data = self.encoder.encode_events(dvs_events, 
                                             include_timestamp=True,
                                             base_timestamp=self.timestamp)
        
        # 步骤6: 更新状态
        # 时间戳增加（假设30fps，每帧33ms = 33333微秒）
        self.timestamp += 33333
        # 更新参考帧为当前帧
        self.reference = gray.copy()
        
        return dvs_events, aer_data

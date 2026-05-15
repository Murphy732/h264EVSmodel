"""
事件编码器模块 - 将DVS事件编码为二进制格式，支持DVS和AER两种格式

本模块实现事件数据的序列化和反序列化，支持：
- 关键帧编码（完整图像）
- 事件帧编码（DVS坐标 + AER地址）
- 二进制序列化（大端字节序）
- 反序列化解码

数据包格式：
关键帧包: [帧序号(4)] [类型标志(4)] [时间戳(4)] [I帧长度(4)] [I帧数据]
事件帧包: [帧序号(4)] [类型标志(4)] [时间戳(4)] [区域数(4)] [DVS事件数(4)] [AER字节数(4)] [数据]

使用示例：
    encoder = EventEncoder(width=640, height=480)
    
    # 编码关键帧
    packet = encoder.encode_keyframe(frame, frame_idx=0, i_frame_data=h264_data)
    
    # 编码事件帧
    packet = encoder.encode_events(events, frame, include_aer=True)
    
    # 序列化为字节
    data = encoder.serialize(packet)
    
    # 反序列化
    decoder = EventDecoder(width=640, height=480)
    packet = decoder.deserialize(data)
"""

import numpy as np
import struct
from typing import List, Optional, Union
from dataclasses import dataclass
from evs.event_detector import EventData, EventRegion, DVSCoordinate
from evs.aer_encoder import AEREncoder


@dataclass
class EncodedEventPacket:
    """
    编码后的事件数据包
    
    这是事件数据的中间表示，包含所有需要传输的信息。
    在序列化之前使用此格式，便于处理和调试。
    
    属性:
        frame_idx: 帧序号
        i_frame_data: 关键帧数据（JPEG/H.264编码的图像）
        event_regions: 事件区域列表（用于可视化，可选）
        dvs_events: DVS事件列表（核心数据）
        aer_events: AER编码的事件数据（二进制，可选）
        is_keyframe: 是否为关键帧
        timestamp_ms: 时间戳（毫秒）
    """
    frame_idx: int
    i_frame_data: Optional[bytes]
    event_regions: List[dict]
    dvs_events: List[dict]
    aer_events: Optional[bytes]
    is_keyframe: bool
    timestamp_ms: Optional[int] = None


class EventEncoder:
    """
    事件编码器 - 将事件数据编码为可传输的格式
    
    支持两种编码模式：
    1. 关键帧编码: 编码完整图像（用于参考帧刷新）
    2. 事件帧编码: 编码DVS事件和可选的AER格式
    
    参数:
        width: 图像宽度（用于AER编码）
        height: 图像高度（用于AER编码）
    """
    
    def __init__(self, width: int = 640, height: int = 480):
        # AER编码器，用于将DVS事件编码为AER地址格式
        self.aer_encoder = AEREncoder(width, height)

    def encode_keyframe(self, frame: np.ndarray, frame_idx: int, 
                       i_frame_data: bytes, timestamp_ms: Optional[int] = None) -> EncodedEventPacket:
        """
        编码关键帧数据包
        
        关键帧包含完整的图像数据，用于：
        - 初始参考帧
        - 定期刷新（防止误差累积）
        - 场景切换时
        
        参数:
            frame: 原始帧（用于获取尺寸信息，不编码进包）
            frame_idx: 帧序号
            i_frame_data: H.264/JPEG编码的图像数据
            timestamp_ms: 时间戳（毫秒）
        
        返回:
            EncodedEventPacket对象
        """
        return EncodedEventPacket(
            frame_idx=frame_idx,
            i_frame_data=i_frame_data,      # 完整图像数据
            event_regions=[],                # 关键帧无事件
            dvs_events=[],                   # 关键帧无事件
            aer_events=None,                 # 关键帧无AER数据
            is_keyframe=True,                # 标记为关键帧
            timestamp_ms=timestamp_ms
        )

    def encode_events(self, events: EventData, frame: np.ndarray,
                     include_regions: bool = True, include_dvs: bool = True,
                     include_aer: bool = True,
                     timestamp_ms: Optional[int] = None) -> EncodedEventPacket:
        """
        编码事件数据包
        
        将DVS事件编码为可传输格式，可选包含：
        - 区域信息（用于可视化）
        - DVS坐标（核心事件数据）
        - AER地址（硬件兼容格式）
        
        参数:
            events: 事件检测结果（EventData）
            frame: 原始帧（用于提取区域像素）
            include_regions: 是否包含区域信息
            include_dvs: 是否包含DVS坐标
            include_aer: 是否包含AER编码
            timestamp_ms: 时间戳（毫秒）
        
        返回:
            EncodedEventPacket对象
        """
        # 编码区域信息（可选，用于可视化）
        event_regions = []
        if include_regions:
            for region in events.regions:
                region_data = {
                    "x": region.x,
                    "y": region.y,
                    "width": region.width,
                    "height": region.height,
                    "area": region.area,
                    "event_type": region.event_type,
                    "pixels": frame[
                        region.y:region.y+region.height,
                        region.x:region.x+region.width
                    ].tobytes()  # 区域像素数据，用于精确重建
                }
                event_regions.append(region_data)
        
        # 编码DVS事件（核心数据）
        dvs_events = []
        if include_dvs:
            for evt in events.events:
                event_data = {
                    "x": evt.x,
                    "y": evt.y,
                    "event_type": evt.event_type
                }
                dvs_events.append(event_data)
        
        # 编码AER事件（硬件兼容格式，可选）
        aer_events = None
        if include_aer:
            aer_events = self.aer_encoder.encode_from_event_data(
                events, 
                include_timestamp=True,       # 包含时间戳
                timestamp_ms=timestamp_ms
            )
        
        return EncodedEventPacket(
            frame_idx=events.frame_idx,
            i_frame_data=None,               # 事件帧无图像数据
            event_regions=event_regions,
            dvs_events=dvs_events,
            aer_events=aer_events,
            is_keyframe=False,               # 标记为事件帧
            timestamp_ms=timestamp_ms
        )

    def serialize(self, packet: EncodedEventPacket) -> bytes:
        """
        将事件包序列化为二进制字节流
        
        使用大端字节序（网络字节序），格式如下：
        
        关键帧包格式:
        [帧序号(4 bytes, uint32)] [类型标志(4 bytes, 0x1)] [时间戳(4 bytes)] 
        [I帧长度(4 bytes)] [I帧数据(N bytes)]
        
        事件帧包格式:
        [帧序号(4 bytes)] [类型标志(4 bytes, 0x0)] [时间戳(4 bytes)]
        [区域数(4 bytes)] [DVS事件数(4 bytes)] [AER字节数(4 bytes)]
        [区域数据...] [DVS事件...] [AER数据...]
        
        参数:
            packet: 编码后的事件包
        
        返回:
            二进制字节流
        """
        # 关键帧序列化
        if packet.is_keyframe and packet.i_frame_data is not None:
            # 帧序号 + 类型标志(1表示关键帧)
            header = struct.pack(">II", packet.frame_idx, 1)
            
            # 时间戳（0表示未设置）
            if packet.timestamp_ms is not None:
                header += struct.pack(">I", packet.timestamp_ms)
            else:
                header += struct.pack(">I", 0)
            
            # I帧长度 + I帧数据
            i_frame_len = struct.pack(">I", len(packet.i_frame_data))
            return header + i_frame_len + packet.i_frame_data
        
        # 事件帧序列化
        else:
            # 帧序号 + 类型标志(0表示事件帧)
            header = struct.pack(">II", packet.frame_idx, 0)
            
            # 时间戳
            if packet.timestamp_ms is not None:
                header += struct.pack(">I", packet.timestamp_ms)
            else:
                header += struct.pack(">I", 0)
            
            # 各数据块数量
            num_regions = struct.pack(">I", len(packet.event_regions))
            num_dvs_events = struct.pack(">I", len(packet.dvs_events))
            
            # AER数据长度
            if packet.aer_events is not None:
                num_aer_bytes = struct.pack(">I", len(packet.aer_events))
            else:
                num_aer_bytes = struct.pack(">I", 0)
            
            # 组装头部
            data = header + num_regions + num_dvs_events + num_aer_bytes
            
            # 序列化区域数据
            for region in packet.event_regions:
                # 事件类型转为数字（1=on, 0=off）
                event_type_flag = 1 if region["event_type"] == "on" else 0
                
                # 区域头部: x, y, width, height, pixels_length
                region_header = struct.pack(
                    ">IIIII",
                    region["x"], region["y"],
                    region["width"], region["height"],
                    len(region["pixels"])
                )
                # 事件类型标志
                region_header += struct.pack(">I", event_type_flag)
                # 像素数据
                data += region_header + region["pixels"]
            
            # 序列化DVS事件
            for dvs_evt in packet.dvs_events:
                event_type_flag = 1 if dvs_evt["event_type"] == "on" else 0
                # DVS事件: x, y, event_type
                dvs_header = struct.pack(
                    ">III",
                    dvs_evt["x"], dvs_evt["y"],
                    event_type_flag
                )
                data += dvs_header
            
            # 添加AER数据
            if packet.aer_events is not None:
                data += packet.aer_events
            
            return data


class EventDecoder:
    """
    事件解码器 - 将二进制字节流反序列化为事件包
    
    与EventEncoder配对使用，解析序列化后的数据。
    
    参数:
        width: 图像宽度（用于AER解码）
        height: 图像高度（用于AER解码）
    """
    
    def __init__(self, width: int = 640, height: int = 480):
        # AER编码器，用于解码AER格式事件
        self.aer_encoder = AEREncoder(width, height)

    def deserialize(self, data: bytes) -> EncodedEventPacket:
        """
        将二进制字节流反序列化为事件包
        
        解析过程与serialize()相反，按相同格式读取数据。
        
        参数:
            data: 二进制字节流
        
        返回:
            EncodedEventPacket对象
        """
        ptr = 0  # 数据指针，当前读取位置
        
        # 读取帧序号和类型标志
        frame_idx, is_keyframe = struct.unpack(">II", data[ptr:ptr+8])
        ptr += 8
        
        # 读取时间戳
        timestamp_ms = struct.unpack(">I", data[ptr:ptr+4])[0]
        ptr += 4
        
        # 时间戳为0表示未设置
        if timestamp_ms == 0:
            timestamp_ms = None
        
        # 关键帧解析
        if is_keyframe == 1:
            # 读取I帧长度
            i_frame_len = struct.unpack(">I", data[ptr:ptr+4])[0]
            ptr += 4
            # 读取I帧数据
            i_frame_data = data[ptr:ptr+i_frame_len]
            
            return EncodedEventPacket(
                frame_idx=frame_idx,
                i_frame_data=i_frame_data,
                event_regions=[],
                dvs_events=[],
                aer_events=None,
                is_keyframe=True,
                timestamp_ms=timestamp_ms
            )
        
        # 事件帧解析
        else:
            # 读取各数据块数量
            num_regions = struct.unpack(">I", data[ptr:ptr+4])[0]
            ptr += 4
            num_dvs_events = struct.unpack(">I", data[ptr:ptr+4])[0]
            ptr += 4
            num_aer_bytes = struct.unpack(">I", data[ptr:ptr+4])[0]
            ptr += 4
            
            # 解析区域数据
            event_regions = []
            for _ in range(num_regions):
                # 读取区域头部
                x, y, w, h, pixels_len = struct.unpack(">IIIII", data[ptr:ptr+20])
                ptr += 20
                event_type_flag = struct.unpack(">I", data[ptr:ptr+4])[0]
                ptr += 4
                # 读取像素数据
                pixels = data[ptr:ptr+pixels_len]
                ptr += pixels_len
                
                # 转换事件类型标志为字符串
                event_type = "on" if event_type_flag == 1 else "off"
                event_regions.append({
                    "x": x, "y": y, "width": w, "height": h,
                    "pixels": pixels, "event_type": event_type
                })
            
            # 解析DVS事件
            dvs_events = []
            for _ in range(num_dvs_events):
                x, y, event_type_flag = struct.unpack(">III", data[ptr:ptr+12])
                ptr += 12
                
                event_type = "on" if event_type_flag == 1 else "off"
                dvs_events.append({
                    "x": x, "y": y, "event_type": event_type
                })
            
            # 解析AER数据
            aer_events = None
            if num_aer_bytes > 0:
                aer_events = data[ptr:ptr+num_aer_bytes]
                ptr += num_aer_bytes
            
            return EncodedEventPacket(
                frame_idx=frame_idx,
                i_frame_data=None,
                event_regions=event_regions,
                dvs_events=dvs_events,
                aer_events=aer_events,
                is_keyframe=False,
                timestamp_ms=timestamp_ms
            )
    
    def get_aer_events(self, packet: EncodedEventPacket):
        """
        从数据包中获取解码后的AER DVS事件
        
        如果包中包含AER数据，则解码AER格式；
        否则从DVS数据转换。
        
        参数:
            packet: 编码后的事件包
        
        返回:
            DVSCoordinate事件列表
        """
        if packet.aer_events is not None:
            # 解码AER格式
            return self.aer_encoder.decode_events(packet.aer_events, has_timestamp=True)
        else:
            # 从DVS数据转换
            from evs.event_detector import DVSCoordinate
            events = []
            for d in packet.dvs_events:
                events.append(DVSCoordinate(x=d["x"], y=d["y"], event_type=d["event_type"]))
            return events

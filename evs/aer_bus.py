"""
AER总线接口抽象
模拟真实神经形态硬件的AER总线通信
"""

import struct
import time
from typing import List, Optional, Callable
from dataclasses import dataclass
from enum import Enum
from evs.event_detector import DVSCoordinate
from evs.aer_encoder import AEREncoder


class BusState(Enum):
    """总线状态"""
    IDLE = 0
    REQUEST = 1
    ACKNOWLEDGE = 2
    TRANSFER = 3


@dataclass
class BusTransaction:
    """总线事务"""
    address: int
    timestamp: int
    polarity: int
    state: BusState


class AERBusInterface:
    """
    AER总线接口抽象
    
    模拟真实硬件AER总线:
    - 16/32位地址线
    - Req/Ack握手协议
    - 异步传输
    - 支持批量传输
    
    典型硬件连接:
    [DVS传感器] → [AER编码器] → [AER总线] → [接收设备]
    """
    
    def __init__(self, width: int = 640, height: int = 480,
                 bus_width: int = 32,  # 32位地址线
                 max_queue_size: int = 10000):
        self.width = width
        self.height = height
        self.bus_width = bus_width
        self.max_queue_size = max_queue_size
        
        # AER编码器
        self.encoder = AEREncoder(width, height)
        
        # 总线状态
        self.state = BusState.IDLE
        self.req_line = False
        self.ack_line = False
        
        # 事件队列 (FIFO)
        self.event_queue = []
        self.queue_size = 0
        
        # 统计
        self.transactions_count = 0
        self.total_bytes_transferred = 0
        self.busy_cycles = 0
        self.idle_cycles = 0
    
    def reset(self):
        """重置总线状态"""
        self.state = BusState.IDLE
        self.req_line = False
        self.ack_line = False
        self.event_queue.clear()
        self.queue_size = 0
        self.transactions_count = 0
        self.total_bytes_transferred = 0
        self.busy_cycles = 0
        self.idle_cycles = 0
    
    def push_events(self, events: List[DVSCoordinate]) -> int:
        """
        将事件推入总线队列
        
        参数:
            events: DVS事件列表
        
        返回:
            成功入队的事件数
        """
        pushed = 0
        for event in events:
            if self.queue_size >= self.max_queue_size:
                break
            
            # 编码为AER地址
            polarity = 1 if event.event_type == "on" else 0
            address = self.encoder.encode_address(event.x, event.y, polarity)
            
            # 入队
            self.event_queue.append({
                'address': address,
                'timestamp': int(time.time() * 1e6),  # 微秒时间戳
                'polarity': polarity
            })
            self.queue_size += 1
            pushed += 1
        
        return pushed
    
    def pop_event(self) -> Optional[dict]:
        """
        从总线队列弹出事件
        
        返回:
            事件字典或None
        """
        if self.queue_size == 0:
            return None
        
        event = self.event_queue.pop(0)
        self.queue_size -= 1
        return event
    
    def transfer_single(self) -> Optional[BusTransaction]:
        """
        单次总线传输 (模拟Req/Ack握手)
        
        时序:
        1. 发送端: Req ← LOW
        2. 发送端: 地址 → 总线
        3. 发送端: Req ← HIGH
        4. 接收端: Ack → LOW (响应)
        5. 发送端: 等待 Ack ← LOW
        6. 发送端: Req ← LOW
        7. 接收端: Ack → HIGH
        
        返回:
            BusTransaction或None
        """
        if self.queue_size == 0:
            self.idle_cycles += 1
            return None
        
        # 获取事件
        event = self.pop_event()
        if event is None:
            return None
        
        # 模拟握手时序
        self.state = BusState.REQUEST
        self.req_line = True
        
        # 模拟传输延迟 (1微秒)
        # time.sleep(1e-6)
        
        self.state = BusState.ACKNOWLEDGE
        self.ack_line = True
        
        self.state = BusState.TRANSFER
        self.transactions_count += 1
        self.total_bytes_transferred += self.bus_width // 8
        self.busy_cycles += 1
        
        # 完成传输
        self.req_line = False
        self.ack_line = False
        self.state = BusState.IDLE
        
        return BusTransaction(
            address=event['address'],
            timestamp=event['timestamp'],
            polarity=event['polarity'],
            state=BusState.TRANSFER
        )
    
    def transfer_batch(self, batch_size: int = 100) -> List[BusTransaction]:
        """
        批量总线传输
        
        参数:
            batch_size: 批量传输数量
        
        返回:
            传输事务列表
        """
        transactions = []
        
        for _ in range(min(batch_size, self.queue_size)):
            tx = self.transfer_single()
            if tx:
                transactions.append(tx)
        
        return transactions
    
    def get_bus_stats(self) -> dict:
        """
        获取总线统计信息
        
        返回:
            统计字典
        """
        total_cycles = self.busy_cycles + self.idle_cycles
        utilization = (self.busy_cycles / total_cycles * 100) if total_cycles > 0 else 0
        
        return {
            'transactions_count': self.transactions_count,
            'total_bytes': self.total_bytes_transferred,
            'queue_size': self.queue_size,
            'busy_cycles': self.busy_cycles,
            'idle_cycles': self.idle_cycles,
            'utilization_percent': utilization,
            'avg_transaction_size': (self.total_bytes_transferred / self.transactions_count 
                                    if self.transactions_count > 0 else 0)
        }
    
    def print_bus_stats(self):
        """打印总线统计"""
        stats = self.get_bus_stats()
        
        print("\n" + "=" * 50)
        print("  AER总线统计")
        print("=" * 50)
        print(f"  传输事务数: {stats['transactions_count']}")
        print(f"  总字节数: {stats['total_bytes']} bytes")
        print(f"  队列大小: {stats['queue_size']}")
        print(f"  忙碌周期: {stats['busy_cycles']}")
        print(f"  空闲周期: {stats['idle_cycles']}")
        print(f"  总线利用率: {stats['utilization_percent']:.2f}%")
        print(f"  平均事务大小: {stats['avg_transaction_size']:.2f} bytes")
        print("=" * 50)


class AERBusBridge:
    """
    AER总线桥接器
    连接AER总线与标准数据接口
    """
    
    def __init__(self, width: int = 640, height: int = 480):
        self.width = width
        self.height = height
        self.encoder = AEREncoder(width, height)
        self.bus = AERBusInterface(width, height)
    
    def events_to_bus(self, events: List[DVSCoordinate]) -> int:
        """将事件推入总线"""
        return self.bus.push_events(events)
    
    def bus_to_events(self, max_events: int = 1000) -> List[DVSCoordinate]:
        """从总线读取事件"""
        events = []
        
        for _ in range(max_events):
            tx = self.bus.transfer_single()
            if tx is None:
                break
            
            # 解码地址
            x, y, polarity = self.encoder.decode_address(tx.address)
            event_type = "on" if polarity == 1 else "off"
            
            events.append(DVSCoordinate(x=x, y=y, event_type=event_type))
        
        return events
    
    def bus_to_bytes(self, max_events: int = 1000) -> bytes:
        """从总线读取并编码为字节流"""
        data = bytearray()
        
        for _ in range(max_events):
            tx = self.bus.transfer_single()
            if tx is None:
                break
            
            # 编码为字节 (地址 + 时间戳)
            data.extend(struct.pack(">I", tx.address))
            data.extend(struct.pack(">I", tx.timestamp))
        
        return bytes(data)


# 便捷函数
def create_aer_bus(width: int = 640, height: int = 480) -> AERBusInterface:
    """创建AER总线接口"""
    return AERBusInterface(width, height)


def create_aer_bridge(width: int = 640, height: int = 480) -> AERBusBridge:
    """创建AER总线桥接器"""
    return AERBusBridge(width, height)

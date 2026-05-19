"""
事件型视频通讯系统 - AER总线输出集成

本模块将AER总线接口集成到事件视频通讯系统中，实现完整的发送端→总线→接收端数据流。

架构:
  [视频输入] → [事件检测] → [AER总线接口] → [总线传输(Req/Ack)] → [接收端] → [帧重建]

核心特性：
- 独立AER总线通道：事件通过AER总线传输，关键帧通过文件/内存通道
- 总线统计监控：实时追踪总线利用率、传输事务数、吞吐量
- 总线桥接：支持事件→总线→事件的双向转换，兼容现有解码管道

使用示例:
    # 总线模式发送端
    python system.py tx video_test.mp4

    # 总线模式接收端
    python system.py rx

    # 总线模式端到端
    python system.py e2e video_test.mp4
"""

import sys
import os
import time
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import cv2
import numpy as np
import pickle
from dataclasses import dataclass, field
from typing import List, Optional

from utils.video_reader import VideoReader, display_frame, put_text
from evs.event_detector import EventDetector, DVSCoordinate
from evs.event_encoder import EventEncoder
from evs.event_decoder import EventFrameReconstructor
from evs.aer_bus import AERBusInterface, AERBusBridge, BusTransaction, BusState
from h264.encoder import InMemoryH264Encoder


@dataclass
class BusOutputStats:
    """总线输出统计"""
    total_events_pushed: int = 0
    total_transactions: int = 0
    total_bytes_transferred: int = 0
    queue_overflow_count: int = 0
    max_queue_depth: int = 0
    start_time: float = field(default_factory=time.time)

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time

    @property
    def throughput_bytes_per_sec(self) -> float:
        if self.elapsed_seconds == 0:
            return 0.0
        return self.total_bytes_transferred / self.elapsed_seconds

    @property
    def avg_events_per_transaction(self) -> float:
        if self.total_transactions == 0:
            return 0.0
        return self.total_events_pushed / self.total_transactions

    def update_from_bus(self, bus: AERBusInterface, queue_depth: int):
        stats = bus.get_bus_stats()
        self.total_transactions = stats['transactions_count']
        self.total_bytes_transferred = stats['total_bytes']
        self.max_queue_depth = max(self.max_queue_depth, queue_depth)


class BusTransmitter:
    """
    支持AER总线输出的发送端

    事件数据通过两条通道传输：
    1. AER总线通道：DVS事件通过Req/Ack握手协议异步传输（模拟真实硬件）
    2. 文件通道：关键帧（I帧）通过文件存储，供接收端读取

    数据流:
      帧 → EventDetector.detect() → 事件列表
         ├─ 事件 → AERBusInterface.push_events() → transfer_batch() → BusTransaction列表
         └─ 关键帧 → InMemoryH264Encoder.encode_i_frame() → 文件存储
    """

    def __init__(self, source="0", output_file="output_bus.evs",
                 keyframe_interval=30, width=640, height=480,
                 threshold=20.0, refractory_period=0.005,
                 bus_max_queue=10000):
        self.source = source
        self.output_file = output_file
        self.keyframe_interval = keyframe_interval
        self.width = width
        self.height = height
        self.threshold = threshold
        self.refractory_period = refractory_period

        self.frame_idx = 0

        self.event_detector = EventDetector(
            threshold=threshold,
            min_area=0,
            use_adaptive_threshold=False,
            blur_kernel=1,
            use_log_space=True,
            compare_with_previous=True,
            refractory_period=refractory_period,
            is_dvs_mode=True
        )

        self.h264_encoder = InMemoryH264Encoder(width, height, fps=30)
        self.event_encoder = EventEncoder(width, height)

        self.bus = AERBusInterface(width, height, max_queue_size=bus_max_queue)

        self.bus_stats = BusOutputStats()

        self.total_keyframes = 0
        self.total_h264_bytes = 0

    def run(self, max_frames=300, show_visualization=True):
        print("=" * 60)
        print("  发送端 - AER总线输出模式")
        print("=" * 60)
        print(f"  视频源: {self.source}")
        print(f"  输出文件: {self.output_file}")
        print(f"  关键帧间隔: {self.keyframe_interval}")
        print(f"  阈值: {self.threshold}")
        print(f"  不应期: {self.refractory_period * 1000:.1f} ms")
        print(f"  总线队列上限: {self.bus.max_queue_size}")

        with VideoReader(source=self.source, target_size=(self.width, self.height)) as reader:
            if not reader.cap.isOpened():
                print(f"  错误: 无法打开视频源: {self.source}")
                return False

            fps = reader.fps
            output_packets = []
            is_first_frame = True

            print("\n  开始传输 (总线模式)...")

            for frame in reader.get_frames(max_frames=max_frames):
                self.frame_idx += 1
                current_time = self.frame_idx / fps

                is_keyframe = (self.frame_idx == 1) or (self.frame_idx % self.keyframe_interval == 0)

                if is_keyframe:
                    self._handle_keyframe(frame, current_time, output_packets)
                else:
                    self._handle_event_frame(frame, current_time, output_packets)

                is_first_frame = False

                if show_visualization:
                    vis = self._create_bus_visualization(frame, is_keyframe)
                    display_frame(vis, "Bus Transmitter")
                    key = cv2.waitKey(30) & 0xFF
                    if key == 27:
                        print("\n  用户退出")
                        break

            cv2.destroyAllWindows()

            self._save_packets(output_packets)
            self._print_statistics()
            return True

    def _handle_keyframe(self, frame, current_time, output_packets):
        h264_data = self.h264_encoder.encode_i_frame(frame)
        packet = self.event_encoder.encode_keyframe(
            frame,
            frame_idx=self.frame_idx,
            i_frame_data=h264_data,
            timestamp_ms=int(current_time * 1000)
        )
        output_packets.append(packet)
        self.total_keyframes += 1
        self.total_h264_bytes += len(h264_data)
        print(f"  帧 {self.frame_idx}: [关键帧] H.264={len(h264_data)}B")

    def _handle_event_frame(self, frame, current_time, output_packets):
        events = self.event_detector.detect(
            frame,
            current_time=current_time,
            frame_idx=self.frame_idx
        )

        if not events.has_events:
            return

        dvs_events = events.events

        pushed = self.bus.push_events(dvs_events)
        if pushed < len(dvs_events):
            self.bus_stats.queue_overflow_count += (len(dvs_events) - pushed)

        self.bus_stats.total_events_pushed += pushed

        transactions = self.bus.transfer_batch(batch_size=pushed)
        self.bus_stats.update_from_bus(self.bus, self.bus.queue_size)

        packet = self.event_encoder.encode_events(
            events, frame,
            include_dvs=True,
            include_aer=True,
            timestamp_ms=int(current_time * 1000)
        )
        output_packets.append(packet)

        if self.frame_idx % 10 == 0:
            print(f"  帧 {self.frame_idx}: [事件帧] 事件={len(dvs_events)} "
                  f"入队={pushed} 传输={len(transactions)} "
                  f"利用率={self.bus.get_bus_stats()['utilization_percent']:.1f}%")

    def _create_bus_visualization(self, frame, is_keyframe):
        h, w = frame.shape[:2]
        if len(frame.shape) == 2:
            display = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        else:
            display = frame.copy()

        stats = self.bus.get_bus_stats()
        info_lines = [
            f"Frame: {self.frame_idx} | {'KEYFRAME' if is_keyframe else 'EVENT'}",
            f"Bus Transactions: {stats['transactions_count']}",
            f"Bus Data: {stats['total_bytes']}B | Util: {stats['utilization_percent']:.1f}%",
            f"Queue: {stats['queue_size']}/{self.bus.max_queue_size}",
        ]

        y_offset = 30
        for line in info_lines:
            display = put_text(display, line, (10, y_offset), color=(0, 255, 255))
            y_offset += 28

        return display

    def _save_packets(self, packets):
        data = {
            'width': self.width,
            'height': self.height,
            'packets': packets,
            'bus_stats': {
                'total_events_pushed': self.bus_stats.total_events_pushed,
                'total_transactions': self.bus_stats.total_transactions,
                'total_bytes_transferred': self.bus_stats.total_bytes_transferred,
                'queue_overflow_count': self.bus_stats.queue_overflow_count,
            },
            'keyframes': self.total_keyframes,
            'h264_bytes': self.total_h264_bytes,
        }
        with open(self.output_file, 'wb') as f:
            pickle.dump(data, f)
        print(f"\n  输出文件: {self.output_file} ({os.path.getsize(self.output_file):,}B)")

    def _print_statistics(self):
        print("\n" + "=" * 60)
        print("  发送端统计 - 总线输出模式")
        print("=" * 60)
        print(f"  总帧数: {self.frame_idx}")
        print(f"  关键帧: {self.total_keyframes}")
        print(f"  H.264数据: {self.total_h264_bytes:,}B")

        print(f"\n  总线输出统计:")
        print(f"    推入事件: {self.bus_stats.total_events_pushed}")
        print(f"    传输事务: {self.bus_stats.total_transactions}")
        print(f"    传输字节: {self.bus_stats.total_bytes_transferred:,}B")
        print(f"    吞吐量: {self.bus_stats.throughput_bytes_per_sec:.1f} B/s")
        print(f"    队列溢出: {self.bus_stats.queue_overflow_count}")
        print(f"    最大队列深度: {self.bus_stats.max_queue_depth}")

        self.bus.print_bus_stats()


class BusReceiver:
    """
    支持AER总线输入的接收端

    从总线和文件两个通道接收数据：
    1. 总线通道：通过AERBusBridge从总线读取事件并解码为DVSCoordinate列表
    2. 文件通道：读取关键帧数据

    数据流:
      事件文件 → 解析 → AERBusBridge.bus_to_events() → DVSCoordinate列表
              → EventFrameReconstructor.reconstruct_frame() → 重建帧
    """

    def __init__(self, input_file="output_bus.evs", width=640, height=480,
                 log_threshold=0.0784, reconstruction_mode="log_space"):
        self.input_file = input_file
        self.width = width
        self.height = height
        self.log_threshold = log_threshold
        self.reconstruction_mode = reconstruction_mode

        self.bridge = AERBusBridge(width, height)

        self.reconstructor = EventFrameReconstructor(
            width, height,
            log_threshold=log_threshold
        )

        self.current_frame = None

        self.total_received_events = 0
        self.total_received_keyframes = 0
        self.total_bus_transactions = 0

    def run(self, show_visualization=True):
        print("=" * 60)
        print("  接收端 - AER总线输入模式")
        print("=" * 60)
        print(f"  输入文件: {self.input_file}")
        print(f"  重建模式: {self.reconstruction_mode}")

        if not os.path.exists(self.input_file):
            print(f"  错误: 文件不存在: {self.input_file}")
            return False

        with open(self.input_file, 'rb') as f:
            data = pickle.load(f)

        packets = data['packets']
        print(f"  数据包: {len(packets)}")

        print("\n  开始接收 (总线模式)...")

        for i, packet in enumerate(packets):
            if packet.is_keyframe:
                self._receive_keyframe(packet, i)
            else:
                self._receive_event_frame(packet, i)

            if show_visualization and self.current_frame is not None:
                self._show_receiver_view(packet)
                key = cv2.waitKey(30) & 0xFF
                if key == 27:
                    print("\n  用户退出")
                    break

        cv2.destroyAllWindows()
        self._print_receiver_stats()
        return True

    def _receive_keyframe(self, packet, index):
        self.current_frame = self.reconstructor.decode_keyframe(packet.i_frame_data)
        if self.current_frame is None:
            self.current_frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        self.total_received_keyframes += 1
        if index < 5 or index % 30 == 0:
            print(f"  包 {index}: [关键帧] 重建参考帧")

    def _receive_event_frame(self, packet, index):
        if not packet.dvs_events or self.current_frame is None:
            return

        dvs_coords = [
            DVSCoordinate(x=e['x'], y=e['y'], event_type=e['event_type'])
            for e in packet.dvs_events
        ]

        pushed = self.bridge.events_to_bus(dvs_coords)
        self.total_received_events += pushed

        bus_events = self.bridge.bus_to_events(max_events=pushed)
        self.total_bus_transactions += len(bus_events)

        self.current_frame = self.reconstructor.reconstruct_frame(
            self.current_frame,
            bus_events,
            mode=self.reconstruction_mode
        )

        if index < 5 or index % 10 == 0:
            print(f"  包 {index}: [事件帧] 源事件={len(dvs_coords)} "
                  f"入队={pushed} 总线输出={len(bus_events)}")

    def _show_receiver_view(self, packet):
        display = self.current_frame.copy()
        display = put_text(display,
                           f"Frame: {packet.frame_idx} | {'KF' if packet.is_keyframe else 'EV'}",
                           (10, 30), color=(0, 255, 255))
        display = put_text(display,
                           f"Bus Events: {self.total_bus_transactions}",
                           (10, 60), color=(0, 255, 255))
        display_frame(display, "Bus Receiver")

    def _print_receiver_stats(self):
        print("\n" + "=" * 60)
        print("  接收端统计 - 总线输入模式")
        print("=" * 60)
        print(f"  接收关键帧: {self.total_received_keyframes}")
        print(f"  接收事件数: {self.total_received_events}")
        print(f"  总线传输事务: {self.total_bus_transactions}")
        self.bridge.bus.print_bus_stats()


class BusE2ESystem:
    """
    端到端AER总线通讯系统

    完整流程:
      [发送端: 视频 → 事件检测 → AER总线 → 文件存储]
                                    ↓
      [接收端: 文件读取 → AER总线桥 → 帧重建 → 显示]

    与无总线版本的关键区别：
    - 事件数据显式经过AER总线的Req/Ack握手传输
    - 发送端和接收端均追踪总线统计
    - 模拟真实神经形态硬件的数据通路
    """

    def __init__(self, source='video_test.mp4', output_file='output_bus.evs',
                 keyframe_interval=30, width=640, height=480,
                 threshold=20.0, refractory_period=0.005):
        self.source = source
        self.output_file = output_file
        self.keyframe_interval = keyframe_interval
        self.width = width
        self.height = height
        self.threshold = threshold
        self.refractory_period = refractory_period

    def run(self, max_frames=200):
        print("=" * 60)
        print("  端到端AER总线通讯系统")
        print("=" * 60)
        print(f"  输入源: {self.source}")
        print(f"  输出文件: {self.output_file}")

        print("\n" + "-" * 60)
        print("  阶段1: 发送端 (AER总线输出)")
        print("-" * 60)

        tx = BusTransmitter(
            source=self.source,
            output_file=self.output_file,
            keyframe_interval=self.keyframe_interval,
            width=self.width,
            height=self.height,
            threshold=self.threshold,
            refractory_period=self.refractory_period
        )
        tx.run(max_frames=max_frames, show_visualization=False)

        print("\n" + "-" * 60)
        print("  阶段2: 接收端 (AER总线输入)")
        print("-" * 60)

        rx = BusReceiver(
            input_file=self.output_file,
            width=self.width,
            height=self.height,
            log_threshold=self.threshold / 255.0
        )
        rx.run(show_visualization=True)

        self._print_e2e_summary(tx, rx)

    def _print_e2e_summary(self, tx: BusTransmitter, rx: BusReceiver):
        print("\n" + "=" * 60)
        print("  端到端总线系统 - 总结报告")
        print("=" * 60)
        print(f"\n  发送端:")
        print(f"    处理帧: {tx.frame_idx}")
        print(f"    关键帧: {tx.total_keyframes}")
        print(f"    推入总线事件: {tx.bus_stats.total_events_pushed}")
        print(f"    总线传输: {tx.bus_stats.total_transactions} 事务, "
              f"{tx.bus_stats.total_bytes_transferred:,}B")

        print(f"\n  接收端:")
        print(f"    关键帧: {rx.total_received_keyframes}")
        print(f"    总线接收事件: {rx.total_bus_transactions}")

        print(f"\n  文件: {self.output_file} "
              f"({os.path.getsize(self.output_file):,}B)")


def main():
    print("=" * 60)
    print("  事件型视频通讯 - AER总线系统")
    print("=" * 60)
    print("\n  模式选择:")
    print("    tx  - 总线发送端")
    print("    rx  - 总线接收端")
    print("    e2e - 端到端总线通讯")

    if len(sys.argv) > 1:
        mode = sys.argv[1]
    else:
        print("\n  选择模式 (默认 e2e): ")
        mode = input().strip() or "e2e"

    source = "video_test.mp4"
    if len(sys.argv) > 2:
        source = sys.argv[2]

    try:
        if mode == "tx":
            tx = BusTransmitter(source=source)
            tx.run(max_frames=300)
        elif mode == "rx":
            rx = BusReceiver(input_file="output_bus.evs")
            rx.run()
        elif mode == "e2e":
            e2e = BusE2ESystem(source=source)
            e2e.run(max_frames=200)
        else:
            print(f"  未知模式: {mode}，使用 e2e")
            e2e = BusE2ESystem(source=source)
            e2e.run(max_frames=200)

    except KeyboardInterrupt:
        print("\n  用户中断")
    except Exception as e:
        print(f"\n  错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
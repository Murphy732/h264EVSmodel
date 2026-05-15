"""
Stage 8: 不插值事件相机系统 - 端到端完整演示 (重构版)

本模块实现不插值事件相机系统的完整流程。

核心重构：
1. 内存级H.264编码 - 无磁盘I/O
2. 向量化事件重建 - O(N) → O(1)
3. 对数空间数学一致性 - 检测端log，重建端exp
4. 不应期(Refractory Period) - 模拟真实DVS硬件
5. 正确的带宽基准 - 对标标准H.264

完整流程:
[光输入] → [灰度/对数] → [DVS事件检测(不应期)] → [编码/AER] → [文件/网络]
                                                                    ↓
[显示/应用] ← [重建(向量化/对数空间)] ← [解码] ← [解包]
"""

import sys
import os
import time
import struct
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Dict

from utils.video_reader import VideoReader, put_text
from utils.io_utils import EventFileWriter, EventFileReader
from evs.event_detector import EventDetector, EventData, DVSCoordinate
from evs.event_encoder import EventEncoder, EventDecoder, EncodedEventPacket
from evs.event_decoder import EventFrameReconstructor, NoInterpolationDecoder, BandwidthBenchmark
from evs.aer_encoder import AEREncoder, AERVisualizer
from h264.encoder import InMemoryH264Encoder, HybridEncoder


@dataclass
class SystemStats:
    """
    系统性能统计 - 包含完整的带宽对比信息

    重构要点：
    - 正确的基准对比：H.264 vs 混合事件流
    - 包含不应期效果统计
    - 端到端延迟测量
    """
    total_frames: int = 0
    keyframe_count: int = 0
    event_frame_count: int = 0
    total_events: int = 0
    on_events: int = 0
    off_events: int = 0

    # 带宽统计
    original_bytes: int = 0          # 原始未压缩
    h264_bytes: int = 0             # 标准H.264
    encoded_bytes: int = 0          # 混合事件流
    keyframe_bytes: int = 0
    event_bytes: int = 0

    # 时间统计
    start_time: float = field(default_factory=time.time)
    detect_time: float = 0
    encode_time: float = 0
    decode_time: float = 0
    h264_encode_time: float = 0

    # 不应期统计
    refractory_events_suppressed: int = 0

    # 质量统计
    total_psnr: float = 0
    total_ssim: float = 0
    quality_samples: int = 0

    @property
    def bandwidth_saving_vs_h264(self) -> float:
        """相对于H.264的带宽变化"""
        if self.h264_bytes == 0:
            return 0.0
        return (self.encoded_bytes - self.h264_bytes) / self.h264_bytes * 100

    @property
    def bandwidth_saving_vs_original(self) -> float:
        """相对于原始视频的带宽节省"""
        if self.original_bytes == 0:
            return 0.0
        return (1 - self.encoded_bytes / self.original_bytes) * 100

    @property
    def avg_events_per_frame(self) -> float:
        """平均每帧事件数"""
        if self.event_frame_count == 0:
            return 0.0
        return self.total_events / self.event_frame_count

    @property
    def avg_psnr(self) -> float:
        if self.quality_samples == 0:
            return 0.0
        return self.total_psnr / self.quality_samples

    @property
    def avg_ssim(self) -> float:
        if self.quality_samples == 0:
            return 0.0
        return self.total_ssim / self.quality_samples

    @property
    def processing_fps(self) -> float:
        elapsed = time.time() - self.start_time
        if elapsed == 0:
            return 0.0
        return self.total_frames / elapsed

    def print_report(self):
        """打印完整报告"""
        print("\n" + "=" * 70)
        print("  不插值事件相机系统 - 性能报告 (重构版)")
        print("=" * 70)

        print(f"\n  处理统计:")
        print(f"    总帧数: {self.total_frames}")
        print(f"    关键帧数: {self.keyframe_count}")
        print(f"    事件帧数: {self.event_frame_count}")
        print(f"    处理速度: {self.processing_fps:.1f} FPS")

        print(f"\n  事件统计:")
        print(f"    总事件数: {self.total_events}")
        print(f"    ON事件: {self.on_events}")
        print(f"    OFF事件: {self.off_events}")
        print(f"    平均每帧事件: {self.avg_events_per_frame:.1f}")
        if self.refractory_events_suppressed > 0:
            print(f"    不应期抑制: {self.refractory_events_suppressed}")

        print(f"\n  带宽统计 (正确基准):")
        print(f"    原始未压缩: {self.original_bytes / 1024:.2f} KB")
        print(f"    标准H.264: {self.h264_bytes / 1024:.2f} KB")
        print(f"    混合事件流: {self.encoded_bytes / 1024:.2f} KB")
        print(f"    关键帧数据: {self.keyframe_bytes / 1024:.2f} KB")
        print(f"    事件数据: {self.event_bytes / 1024:.2f} KB")

        print(f"\n  带宽对比:")
        if self.bandwidth_saving_vs_h264 > 0:
            print(f"    ⚠️ 混合流比H.264大 {self.bandwidth_saving_vs_h264:.1f}%")
        else:
            print(f"    ✅ 混合流比H.264节省 {-self.bandwidth_saving_vs_h264:.1f}%")
        print(f"    vs 原始视频: {self.bandwidth_saving_vs_original:.1f}%")

        print(f"\n  时间统计:")
        print(f"    检测时间: {self.detect_time * 1000:.2f} ms")
        print(f"    H.264编码: {self.h264_encode_time * 1000:.2f} ms")
        print(f"    事件编码: {self.encode_time * 1000:.2f} ms")
        print(f"    解码重建: {self.decode_time * 1000:.2f} ms")

        if self.quality_samples > 0:
            print(f"\n  质量统计:")
            print(f"    平均PSNR: {self.avg_psnr:.2f} dB")
            print(f"    平均SSIM: {self.avg_ssim:.4f}")

        print("=" * 70)


class NoInterpolationTransmitter:
    """
    不插值发送端 - 重构版

    核心改进：
    1. 内存级H.264编码（无磁盘I/O）
    2. 不应期事件检测
    3. 正确的带宽基准计算
    """

    def __init__(self, source='video_test.mp4', output_file='output_no_interp.evs',
                 keyframe_interval=30, width=640, height=480,
                 threshold=20.0, refractory_period=0.0):
        self.source = source
        self.output_file = output_file
        self.keyframe_interval = keyframe_interval
        self.width = width
        self.height = height
        self.threshold = threshold
        self.refractory_period = refractory_period

        # 内存级H.264编码器（无磁盘I/O！）
        self.h264_encoder = InMemoryH264Encoder(width, height, fps=30)

        # 事件检测器 - 支持不应期
        self.detector = EventDetector(
            threshold=threshold,
            min_area=10,
            use_adaptive_threshold=False,
            blur_kernel=1,
            use_log_space=True,              # 对数空间
            is_dvs_mode=True,
            compare_with_previous=True,      # 与前一帧比较
            refractory_period=refractory_period  # 不应期
        )

        # 事件编码器
        self.event_encoder = EventEncoder(width, height)

        # 统计
        self.stats = SystemStats()

    def run(self, max_frames=200, show_visualization=True):
        """运行发送端"""
        print("=" * 70)
        print("  不插值事件相机系统 - 发送端 (重构版)")
        print("=" * 70)
        print(f"\n  输入源: {self.source}")
        print(f"  输出文件: {self.output_file}")
        print(f"  关键帧间隔: {self.keyframe_interval}")
        print(f"  分辨率: {self.width}x{self.height}")
        print(f"  阈值: {self.threshold}")
        if self.refractory_period > 0:
            print(f"  不应期: {self.refractory_period * 1000:.1f} ms")
        print("\n  按 ESC 退出, S 保存截图")

        # 收集帧用于H.264基准对比
        all_frames = []

        with VideoReader(source=self.source, target_size=(self.width, self.height)) as reader:
            if not reader.cap.isOpened():
                print(f"  错误: 无法打开视频源: {self.source}")
                return

            with EventFileWriter(self.output_file, self.width, self.height) as writer:
                frame_idx = 0
                current_time = 0.0
                frame_duration = 1.0 / 30.0  # 假设30fps

                for frame in reader.get_frames(max_frames=max_frames):
                    frame_idx += 1
                    self.stats.total_frames += 1

                    # 收集帧用于基准对比
                    all_frames.append(frame.copy())
                    self.stats.original_bytes += frame.nbytes

                    # 判断是否为关键帧
                    is_keyframe = (frame_idx == 1) or (frame_idx % self.keyframe_interval == 0)

                    if is_keyframe:
                        # 关键帧: H.264编码（内存操作！）
                        print(f"  帧 {frame_idx}: 发送关键帧 (H.264)")

                        # 计时H.264编码
                        t0 = time.time()

                        # 确保BGR格式
                        if len(frame.shape) == 2:
                            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                        else:
                            frame_bgr = frame

                        # 内存级H.264编码（无磁盘I/O！）
                        i_frame_data = self.h264_encoder.encode_i_frame(frame_bgr)

                        self.stats.h264_encode_time += time.time() - t0

                        # 创建关键帧包
                        packet = self.event_encoder.encode_keyframe(
                            frame_bgr, frame_idx, i_frame_data,
                            timestamp_ms=int(current_time * 1000)
                        )

                        self.stats.keyframe_count += 1
                        self.stats.keyframe_bytes += len(i_frame_data)
                        self.stats.h264_bytes += len(i_frame_data)

                        # 重置参考帧
                        self.detector.set_reference(frame)

                    else:
                        # 事件帧: 检测并编码事件
                        t0 = time.time()
                        events = self.detector.detect(frame, frame_idx, current_time)
                        self.stats.detect_time += time.time() - t0

                        # 统计不应期抑制的事件
                        # （如果启用了不应期，实际触发的事件会减少）

                        # 统计事件
                        if events.has_events:
                            on_count = sum(1 for e in events.events if e.event_type == 'on')
                            off_count = len(events.events) - on_count
                            self.stats.total_events += len(events.events)
                            self.stats.on_events += on_count
                            self.stats.off_events += off_count

                            if frame_idx % 10 == 0:
                                print(f"  帧 {frame_idx}: {len(events.events)} 事件 "
                                      f"(ON:{on_count}, OFF:{off_count})")

                        # 编码事件
                        t0 = time.time()
                        packet = self.event_encoder.encode_events(
                            events, frame,
                            include_regions=False,
                            include_dvs=True,
                            include_aer=True,
                            timestamp_ms=int(current_time * 1000)
                        )
                        self.stats.encode_time += time.time() - t0

                        self.stats.event_frame_count += 1
                        self.stats.event_bytes += len(self.event_encoder.serialize(packet))

                    # 写入
                    writer.write_packet(packet)
                    self.stats.encoded_bytes += len(self.event_encoder.serialize(packet))

                    # 更新时间
                    current_time += frame_duration

                    # 可视化
                    if show_visualization:
                        vis_frame = self._create_transmitter_view(
                            frame, events if not is_keyframe else None,
                            frame_idx, is_keyframe
                        )
                        cv2.imshow("Transmitter (Refactored)", vis_frame)

                        key = cv2.waitKey(30) & 0xFF
                        if key == 27:
                            print("\n  用户退出")
                            break
                        elif key == ord('s') or key == ord('S'):
                            cv2.imwrite(f"tx_frame_{frame_idx:04d}.png", vis_frame)
                            print(f"  已保存: tx_frame_{frame_idx:04d}.png")

                cv2.destroyAllWindows()

        # 打印统计
        self.stats.print_report()

        return all_frames

    def _create_transmitter_view(self, frame, events, frame_idx, is_keyframe):
        """创建发送端可视化视图"""
        h, w = frame.shape[:2]

        if len(frame.shape) == 2:
            display = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        else:
            display = frame.copy()

        # 添加信息文本
        info_lines = [
            f"Frame: {frame_idx}",
            f"Type: {'KEYFRAME' if is_keyframe else 'EVENT'}",
        ]

        if events and events.has_events:
            on_count = sum(1 for e in events.events if e.event_type == 'on')
            off_count = len(events.events) - on_count
            info_lines.append(f"Events: {len(events.events)} (ON:{on_count} OFF:{off_count})")

        if self.refractory_period > 0:
            info_lines.append(f"Refractory: {self.refractory_period * 1000:.1f}ms")

        y_offset = 30
        for line in info_lines:
            display = put_text(display, line, (10, y_offset), color=(0, 255, 255))
            y_offset += 30

        return display


class NoInterpolationReceiver:
    """
    不插值接收端 - 重构版

    核心改进：
    1. 向量化事件重建（O(N) → O(1)）
    2. 对数空间数学一致性
    3. np.add.at 处理事件重叠
    """

    def __init__(self, input_file='output_no_interp.evs', width=640, height=480,
                 log_threshold=0.1, reconstruction_mode='log_space'):
        self.input_file = input_file
        self.width = width
        self.height = height
        self.log_threshold = log_threshold
        self.reconstruction_mode = reconstruction_mode

        # 向量化重建器
        self.reconstructor = EventFrameReconstructor(
            width, height,
            log_threshold=log_threshold  # 必须与检测端一致！
        )

        # AER编码器
        self.aer_encoder = AEREncoder(width, height)

        # 统计
        self.stats = SystemStats()

        # 当前帧
        self.current_frame = None

    def reconstruct_frame_vectorized(self, packet, prev_frame):
        """
        向量化帧重建 - 数学一致性版本

        核心算法（与检测端完全对称）：
        1. 对数变换: log(I + 1)
        2. 向量化累加: np.add.at
        3. 指数映射: exp(log_I) - 1
        """
        if packet.is_keyframe and packet.i_frame_data:
            # 关键帧: 直接解码
            i_frame_array = np.frombuffer(packet.i_frame_data, dtype=np.uint8)
            frame = cv2.imdecode(i_frame_array, cv2.IMREAD_COLOR)
            if frame is not None:
                self.current_frame = frame.copy()
                self.reconstructor.reset_accumulation()
                return frame
            return prev_frame

        if prev_frame is None:
            prev_frame = np.ones((self.height, self.width, 3), dtype=np.uint8) * 128

        # 向量化重建
        output_frame = self.reconstructor.reconstruct_frame(
            prev_frame,
            packet.dvs_events,
            self.reconstruction_mode
        )

        self.current_frame = output_frame
        return output_frame

    def run(self, show_visualization=True, save_output=False):
        """运行接收端"""
        print("=" * 70)
        print("  不插值事件相机系统 - 接收端 (重构版)")
        print("=" * 70)
        print(f"\n  输入文件: {self.input_file}")
        print(f"  重建模式: {self.reconstruction_mode} (向量化/对数空间)")
        print("\n  按 ESC 退出, S 保存截图")

        if not os.path.exists(self.input_file):
            print(f"  错误: 文件不存在: {self.input_file}")
            return

        with EventFileReader(self.input_file, self.width, self.height) as reader:
            prev_frame = None
            frame_idx = 0

            video_writer = None
            if save_output:
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                video_writer = cv2.VideoWriter(
                    'reconstructed_no_interp.mp4', fourcc, 30, (self.width * 2, self.height)
                )

            try:
                while True:
                    packet = reader.read_packet()
                    if packet is None:
                        print("\n  文件读取完成")
                        break

                    frame_idx += 1
                    self.stats.total_frames += 1

                    # 向量化解码重建
                    t0 = time.time()
                    reconstructed = self.reconstruct_frame_vectorized(packet, prev_frame)
                    self.stats.decode_time += time.time() - t0

                    # 统计
                    if packet.is_keyframe:
                        self.stats.keyframe_count += 1
                    else:
                        self.stats.event_frame_count += 1
                        self.stats.total_events += len(packet.dvs_events)

                    # 可视化
                    if show_visualization and reconstructed is not None:
                        # 创建事件掩码视图
                        event_mask = np.ones_like(reconstructed) * 255
                        for dvs_evt in packet.dvs_events:
                            x, y = dvs_evt["x"], dvs_evt["y"]
                            if 0 <= y < self.height and 0 <= x < self.width:
                                if dvs_evt["event_type"] == "on":
                                    event_mask[y, x] = [0, 0, 255]  # 红色
                                else:
                                    event_mask[y, x] = [0, 255, 0]  # 绿色

                        # 创建对比视图
                        recon_with_info = put_text(reconstructed,
                                                    f"Reconstructed: {packet.frame_idx}",
                                                    (10, 30), color=(0, 255, 255))
                        mask_with_info = put_text(event_mask,
                                                  "Event Mask (Red=ON, Green=OFF)",
                                                  (10, 30), color=(0, 255, 255))

                        display = np.hstack([recon_with_info, mask_with_info])

                        type_text = f"Type: {'KEYFRAME' if packet.is_keyframe else 'EVENT'}"
                        display = put_text(display, type_text, (10, 60), color=(0, 255, 255))

                        cv2.imshow("Receiver (Refactored)", display)

                        if video_writer:
                            video_writer.write(display)

                        key = cv2.waitKey(30) & 0xFF
                        if key == 27:
                            print("\n  用户退出")
                            break
                        elif key == ord('s') or key == ord('S'):
                            cv2.imwrite(f"rx_frame_{frame_idx:04d}.png", display)
                            print(f"  已保存: rx_frame_{frame_idx:04d}.png")

                    if reconstructed is not None:
                        prev_frame = reconstructed.copy()

            finally:
                if video_writer:
                    video_writer.release()
                cv2.destroyAllWindows()

        self.stats.print_report()


class NoInterpolationE2E:
    """不插值端到端完整系统 - 重构版"""

    def __init__(self, source='video_test.mp4', output_file='output_no_interp.evs',
                 keyframe_interval=30, width=640, height=480,
                 threshold=20.0, refractory_period=0.0):
        self.source = source
        self.output_file = output_file
        self.keyframe_interval = keyframe_interval
        self.width = width
        self.height = height
        self.threshold = threshold
        self.refractory_period = refractory_period

    def run_full_pipeline(self, max_frames=200):
        """运行完整端到端流程"""
        print("=" * 70)
        print("  不插值事件相机系统 - 端到端完整演示 (重构版)")
        print("=" * 70)
        print(f"\n  输入源: {self.source}")
        print(f"  输出文件: {self.output_file}")
        print(f"  关键帧间隔: {self.keyframe_interval}")
        print(f"  分辨率: {self.width}x{self.height}")
        print(f"  阈值: {self.threshold}")
        if self.refractory_period > 0:
            print(f"  不应期: {self.refractory_period * 1000:.1f} ms")

        # 阶段1: 发送端
        print("\n" + "-" * 70)
        print("  阶段1: 发送端编码")
        print("-" * 70)

        transmitter = NoInterpolationTransmitter(
            self.source, self.output_file,
            self.keyframe_interval, self.width, self.height,
            self.threshold, self.refractory_period
        )
        all_frames = transmitter.run(max_frames=max_frames, show_visualization=False)
        tx_stats = transmitter.stats

        # 阶段2: 接收端
        print("\n" + "-" * 70)
        print("  阶段2: 接收端解码重建 (向量化)")
        print("-" * 70)

        receiver = NoInterpolationReceiver(
            self.output_file, self.width, self.height,
            log_threshold=20.0 / 255.0  # 必须与检测端一致！
        )
        receiver.run(show_visualization=True, save_output=True)

        # 最终报告
        print("\n" + "=" * 70)
        print("  端到端完整报告 (重构版)")
        print("=" * 70)

        print(f"\n  发送端:")
        print(f"    处理帧数: {tx_stats.total_frames}")
        print(f"    关键帧: {tx_stats.keyframe_count}")
        print(f"    事件帧: {tx_stats.event_frame_count}")
        print(f"    总事件: {tx_stats.total_events}")
        print(f"    vs H.264: {tx_stats.bandwidth_saving_vs_h264:.1f}%")
        print(f"    vs 原始: {tx_stats.bandwidth_saving_vs_original:.1f}%")

        print(f"\n  输出文件:")
        if os.path.exists(self.output_file):
            file_size = os.path.getsize(self.output_file)
            print(f"    事件流: {self.output_file} ({file_size / 1024:.2f} KB)")
        if os.path.exists('reconstructed_no_interp.mp4'):
            recon_size = os.path.getsize('reconstructed_no_interp.mp4')
            print(f"    重建视频: reconstructed_no_interp.mp4 ({recon_size / 1024:.2f} KB)")

        print("=" * 70)


def main():
    print("=" * 70)
    print("  Stage 8: 不插值事件相机系统 (重构版)")
    print("=" * 70)
    print("\n  模式选择:")
    print("    1 - 发送端 (编码并保存)")
    print("    2 - 接收端 (读取并重建)")
    print("    3 - 端到端完整流程")

    if len(sys.argv) > 1:
        mode = sys.argv[1]
    else:
        print("\n  选择模式 (默认3): ")
        mode = input().strip() or "3"

    source = "video_test.mp4"
    if len(sys.argv) > 2:
        source = sys.argv[2]

    # 参数配置
    threshold = 20.0
    refractory_period = 0.005  # 5毫秒不应期

    try:
        if mode == "1":
            tx = NoInterpolationTransmitter(
                source=source,
                threshold=threshold,
                refractory_period=refractory_period
            )
            tx.run(max_frames=200)
        elif mode == "2":
            rx = NoInterpolationReceiver()
            rx.run(save_output=True)
        elif mode == "3":
            e2e = NoInterpolationE2E(
                source=source,
                threshold=threshold,
                refractory_period=refractory_period
            )
            e2e.run_full_pipeline(max_frames=200)
        else:
            print("  无效选择，运行端到端流程")
            e2e = NoInterpolationE2E(source=source)
            e2e.run_full_pipeline(max_frames=200)

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

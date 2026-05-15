"""
Stage 6: 完整系统演示 - 发送端+接收端重构版

本模块演示完整的事件型视频通讯系统，包含独立的发送端和接收端，
确保与Stage 8的端到端系统完全兼容。

核心功能：
- 发送端：内存级H.264编码 + 不应期事件检测
- 接收端：向量化事件重建（对数空间）
- 文件存储模式：.evs文件格式
- 网络传输模式：TCP socket（可选）

输出规范（与Stage 8兼容）：
- 发送端: EncodedEventPacket -> 文件/网络
- 接收端: 文件/网络 -> 重建帧
- 统计信息: 带宽、PSNR、SSIM

使用示例：
    # 发送端模式
    python examples/stage6_full_system.py 1 video_test.mp4
    
    # 接收端模式
    python examples/stage6_full_system.py 2
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
import pickle
from utils.video_reader import VideoReader, display_frame, put_text
from evs.event_detector import EventDetector, DVSCoordinate
from evs.event_encoder import EventEncoder
from evs.event_decoder import EventFrameReconstructor
from h264.encoder import InMemoryH264Encoder


class EventVideoTransmitter:
    """
    事件视频发送端 - 与Stage 8的NoInterpolationTransmitter逻辑等价
    
    功能：
    - 读取视频帧
    - 事件检测（带不应期）
    - H.264关键帧编码（内存级）
    - 事件编码（DVS + AER）
    - 输出到文件或网络
    """
    
    def __init__(self, source="0", output_file="output.evs", keyframe_interval=30):
        """
        初始化发送端
        
        参数:
            source: 视频源
            output_file: 输出文件路径
            keyframe_interval: 关键帧间隔
        """
        self.source = source
        self.output_file = output_file
        self.keyframe_interval = keyframe_interval
        self.frame_idx = 0
        
        # 统计信息
        self.total_events = 0
        self.total_keyframes = 0
        self.total_h264_bytes = 0
        self.total_dvs_bytes = 0
    
    def run_transmission(self):
        """
        运行发送端 - 读取视频、检测事件、编码并输出
        """
        print("=" * 60)
        print("  Stage 6: 发送端")
        print("=" * 60)
        print(f"  视频源: {self.source}")
        print(f"  输出文件: {self.output_file}")
        print(f"  关键帧间隔: {self.keyframe_interval}")
        
        with VideoReader(source=self.source, target_size=(640, 480)) as reader:
            if not reader.cap.isOpened():
                print(f"  错误: 无法打开视频源: {self.source}")
                return False
            
            print(f"  视频信息: {reader.original_size} @ {reader.fps:.1f} FPS")
            
            width, height = reader.target_size
            fps = reader.fps
            
            # 初始化组件（与Stage 8配置一致）
            detector = EventDetector(
                threshold=20.0,
                min_area=0,
                use_adaptive_threshold=False,
                blur_kernel=1,
                use_log_space=True,
                compare_with_previous=True,
                refractory_period=0.005,
                is_dvs_mode=True
            )
            
            h264_encoder = InMemoryH264Encoder(width, height, fps=fps)
            event_encoder = EventEncoder(width, height)
            
            # 存储数据包
            output_packets = []
            is_first_frame = True
            
            print("\n  开始传输...")
            
            for frame in reader.get_frames(max_frames=300):
                self.frame_idx += 1
                current_time = self.frame_idx / fps
                
                # 判断是否为关键帧
                is_keyframe = (self.frame_idx % self.keyframe_interval == 1)
                
                # 事件检测（带不应期）
                events = detector.detect(frame, current_time=current_time, frame_idx=self.frame_idx)
                self.total_events += len(events.regions)
                
                # 编码
                if is_keyframe or is_first_frame:
                    # 关键帧：H.264内存编码
                    h264_data = h264_encoder.encode_i_frame(frame)
                    packet = event_encoder.encode_keyframe(
                        frame,
                        frame_idx=self.frame_idx,
                        i_frame_data=h264_data,
                        timestamp_ms=int(current_time * 1000)
                    )
                    self.total_keyframes += 1
                    self.total_h264_bytes += len(h264_data)
                else:
                    # 事件帧：仅事件数据
                    packet = event_encoder.encode_events(
                        events,
                        frame,
                        include_aer=True,
                        timestamp_ms=int(current_time * 1000)
                    )
                    if packet.aer_events is not None:
                        self.total_dvs_bytes += len(packet.aer_events)
                
                output_packets.append(packet)
                is_first_frame = False
                
                # 可视化
                info_frame = put_text(frame.copy(), f"帧: {self.frame_idx}", (10, 30), color=(0, 255, 255))
                info_frame = put_text(info_frame, f"事件: {len(events.regions)}", (10, 60), color=(0, 255, 255))
                info_frame = put_text(info_frame, f"关键帧: {'是' if is_keyframe else '否'}", (10, 90), color=(0, 255, 255))
                info_frame = put_text(info_frame, f"抑制: {events.suppressed_count}", (10, 120), color=(0, 255, 255))
                
                display_frame(info_frame, "Stage 6: 发送端")
                
                key = cv2.waitKey(30) & 0xFF
                if key == 27:
                    print("\n  用户退出")
                    break
            
            cv2.destroyAllWindows()
            
            # 保存到文件
            print(f"\n  保存到文件: {self.output_file}")
            self._save_packets(output_packets)
            
            # 打印统计
            self._print_stats()
            
            return True
    
    def _save_packets(self, packets):
        """
        保存数据包到文件
        
        参数:
            packets: EncodedEventPacket列表
        """
        data = {
            'width': 640,
            'height': 480,
            'packets': packets,
            'stats': {
                'total_frames': self.frame_idx,
                'total_events': self.total_events,
                'total_keyframes': self.total_keyframes,
                'total_h264_bytes': self.total_h264_bytes,
                'total_dvs_bytes': self.total_dvs_bytes,
            }
        }
        
        with open(self.output_file, 'wb') as f:
            pickle.dump(data, f)
        
        file_size = os.path.getsize(self.output_file)
        print(f"  文件大小: {file_size:,} 字节")
    
    def _print_stats(self):
        """打印发送端统计信息"""
        print("\n" + "=" * 60)
        print("  发送端统计")
        print("=" * 60)
        print(f"  总帧数: {self.frame_idx}")
        print(f"  关键帧数: {self.total_keyframes}")
        print(f"  总事件数: {self.total_events}")
        print(f"  H.264数据: {self.total_h264_bytes:,} 字节")
        print(f"  DVS事件数据: {self.total_dvs_bytes:,} 字节")
        print(f"  总数据: {self.total_h264_bytes + self.total_dvs_bytes:,} 字节")


class EventVideoReceiver:
    """
    事件视频接收端 - 与Stage 8的NoInterpolationReceiver逻辑等价
    
    功能：
    - 从文件或网络读取数据包
    - 数据包解码
    - 向量化事件重建（对数空间）
    - 可视化显示
    """
    
    def __init__(self, input_file="output.evs"):
        """
        初始化接收端
        
        参数:
            input_file: 输入文件路径
        """
        self.input_file = input_file
    
    def run_reception(self):
        """
        运行接收端 - 读取文件、解码、重建并显示
        """
        print("=" * 60)
        print("  Stage 6: 接收端")
        print("=" * 60)
        print(f"  输入文件: {self.input_file}")
        
        if not os.path.exists(self.input_file):
            print(f"  错误: 文件不存在: {self.input_file}")
            return False
        
        # 读取文件
        print("  读取文件...")
        with open(self.input_file, 'rb') as f:
            data = pickle.load(f)
        
        width = data['width']
        height = data['height']
        packets = data['packets']
        
        print(f"  文件大小: {os.path.getsize(self.input_file):,} 字节")
        print(f"  数据包数: {len(packets)}")
        
        # 初始化重建器
        reconstructor = EventFrameReconstructor(
            width=width,
            height=height,
            log_threshold=20.0 / 255.0
        )
        
        reconstructed = None
        
        print("\n  开始重建...")
        
        for i, packet in enumerate(packets):
            if packet.is_keyframe:
                # 关键帧：解码I帧
                reconstructed = reconstructor.decode_keyframe(packet.i_frame_data)
                if reconstructed is None:
                    reconstructed = np.zeros((height, width, 3), dtype=np.uint8)
            else:
                # 事件帧：向量化对数空间重建
                if reconstructed is not None and packet.dvs_events:
                    dvs_coords = [
                        DVSCoordinate(x=e['x'], y=e['y'], event_type=e['event_type'])
                        for e in packet.dvs_events
                    ]
                    reconstructed = reconstructor.reconstruct_frame(
                        prev_frame=reconstructed,
                        events=dvs_coords,
                        reconstruction_mode="log_space"
                    )
            
            if reconstructed is not None:
                # 显示
                info_frame = put_text(reconstructed.copy(), 
                    f"帧: {packet.frame_idx} | 事件: {len(packet.dvs_events)}", 
                    (10, 30), color=(0, 255, 255))
                info_frame = put_text(info_frame, 
                    f"关键帧: {'是' if packet.is_keyframe else '否'}", 
                    (10, 60), color=(0, 255, 255))
                
                display_frame(info_frame, "Stage 6: 接收端")
                
                key = cv2.waitKey(30) & 0xFF
                if key == 27:
                    print("\n  用户退出")
                    break
        
        cv2.destroyAllWindows()
        print("\n  接收完成")
        
        return True


def main():
    """主函数 - 选择发送端或接收端模式"""
    print("=" * 60)
    print("  Stage 6: 完整事件型视频通讯系统")
    print("=" * 60)
    print("\n  模式选择：")
    print("    1. 发送端 (Transmitter) - 读取视频，生成.evs文件")
    print("    2. 接收端 (Receiver) - 读取.evs文件，重建视频")
    print("\n  按 ESC 退出")
    
    # 从命令行参数获取模式
    mode = "1"
    if len(sys.argv) > 1:
        mode = sys.argv[1]
    
    source = "0"
    if len(sys.argv) > 2:
        source = sys.argv[2]
    
    try:
        if mode == "1":
            # 发送端模式
            transmitter = EventVideoTransmitter(
                source=source,
                output_file="output.evs",
                keyframe_interval=30
            )
            transmitter.run_transmission()
            
        elif mode == "2":
            # 接收端模式
            receiver = EventVideoReceiver(
                input_file="output.evs"
            )
            receiver.run_reception()
            
        else:
            print(f"  错误: 未知模式: {mode}")
            
    except KeyboardInterrupt:
        print("\n  用户中断")
    except Exception as e:
        print(f"  错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

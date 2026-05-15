"""
Stage 5: 完整事件型视频通讯流水线 - 重构版

本模块演示完整的事件型视频通讯流水线，确保与Stage 8的端到端系统
完全兼容。所有组件使用相同的配置和接口。

核心功能：
- 内存级H.264编码（PyAV，无磁盘I/O）
- 不应期事件检测（模拟真实DVS硬件）
- 向量化事件重建（NumPy，O(1)操作）
- 对数空间数学一致性（检测端log，重建端exp）
- 正确的带宽基准（对标标准H.264）

输出规范（与Stage 8兼容）：
- 事件数据: EventResult + EncodedEventPacket
- H.264数据: bytes类型（内存编码）
- 重建帧: (H, W, 3) uint8 BGR格式

使用示例：
    python examples/stage5_full_pipeline.py video_test.mp4
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
from utils.video_reader import VideoReader, display_frame, put_text
from evs.event_detector import EventDetector, DVSCoordinate
from evs.event_encoder import EventEncoder, EncodedEventPacket
from evs.event_decoder import EventFrameReconstructor
from h264.encoder import InMemoryH264Encoder


def demo_full_pipeline(source="0", max_frames=200):
    """
    完整流水线演示 - 展示端到端事件型视频通讯
    
    此演示验证Stage 5的所有组件与Stage 8完全一致。
    
    参数:
        source: 视频源（"0"为摄像头，或文件路径）
        max_frames: 最大处理帧数
    """
    print("=" * 60)
    print("  Stage 5: 完整事件型视频通讯流水线")
    print("=" * 60)
    print(f"  视频源: {source}")
    print(f"  最大帧数: {max_frames}")
    print("\n  组件配置：")
    print("    - EventDetector: 阈值20.0, 不应期5ms, 对数空间")
    print("    - InMemoryH264Encoder: PyAV内存编码")
    print("    - EventEncoder: DVS+AER编码")
    print("    - EventFrameReconstructor: 向量化对数空间重建")
    print("\n  按 ESC 退出")
    
    with VideoReader(source=source, target_size=(640, 480)) as reader:
        if not reader.cap.isOpened():
            print(f"  错误: 无法打开视频源: {source}")
            return
        
        print(f"\n  视频信息: {reader.original_size} @ {reader.fps:.1f} FPS")
        
        width, height = reader.target_size
        fps = reader.fps
        
        # 初始化所有组件（与Stage 8配置一致）
        detector = EventDetector(
            threshold=20.0,
            min_area=0,
            use_adaptive_threshold=False,
            blur_kernel=1,
            use_log_space=True,
            compare_with_previous=True,
            refractory_period=0.005,  # 5ms不应期
            is_dvs_mode=True
        )
        
        h264_encoder = InMemoryH264Encoder(width, height, fps=fps)
        event_encoder = EventEncoder(width, height)
        reconstructor = EventFrameReconstructor(
            width=width,
            height=height,
            log_threshold=20.0 / 255.0  # 归一化阈值
        )
        
        # 统计信息
        total_events = 0
        total_keyframes = 0
        total_h264_bytes = 0
        total_dvs_bytes = 0
        frame_idx = 0
        keyframe_interval = 30
        is_first_frame = True
        reconstructed = None
        
        for frame in reader.get_frames(max_frames=max_frames):
            frame_idx += 1
            current_time = frame_idx / fps
            
            # 每keyframe_interval帧发送一次关键帧
            is_keyframe = (frame_idx % keyframe_interval == 1)
            
            # 事件检测（带不应期）
            events = detector.detect(frame, current_time=current_time, frame_idx=frame_idx)
            total_events += len(events.regions)
            
            # 编码
            if is_keyframe or is_first_frame:
                # 关键帧：H.264内存编码
                h264_data = h264_encoder.encode_i_frame(frame)
                packet = event_encoder.encode_keyframe(
                    frame,
                    frame_idx=frame_idx,
                    i_frame_data=h264_data,
                    timestamp_ms=int(current_time * 1000)
                )
                total_keyframes += 1
                total_h264_bytes += len(h264_data)
                reconstructed = frame.copy()
            else:
                # 事件帧：仅事件数据
                packet = event_encoder.encode_events(
                    events,
                    frame,
                    include_aer=True,
                    timestamp_ms=int(current_time * 1000)
                )
                
                # 统计AER数据大小
                if packet.aer_events is not None:
                    total_dvs_bytes += len(packet.aer_events)
                
                # 接收端重建（使用与Stage 8一致的接口）
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
            
            is_first_frame = False
            
            # 计算PSNR
            if reconstructed is not None:
                diff = np.mean((frame.astype(float) - reconstructed.astype(float)) ** 2)
                psnr = 10 * np.log10(255**2 / diff) if diff > 0 else float('inf')
            else:
                psnr = 0
            
            # 创建可视化
            h, w = frame.shape[:2]
            grid = np.zeros((h * 2, w, 3), dtype=np.uint8)
            grid[:h, :] = frame
            grid[h:, :] = reconstructed if reconstructed is not None else np.zeros_like(frame)
            
            # 添加信息
            grid = put_text(grid, f"帧: {frame_idx} | 事件: {len(events.regions)}", (10, 30), color=(0, 255, 255))
            grid = put_text(grid, f"关键帧: {'是' if is_keyframe else '否'} | 抑制: {events.suppressed_count}", (10, 60), color=(0, 255, 255))
            grid = put_text(grid, f"原始帧", (10, h // 2), color=(255, 255, 255))
            grid = put_text(grid, f"重建帧 | PSNR: {psnr:.1f}dB", (10, h + h // 2), color=(255, 255, 255))
            
            display_frame(grid, "Stage 5: 完整流水线")
            
            key = cv2.waitKey(30) & 0xFF
            if key == 27:
                print("\n  用户退出")
                break
        
        cv2.destroyAllWindows()
        
        # 打印统计信息
        _print_pipeline_stats(frame_idx, total_events, total_keyframes, 
                            total_h264_bytes, total_dvs_bytes)


def _print_pipeline_stats(total_frames, total_events, total_keyframes, 
                         total_h264_bytes, total_dvs_bytes):
    """
    打印流水线统计信息
    
    参数:
        total_frames: 总帧数
        total_events: 总事件数
        total_keyframes: 关键帧数
        total_h264_bytes: H.264数据总大小
        total_dvs_bytes: DVS事件数据总大小
    """
    print("\n" + "=" * 60)
    print("  流水线统计")
    print("=" * 60)
    print(f"  总帧数: {total_frames}")
    print(f"  关键帧数: {total_keyframes}")
    print(f"  总事件数: {total_events}")
    print(f"  平均每帧事件: {total_events / total_frames:.0f}" if total_frames > 0 else "  N/A")
    print(f"\n  带宽统计:")
    print(f"    H.264数据: {total_h264_bytes:,} 字节")
    print(f"    DVS事件数据: {total_dvs_bytes:,} 字节")
    print(f"    总数据: {total_h264_bytes + total_dvs_bytes:,} 字节")
    print(f"    平均每帧: {(total_h264_bytes + total_dvs_bytes) / total_frames:.0f} 字节" if total_frames > 0 else "    N/A")


if __name__ == "__main__":
    source = "0"
    if len(sys.argv) > 1:
        source = sys.argv[1]
    
    try:
        demo_full_pipeline(source, max_frames=200)
    except KeyboardInterrupt:
        print("\n  用户中断")
    except Exception as e:
        print(f"  错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cv2.destroyAllWindows()

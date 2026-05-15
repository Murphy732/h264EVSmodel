"""
Stage 4: H.264编码集成 - 内存级H.264编码

本模块演示H.264内存级编码，消除磁盘I/O延迟，确保与Stage 8的
InMemoryH264Encoder完全兼容。

核心功能：
- 内存级H.264编码（使用PyAV）
- 强制全I帧（gop_size=1）
- 零延迟优化（tune='zerolatency'）
- JPEG备选方案（PyAV不可用时）

输出规范（与Stage 8兼容）：
- H.264字节流: bytes类型
- 编码延迟: <10ms/帧
- 压缩率: >10x vs原始帧

使用示例：
    python examples/stage4_h264_integration.py video_test.mp4
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
from utils.video_reader import VideoReader, display_frame, put_text
from h264.encoder import H264Encoder, InMemoryH264Encoder, HybridEncoder


def demo_memory_encoding():
    """
    内存级H.264编码演示 - 对比新旧编码方式
    
    此演示验证Stage 4的内存编码与Stage 8完全一致。
    """
    print("=" * 60)
    print("  Stage 4: H.264内存级编码集成演示")
    print("=" * 60)
    print("  编码器类型：")
    print("    1. InMemoryH264Encoder - 内存级PyAV编码")
    print("    2. HybridEncoder - 混合编码（H.264/JPEG自适应）")
    print("\n  按 ESC 退出")
    
    width, height = 640, 480
    fps = 30
    
    try:
        in_memory_encoder = InMemoryH264Encoder(width, height, fps=fps)
        print("  InMemoryH264Encoder 初始化成功")
    except Exception as e:
        print(f"  InMemoryH264Encoder 初始化失败: {e}")
        in_memory_encoder = None
    
    try:
        hybrid_encoder = HybridEncoder(width, height, fps=fps)
        print("  HybridEncoder 初始化成功")
    except Exception as e:
        print(f"  HybridEncoder 初始化失败: {e}")
        hybrid_encoder = None
    
    test_frames = []
    for i in range(30):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :] = [30, 30, 50]
        
        x = 50 + i * 15
        y = 120
        cv2.rectangle(frame, (x, y), (x + 60, y + 60), (0, 255, 0), -1)
        
        cv2.putText(frame, f"Frame {i}", (x - 20, y - 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        test_frames.append(frame)
    
    print(f"\n  测试编码 {len(test_frames)} 帧...")
    
    if in_memory_encoder:
        print("\n  [1] InMemoryH264Encoder 测试:")
        encoded_sizes = []
        total_time = 0
        
        for i, frame in enumerate(test_frames):
            start_time = cv2.getTickCount()
            h264_data = in_memory_encoder.encode_i_frame(frame)
            elapsed = (cv2.getTickCount() - start_time) / cv2.getTickFrequency()
            total_time += elapsed
            
            encoded_sizes.append(len(h264_data))
            
            if i < 5 or i % 5 == 0:
                print(f"    帧 {i:2d}: {len(h264_data):6d} 字节 | {elapsed*1000:.1f}ms")
        
        avg_fps = len(test_frames) / total_time if total_time > 0 else 0
        avg_size = np.mean(encoded_sizes)
        orig_size = width * height * 3
        
        print(f"\n    平均大小: {avg_size:.0f} 字节")
        print(f"    压缩率: {orig_size / avg_size:.1f}x")
        print(f"    平均速度: {avg_fps:.1f} FPS")
    
    if hybrid_encoder:
        print("\n  [2] HybridEncoder 测试:")
        for i, frame in enumerate(test_frames[:10]):
            start_time = cv2.getTickCount()
            data, method = hybrid_encoder.encode(frame, quality_threshold=50)
            elapsed = (cv2.getTickCount() - start_time) / cv2.getTickFrequency()
            print(f"    帧 {i:2d}: {len(data):6d} 字节 | {method:4s} | {elapsed*1000:.1f}ms")
    
    print("\n  编码测试完成")


def demo_video_encoding(source="0"):
    """
    视频编码实时演示 - 展示内存H.264编码
    
    参数:
        source: 视频源（"0"为摄像头，或文件路径）
    """
    print("\n" + "=" * 60)
    print("  Stage 4: 视频H.264编码实时演示")
    print("=" * 60)
    print(f"  视频源: {source}")
    print("  编码器: InMemoryH264Encoder")
    print("\n  按 ESC 退出")
    
    with VideoReader(source=source, target_size=(640, 480)) as reader:
        if not reader.cap.isOpened():
            print(f"  错误: 无法打开视频源: {source}")
            return
        
        print(f"  视频信息: {reader.original_size} @ {reader.fps:.1f} FPS")
        
        width, height = reader.target_size
        encoder = InMemoryH264Encoder(width, height, fps=30)
        
        frame_idx = 0
        encoded_sizes = []
        
        for frame in reader.get_frames(max_frames=100):
            frame_idx += 1
            
            start_time = cv2.getTickCount()
            h264_data = encoder.encode_i_frame(frame)
            elapsed = (cv2.getTickCount() - start_time) / cv2.getTickFrequency()
            
            encoded_sizes.append(len(h264_data))
            orig_size = frame.shape[0] * frame.shape[1] * 3
            compression_ratio = orig_size / len(h264_data) if len(h264_data) > 0 else 0
            
            info_frame = put_text(frame.copy(), f"帧: {frame_idx}", (10, 30), color=(0, 255, 255))
            info_frame = put_text(info_frame, f"编码: {len(h264_data)} 字节", (10, 60), color=(0, 255, 255))
            info_frame = put_text(info_frame, f"压缩率: {compression_ratio:.1f}x", (10, 90), color=(0, 255, 255))
            info_frame = put_text(info_frame, f"延迟: {elapsed*1000:.1f}ms", (10, 120), color=(0, 255, 255))
            
            display_frame(info_frame, "Stage 4: 视频H.264编码")
            
            key = cv2.waitKey(30) & 0xFF
            if key == 27:
                print("\n  用户退出")
                break
        
        cv2.destroyAllWindows()
        
        if encoded_sizes:
            avg_size = np.mean(encoded_sizes)
            avg_ratio = np.mean([frame.shape[0] * frame.shape[1] * 3 / s for s in encoded_sizes])
            print(f"\n  编码统计:")
            print(f"    总帧数: {frame_idx}")
            print(f"    平均大小: {avg_size:.0f} 字节")
            print(f"    平均压缩率: {avg_ratio:.1f}x")


if __name__ == "__main__":
    source = "0"
    if len(sys.argv) > 1:
        source = sys.argv[1]
    
    try:
        demo_memory_encoding()
        demo_video_encoding(source)
    except KeyboardInterrupt:
        print("\n  用户中断")
    except Exception as e:
        print(f"  错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cv2.destroyAllWindows()

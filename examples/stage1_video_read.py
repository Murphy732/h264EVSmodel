"""
Stage 1: 视频读取与预处理 - 标准化光输入模块

本模块负责从视频源（摄像头或文件）读取帧，并提供标准化预处理输出，
确保与后续Stage（特别是Stage 8的事件检测器）的接口完全兼容。

核心功能：
- 视频帧读取与尺寸调整
- 灰度转换（事件检测的基础）
- 标准化输出格式（640x480 BGR/灰度）

输出规范（与Stage 8兼容）：
- 彩色帧: (H, W, 3) uint8, BGR格式
- 灰度帧: (H, W) uint8
- 目标尺寸: 640x480（可配置）

使用示例：
    # 读取视频文件
    python examples/stage1_video_read.py video_test.mp4
    
    # 读取摄像头
    python examples/stage1_video_read.py 0
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
from utils.video_reader import VideoReader, FramePreprocessor, display_frame, save_frame, put_text


def create_comparison_grid(frames, labels):
    """
    创建对比网格显示 - 将多帧图像拼接为2xN网格
    
    参数:
        frames: 帧列表，每帧为(H, W, 3) BGR图像
        labels: 每帧的标签文本列表
    
    返回:
        拼接后的网格图像
    """
    h, w = frames[0].shape[:2]
    num_frames = len(frames)
    cols = 2
    rows = (num_frames + 1) // cols
    grid_h = h * rows
    grid_w = w * cols
    grid = np.zeros((grid_h, grid_w, 3), dtype=np.uint8)
    
    for i, (frame, label) in enumerate(zip(frames, labels)):
        row = i // cols
        col = i % cols
        y = row * h
        x = col * w
        # 确保帧是BGR格式
        if len(frame.shape) == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        grid[y:y+h, x:x+w] = frame
        # 添加标签
        put_text(grid, label, (x + 10, y + 30), color=(0, 255, 255))
    
    return grid


def preprocess_for_stage8(frame, target_size=(640, 480)):
    """
    标准化预处理 - 确保输出与Stage 8的EventDetector兼容
    
    处理流程：
    1. 尺寸调整到目标大小
    2. 确保BGR格式
    3. 生成灰度版本
    
    参数:
        frame: 输入帧（任意尺寸，BGR或灰度）
        target_size: 目标尺寸（宽, 高）
    
    返回:
        dict: {
            'bgr': (H, W, 3) BGR彩色帧,
            'gray': (H, W) 灰度帧,
            'denoised': (H, W) 去噪后灰度帧
        }
    """
    # 尺寸调整
    if frame.shape[1] != target_size[0] or frame.shape[0] != target_size[1]:
        frame = cv2.resize(frame, target_size)
    
    # 确保BGR格式
    if len(frame.shape) == 2:
        bgr = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    else:
        bgr = frame.copy()
    
    # 灰度转换
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    
    # 轻微去噪（3x3高斯，不损失细节）
    denoised = cv2.GaussianBlur(gray, (3, 3), 0)
    
    return {
        'bgr': bgr,
        'gray': gray,
        'denoised': denoised
    }


def demo_video_read(source="./video_test.mp4"):
    """
    视频读取演示 - 展示标准化预处理输出
    
    此演示验证Stage 1的输出格式与Stage 8的输入要求完全兼容。
    
    参数:
        source: 视频源（"0"为摄像头，或文件路径）
    """
    print("=" * 60)
    print("  Stage 1: 视频读取与标准化预处理")
    print("=" * 60)
    print(f"  视频源: {source}")
    print(f"  目标尺寸: 640x480")
    print(f"  输出格式: BGR (640,480,3) + Gray (640,480)")
    print("\n  按 ESC 退出，按 S 保存当前帧")
    
    # 使用VideoReader确保与Stage 8相同的读取方式
    with VideoReader(source=source, target_size=(640, 480)) as reader:
        if not reader.cap.isOpened():
            print(f"  错误: 无法打开视频源: {source}")
            return
        
        print(f"  原始尺寸: {reader.original_size}")
        print(f"  帧率: {reader.fps:.1f} FPS")
        print(f"  总帧数: {reader.frame_count}")
        
        frame_idx = 0
        processed_frames = []  # 存储预处理结果
        
        for frame in reader.get_frames(max_frames=100):
            frame_idx += 1
            
            # 标准化预处理（与Stage 8输入要求一致）
            result = preprocess_for_stage8(frame)
            processed_frames.append(result)
            
            # 创建对比视图
            frames = [
                put_text(result['bgr'].copy(), f"原始 BGR", (10, 30), color=(0, 255, 255)),
                put_text(cv2.cvtColor(result['gray'], cv2.COLOR_GRAY2BGR), f"灰度 Gray", (10, 30), color=(0, 255, 255)),
                put_text(cv2.cvtColor(result['denoised'], cv2.COLOR_GRAY2BGR), f"去噪 Denoised", (10, 30), color=(0, 255, 255)),
            ]
            
            grid = create_comparison_grid(
                frames,
                ["原始 BGR", "灰度 Gray", "去噪 Denoised"]
            )
            
            # 添加信息文本
            info_text = f"帧: {frame_idx} | 尺寸: {result['bgr'].shape[1]}x{result['bgr'].shape[0]}"
            put_text(grid, info_text, (10, grid.shape[0] - 20), color=(255, 255, 255))
            
            display_frame(grid, "Stage 1: 视频读取与预处理")
            
            # 用户控制
            key = cv2.waitKey(30) & 0xFF
            if key == 27:  # ESC退出
                print("\n  用户退出")
                break
            elif key == ord('s') or key == ord('S'):
                save_frame(result['bgr'], f"stage1_bgr_{frame_idx:04d}.png")
                save_frame(result['gray'], f"stage1_gray_{frame_idx:04d}.png")
                print(f"  已保存帧 #{frame_idx}")
        
        cv2.destroyAllWindows()
        print(f"\n  共处理 {frame_idx} 帧")
        
        # 验证输出格式兼容性
        if processed_frames:
            sample = processed_frames[0]
            print(f"\n  输出格式验证:")
            print(f"    BGR: {sample['bgr'].shape} dtype={sample['bgr'].dtype}")
            print(f"    Gray: {sample['gray'].shape} dtype={sample['gray'].dtype}")
            print(f"    Denoised: {sample['denoised'].shape} dtype={sample['denoised'].dtype}")
            print(f"    ✓ 与Stage 8 EventDetector输入兼容")


if __name__ == "__main__":
    # 从命令行参数获取视频源，默认为测试视频
    source = "video_test.mp4"
    if len(sys.argv) > 1:
        source = sys.argv[1]
    
    try:
        demo_video_read(source)
    except KeyboardInterrupt:
        print("\n  用户中断")
    except Exception as e:
        print(f"  错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cv2.destroyAllWindows()

"""
Stage 3: 帧间插值方案对比 - 不插值优先基准

本模块对比多种插值方案，以不插值（NoInterpolator）为首要基准，
确保与Stage 8的不插值事件重建策略完全兼容。

核心功能：
- 不插值作为首要基准（与Stage 8一致）
- 线性插值对比方案
- 光流插值对比方案
- 正确的质量评估（PSNR/SSIM）

输出规范（与Stage 8兼容）：
- 不插值: 直接复制前一帧
- 线性插值: 加权混合两帧
- 评估指标: PSNR (dB), SSIM

使用示例：
    python examples/stage3_interpolation_comparison.py video_test.mp4
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
from utils.video_reader import VideoReader, display_frame, put_text
from interpolation.base import Interpolator
from interpolation.no_interpolation import NoInterpolator
from interpolation.linear import LinearInterpolator
from interpolation.optical_flow import OpticalFlowInterpolator
from visualization.comparison_viz import InterpolationComparison, calculate_psnr


def generate_test_sequence():
    """
    生成测试序列 - 用于插值方案对比
    
    返回:
        list: 帧列表，每帧为(H, W, 3) BGR图像
    """
    print("  生成测试序列...")
    h, w = 240, 320
    frames = []
    
    for i in range(5):
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[:, :] = [30, 30, 50]
        
        x1 = 50 + i * 30
        y1 = 80
        cv2.rectangle(frame, (x1, y1), (x1 + 60, y1 + 60), (0, 255, 0), -1)
        
        x2 = 250 - i * 20
        y2 = 150
        cv2.circle(frame, (x2, y2), 35, (0, 0, 255), -1)
        
        frames.append(frame)
    
    return frames


def demo_interpolation_comparison():
    """
    插值方案对比演示 - 以不插值为首要基准
    
    此演示验证Stage 3的插值方案与Stage 8的重建策略兼容。
    """
    print("=" * 60)
    print("  Stage 3: 帧间插值方案对比演示")
    print("=" * 60)
    print("  对比方案：")
    print("    1. 不插值（NoInterpolator）- 首要基准")
    print("    2. 线性插值（LinearInterpolator）")
    print("    3. 光流插值（OpticalFlowInterpolator）")
    print("\n  按 ESC 退出")
    
    interpolators = [
        NoInterpolator(),
        LinearInterpolator(),
        OpticalFlowInterpolator(method="farneback"),
    ]
    
    comparison = InterpolationComparison(interpolators)
    test_frames = generate_test_sequence()
    
    for i in range(len(test_frames) - 2):
        frame1 = test_frames[i]
        ground_truth = test_frames[i + 1]
        frame2 = test_frames[i + 2]
        
        print(f"\n  测试: 帧 {i} -> 帧 {i+1} (GT) -> 帧 {i+2}")
        
        results = comparison.compare(frame1, frame2, ground_truth, t=0.5)
        
        for result in results:
            print(f"    {result['name']}: PSNR={result['psnr']:.2f}dB")
        
        grid = InterpolationComparison.create_comparison_grid(
            frame1, frame2, ground_truth, results, t=0.5
        )
        
        display_frame(grid, "Stage 3: 插值方案对比")
        key = cv2.waitKey(1500) & 0xFF
        if key == 27:
            break
    
    cv2.destroyAllWindows()


def demo_video_interpolation(source="0"):
    """
    视频插值实时演示 - 展示不插值优先策略
    
    参数:
        source: 视频源（"0"为摄像头，或文件路径）
    """
    print("\n" + "=" * 60)
    print("  Stage 3: 视频插值实时演示")
    print("=" * 60)
    print(f"  视频源: {source}")
    print("  方案：")
    print("    1. 不插值（NoInterpolator）- 默认")
    print("    2. 线性插值（LinearInterpolator）")
    print("    3. 光流插值（OpticalFlowInterpolator）")
    print("\n  按 1-3 切换方案，按 ESC 退出")
    
    interpolators = [
        NoInterpolator(),
        LinearInterpolator(),
        OpticalFlowInterpolator(method="farneback"),
    ]
    
    current_idx = 0
    
    with VideoReader(source=source, target_size=(640, 480)) as reader:
        if not reader.cap.isOpened():
            print(f"  错误: 无法打开视频源: {source}")
            return
        
        print(f"  视频信息: {reader.original_size} @ {reader.fps:.1f} FPS")
        
        prev_frame = None
        frame_idx = 0
        
        for frame in reader.get_frames(max_frames=200):
            frame_idx += 1
            
            if prev_frame is None:
                prev_frame = frame
                continue
            
            # 获取当前插值器
            interpolator = interpolators[current_idx]
            
            # 执行插值
            start_time = cv2.getTickCount()
            interpolated = interpolator.interpolate(prev_frame, frame, t=0.5)
            elapsed = (cv2.getTickCount() - start_time) / cv2.getTickFrequency()
            fps = 1.0 / elapsed if elapsed > 0 else 0
            
            # 创建3列对比视图
            h, w = frame.shape[:2]
            grid = np.zeros((h, w * 3, 3), dtype=np.uint8)
            grid[:, :w] = prev_frame
            grid[:, w:w*2] = interpolated
            grid[:, w*2:] = frame
            
            # 添加标签
            label = f"{interpolator.name} | FPS: {fps:.1f}"
            grid = put_text(grid, label, (10, 30), color=(0, 255, 255))
            grid = put_text(grid, "Prev", (10, h - 20), color=(255, 255, 255))
            grid = put_text(grid, "Interpolated", (w + 10, h - 20), color=(255, 255, 255))
            grid = put_text(grid, "Next", (w*2 + 10, h - 20), color=(255, 255, 255))
            
            display_frame(grid, "Stage 3: 实时插值演示")
            
            # 用户控制
            key = cv2.waitKey(30) & 0xFF
            if key == 27:
                print("\n  用户退出")
                break
            elif ord('1') <= key <= ord('3'):
                current_idx = key - ord('1')
                print(f"  切换到: {interpolators[current_idx].name}")
            
            prev_frame = frame
        
        cv2.destroyAllWindows()


if __name__ == "__main__":
    source = "0"
    if len(sys.argv) > 1:
        source = sys.argv[1]
    
    try:
        demo_interpolation_comparison()
        demo_video_interpolation(source)
    except KeyboardInterrupt:
        print("\n  用户中断")
    except Exception as e:
        print(f"  错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cv2.destroyAllWindows()

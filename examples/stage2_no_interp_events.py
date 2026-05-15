"""
Stage 2: 不插值的事件检测演示 - 带不应期和对数空间一致性

本模块演示事件检测的核心算法，确保与Stage 8的EventDetector完全兼容。

核心功能：
- 不应期事件检测（模拟真实DVS硬件）
- 对数空间处理（Weber-Fechner定律）
- 与前一帧比较（增量检测）
- 可视化：原图 + 事件叠加 + 纯事件 + 统计图表

输出规范（与Stage 8兼容）：
- 事件数据: EventResult对象，包含事件坐标和极性
- 不应期抑制: 抑制高频噪声（默认5ms）
- 阈值: 20.0（对数空间）

使用示例：
    python examples/stage2_no_interp_events.py video_test.mp4
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from utils.video_reader import VideoReader, display_frame, put_text
from evs.event_detector import EventDetector, EventStats
from visualization.event_viz import EventVisualizer


def demo_event_detection(source="0"):
    """
    事件检测演示 - 展示不应期和对数空间一致性
    
    此演示验证Stage 2的事件检测逻辑与Stage 8完全一致。
    
    参数:
        source: 视频源（"0"为摄像头，或文件路径）
    """
    print("=" * 60)
    print("  Stage 2: 不插值的事件检测演示")
    print("=" * 60)
    print(f"  视频源: {source}")
    print(f"  阈值: 20.0")
    print(f"  不应期: 5ms")
    print(f"  对数空间: 是")
    print("\n  控制说明：")
    print("  - ESC: 退出")
    print("  - R: 重置参考帧")
    print("  - S: 保存截图")
    print("  - 1-9: 调整播放速度")
    print("  - P: 暂停/继续")
    print("  - F: 重新开始")
    
    # 创建与Stage 8完全兼容的EventDetector
    detector = EventDetector(
        threshold=20.0,           # 与Stage 8一致
        min_area=0,               # 像素级事件，无需区域过滤
        use_adaptive_threshold=False,  # 固定阈值
        blur_kernel=1,            # 无模糊
        use_log_space=True,       # 对数空间
        compare_with_previous=True,  # 与前一帧比较
        refractory_period=0.005,  # 5ms不应期（与Stage 8一致）
        is_dvs_mode=True
    )
    
    # 播放速度控制
    speed_levels = [1000, 500, 300, 200, 100, 50, 30, 20, 10]
    current_speed = 4  # 默认中等速度
    paused = False
    
    # 统计图表数据
    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    plt.ion()
    
    while True:
        with VideoReader(source=source, target_size=(640, 480)) as reader:
            if not reader.cap.isOpened():
                print(f"  错误: 无法打开视频源: {source}")
                return
            
            print(f"  视频信息: {reader.original_size} @ {reader.fps:.1f} FPS")
            
            frame_idx = 0
            reset_reference = True
            event_counts = []
            
            for frame in reader.get_frames():
                frame_idx += 1
                
                if reset_reference:
                    detector.set_reference(frame)
                    print(f"  已设置第 {frame_idx} 帧为参考帧")
                    reset_reference = False
                    continue
                
                # 获取时间戳（微秒）
                current_time = (frame_idx - 1) / reader.fps
                
                # 事件检测（带不应期）
                events = detector.detect(frame, current_time=current_time, frame_idx=frame_idx)
                
                # 记录事件统计
                event_counts.append(len(events.regions))
                
                # 创建可视化
                comparison_view = EventVisualizer.create_comparison_view(
                    frame, events, show_heatmap=True, show_mask=True
                )
                
                # 添加控制信息
                speed_text = f"速度: {current_speed + 1}/9"
                status_text = f"{'暂停' if paused else '播放'}"
                events_text = f"事件: {len(events.regions)}"
                suppressed_text = f"抑制: {events.suppressed_count}"
                
                info_frame = put_text(comparison_view, speed_text, (10, 60), color=(0, 255, 255))
                info_frame = put_text(info_frame, status_text, (10, 90), color=(0, 255, 255))
                info_frame = put_text(info_frame, events_text, (10, 120), color=(0, 255, 255))
                info_frame = put_text(info_frame, suppressed_text, (10, 150), color=(0, 255, 255))
                
                # 显示主窗口
                display_frame(info_frame, "Stage 2: 事件检测")
                
                # 更新统计图表（每5帧更新一次）
                if frame_idx % 5 == 0:
                    _update_stats_charts(axes, event_counts, frame_idx)
                
                # 用户控制
                wait_time = speed_levels[current_speed] if not paused else 0
                key = cv2.waitKey(wait_time) & 0xFF
                
                if key == 27:  # ESC退出
                    print("\n  用户退出")
                    plt.close(fig)
                    cv2.destroyAllWindows()
                    return
                elif key == ord('r') or key == ord('R'):
                    detector.set_reference(frame)
                    print(f"  已更新参考帧为第 {frame_idx} 帧")
                elif key == ord('s') or key == ord('S'):
                    save_path = f"stage2_events_{frame_idx:04d}.png"
                    cv2.imwrite(save_path, comparison_view)
                    print(f"  已保存截图: {save_path}")
                elif ord('1') <= key <= ord('9'):
                    current_speed = key - ord('1')
                    print(f"  速度调整: {current_speed + 1}/9")
                elif key == ord('p') or key == ord('P'):
                    paused = not paused
                    print(f"  {'暂停' if paused else '继续'}")
                elif key == ord('f') or key == ord('F'):
                    print("  重新开始")
                    break
            
            # 播放结束后的等待
            print("\n  播放结束！按 ESC 退出，按 F 重新开始")
            _show_final_stats(event_counts)
            
            while True:
                key = cv2.waitKey(0) & 0xFF
                if key == 27:
                    print("  用户退出")
                    plt.close(fig)
                    cv2.destroyAllWindows()
                    return
                elif key == ord('f') or key == ord('F'):
                    print("  重新开始")
                    break
        
        if key != ord('f') and key != ord('F'):
            break
    
    plt.close(fig)
    cv2.destroyAllWindows()


def _update_stats_charts(axes, event_counts, frame_idx):
    """
    更新统计图表
    
    参数:
        axes: matplotlib子图数组
        event_counts: 每帧事件计数列表
        frame_idx: 当前帧索引
    """
    if len(event_counts) < 2:
        return
    
    for ax in axes:
        ax.clear()
    
    # 事件数量随时间变化
    axes[0].plot(event_counts, color='blue', linewidth=1)
    axes[0].set_title('Events per Frame')
    axes[0].set_xlabel('Frame')
    axes[0].set_ylabel('Count')
    axes[0].grid(True, alpha=0.3)
    
    # 事件分布直方图
    axes[1].hist(event_counts[-50:], bins=20, color='green', alpha=0.7)
    axes[1].set_title('Event Distribution (last 50)')
    axes[1].set_xlabel('Count')
    axes[1].set_ylabel('Frequency')
    axes[1].grid(True, alpha=0.3)
    
    # 累积事件数
    cumulative = np.cumsum(event_counts)
    axes[2].plot(cumulative, color='red', linewidth=1)
    axes[2].set_title('Cumulative Events')
    axes[2].set_xlabel('Frame')
    axes[2].set_ylabel('Total')
    axes[2].grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.pause(0.01)


def _show_final_stats(event_counts):
    """
    显示最终统计信息
    
    参数:
        event_counts: 每帧事件计数列表
    """
    if not event_counts:
        return
    
    total = sum(event_counts)
    avg = np.mean(event_counts)
    max_events = max(event_counts)
    min_events = min(event_counts)
    
    print("\n  === 事件检测统计 ===")
    print(f"  总事件区域: {total}")
    print(f"  平均每帧: {avg:.1f}")
    print(f"  最大: {max_events}")
    print(f"  最小: {min_events}")


if __name__ == "__main__":
    source = "0"
    if len(sys.argv) > 1:
        source = sys.argv[1]
    
    try:
        demo_event_detection(source)
    except KeyboardInterrupt:
        print("\n  用户中断")
    except Exception as e:
        print(f"  错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cv2.destroyAllWindows()

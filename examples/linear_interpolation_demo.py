
"""
线性插值效果演示
使用 video_test.mp4 作为输入，展示线性插值
"""

import sys
import os
import cv2
import numpy as np
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.video_reader import VideoReader
from interpolation.linear import LinearInterpolator
from interpolation.no_interpolation import NoInterpolator
from interpolation.optical_flow import OpticalFlowInterpolator


def create_comparison_view(frame1, frame2, interpolated, t=0.5):
    """
    创建对比视图:
    [  帧1  |  插值帧  |  帧2  ]
    """
    h, w = frame1.shape[:2]

    # 确保3通道
    if len(frame1.shape) == 2:
        frame1 = cv2.cvtColor(frame1, cv2.COLOR_GRAY2BGR)
    if len(frame2.shape) == 2:
        frame2 = cv2.cvtColor(frame2, cv2.COLOR_GRAY2BGR)
    if len(interpolated.shape) == 2:
        interpolated = cv2.cvtColor(interpolated, cv2.COLOR_GRAY2BGR)

    # 拼接
    comparison = np.hstack([frame1, interpolated, frame2])

    # 添加标签
    cv2.putText(comparison, "Frame 1", (20, h - 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    cv2.putText(comparison, f"Interpolated (t={t:.2f})", (w + 20, h - 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    cv2.putText(comparison, "Frame 2", (2 * w + 20, h - 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

    return comparison


def create_multi_t_comparison(frame1, frame2, ts=[0.25, 0.5, 0.75]):
    """
    创建多t值的对比
    [ 帧1 | t=0.25 | t=0.5 | t=0.75 | 帧2 ]
    """
    interpolator = LinearInterpolator()
    interpolated_frames = []

    for t in ts:
        interpolated = interpolator(frame1, frame2, t)
        interpolated_frames.append(interpolated)

    # 拼接
    frames_to_stack = [frame1] + interpolated_frames + [frame2]
    comparison = np.hstack(frames_to_stack)

    h, w = frame1.shape[:2]
    cv2.putText(comparison, "F1", (20, h - 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

    for i, t in enumerate(ts):
        x_pos = w * (i + 1) + 20
        cv2.putText(comparison, f"t={t:.2f}", (x_pos, h - 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

    cv2.putText(comparison, "F2", (w * (len(ts) + 1) + 20, h - 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

    return comparison


def demo_single_pair():
    """演示: 两帧之间的单帧插值"""
    print("=" * 60)
    print("  演示 1: 两帧之间的线性插值 (t=0.5)")
    print("=" * 60)

    video_path = "video_test.mp4"
    interpolator = LinearInterpolator()

    with VideoReader(source=video_path, target_size=(640, 480)) as reader:
        # 获取两帧
        frame1 = None
        frame2 = None

        for i, frame in enumerate(reader.get_frames(max_frames=10)):
            if i == 0:
                frame1 = frame.copy()
            if i == 3:
                frame2 = frame.copy()
                break

        if frame1 is None or frame2 is None:
            print("无法获取足够的帧!")
            return

        print("")
        print("  帧 1 和 帧 2 已读取")
        print("  正在计算插值...")

        # 插值
        interpolated = interpolator(frame1, frame2, t=0.5)

        # 创建对比视图
        comparison = create_comparison_view(frame1, frame2, interpolated, t=0.5)

        print("  显示对比 (按 ESC 退出, S 保存)")

        while True:
            cv2.imshow("Linear Interpolation Demo - Single Pair", comparison)
            key = cv2.waitKey(30) & 0xFF

            if key == 27:
                break
            elif key == ord('s') or key == ord('S'):
                cv2.imwrite("linear_interpolation_single.png", comparison)
                print("  已保存: linear_interpolation_single.png")

        cv2.destroyAllWindows()


def demo_multi_t():
    """演示: 两帧之间的多t值插值 (0.25, 0.5, 0.75)"""
    print("\n" + "=" * 60)
    print("  演示 2: 多t值线性插值 (0.25, 0.5, 0.75)")
    print("=" * 60)

    video_path = "video_test.mp4"

    with VideoReader(source=video_path, target_size=(640, 480)) as reader:
        frame1 = None
        frame2 = None

        for i, frame in enumerate(reader.get_frames(max_frames=10)):
            if i == 0:
                frame1 = frame.copy()
            if i == 3:
                frame2 = frame.copy()
                break

        if frame1 is None or frame2 is None:
            print("无法获取足够的帧!")
            return

        print("  正在计算多个 t 值的插值...")

        comparison = create_multi_t_comparison(frame1, frame2)

        print("  显示对比 (按 ESC 退出, S 保存)")

        while True:
            cv2.imshow("Linear Interpolation Demo - Multi t", comparison)
            key = cv2.waitKey(30) & 0xFF

            if key == 27:
                break
            elif key == ord('s') or key == ord('S'):
                cv2.imwrite("linear_interpolation_multi_t.png", comparison)
                print("  已保存: linear_interpolation_multi_t.png")

        cv2.destroyAllWindows()


def demo_video_sequence():
    """演示: 视频序列实时插值"""
    print("\n" + "=" * 60)
    print("  演示 3: 视频序列实时插值 (按 1-4 改变t值)")
    print("=" * 60)
    print("\n  按键说明:")
    print("    1-4: t = 0.25, 0.5, 0.75, 0.9")
    print("    ESC: 退出")
    print("    S: 保存当前帧")
    print("")

    video_path = "video_test.mp4"
    interpolator = LinearInterpolator()

    with VideoReader(source=video_path, target_size=(640, 480)) as reader:
        previous_frame = None
        current_t = 0.5
        frame_count = 0

        for frame in reader.get_frames():
            frame_count += 1

            if previous_frame is None:
                previous_frame = frame.copy()
                continue

            # 插值
            interpolated = interpolator(previous_frame, frame, t=current_t)

            # 对比视图
            comparison = create_comparison_view(previous_frame, frame, interpolated, t=current_t)

            # 显示
            cv2.imshow("Linear Interpolation Demo - Real-time", comparison)

            key = cv2.waitKey(30) & 0xFF
            if key == 27:
                break
            elif key == ord('s') or key == ord('S'):
                filename = f"linear_interpolation_frame_{frame_count:04d}.png"
                cv2.imwrite(filename, comparison)
                print(f"  已保存: {filename}")
            elif key == ord('1'):
                current_t = 0.25
                print(f"  t 设为: {current_t}")
            elif key == ord('2'):
                current_t = 0.5
                print(f"  t 设为: {current_t}")
            elif key == ord('3'):
                current_t = 0.75
                print(f"  t 设为: {current_t}")
            elif key == ord('4'):
                current_t = 0.9
                print(f"  t 设为: {current_t}")

            previous_frame = frame.copy()

        cv2.destroyAllWindows()


def main():
    print("=" * 60)
    print("  线性插值效果演示程序")
    print("  使用 video_test.mp4 作为输入")
    print("=" * 60)
    print("\n请选择演示:")
    print("  1 - 两帧之间的单帧插值 (t=0.5)")
    print("  2 - 两帧之间的多t值插值 (0.25, 0.5, 0.75)")
    print("  3 - 视频序列实时插值")

    if len(sys.argv) > 1:
        choice = sys.argv[1]
    else:
        print("\n输入你的选择 (默认为3):")
        choice = input().strip() or "3"

    try:
        if choice == "1":
            demo_single_pair()
        elif choice == "2":
            demo_multi_t()
        elif choice == "3":
            demo_video_sequence()
        else:
            print("无效选择，默认运行演示3")
            demo_video_sequence()
    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()


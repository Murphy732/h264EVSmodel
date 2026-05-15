
"""
线性插值效果演示 - 直接生成保存图片
使用 video_test.mp4 作为输入，输出对比图
"""

import sys
import os
import cv2
import numpy as np
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.video_reader import VideoReader
from interpolation.linear import LinearInterpolator


def save_results():
    """生成并保存对比结果"""
    print("=" * 70)
    print("  线性插值效果演示 - 生成保存结果")
    print("  使用 video_test.mp4")
    print("=" * 70)

    video_path = "video_test.mp4"
    interpolator = LinearInterpolator()

    with VideoReader(source=video_path, target_size=(640, 480)) as reader:
        print("\n  正在读取视频帧...")

        # 读取几帧
        frames = []
        for i, frame in enumerate(reader.get_frames(max_frames=8)):
            frames.append(frame.copy())
            print(f"    读取第 {i+1} 帧")
            if len(frames) >= 6:
                break

        if len(frames) < 2:
            print("  错误: 无法读取足够的帧!")
            return

        print("\n  开始生成对比结果...")

        # 演示1: 两帧之间的 t=0.5 插值
        if len(frames) >= 2:
            print("\n  [演示1] 两帧插值 (t=0.5)")
            frame1 = frames[0]
            frame2 = frames[3]
            interpolated = interpolator(frame1, frame2, t=0.5)

            # 拼接
            h, w = frame1.shape[:2]
            if len(frame1.shape) == 2:
                frame1 = cv2.cvtColor(frame1, cv2.COLOR_GRAY2BGR)
                frame2 = cv2.cvtColor(frame2, cv2.COLOR_GRAY2BGR)
                interpolated = cv2.cvtColor(interpolated, cv2.COLOR_GRAY2BGR)

            comparison1 = np.hstack([frame1, interpolated, frame2])

            # 添加标签
            cv2.putText(comparison1, "Frame 1", (20, h - 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            cv2.putText(comparison1, "Interpolated (t=0.5)", (w + 20, h - 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            cv2.putText(comparison1, "Frame 2", (2 * w + 20, h - 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

            cv2.imwrite("output_linear_interp_comparison1.png", comparison1)
            print("    已保存: output_linear_interp_comparison1.png")

        # 演示2: 多t值对比
        if len(frames) >= 2:
            print("\n  [演示2] 多t值对比 (0.25, 0.5, 0.75)")
            frame1 = frames[0]
            frame2 = frames[3]
            ts = [0.25, 0.5, 0.75]

            interpolated_frames = []
            for t in ts:
                interpolated_frames.append(interpolator(frame1, frame2, t))

            if len(frame1.shape) == 2:
                frame1 = cv2.cvtColor(frame1, cv2.COLOR_GRAY2BGR)
                frame2 = cv2.cvtColor(frame2, cv2.COLOR_GRAY2BGR)
                for i in range(len(interpolated_frames)):
                    interpolated_frames[i] = cv2.cvtColor(interpolated_frames[i], cv2.COLOR_GRAY2BGR)

            all_frames = [frame1] + interpolated_frames + [frame2]
            comparison2 = np.hstack(all_frames)

            h, w = frame1.shape[:2]
            cv2.putText(comparison2, "F1", (20, h - 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            for i, t in enumerate(ts):
                x_pos = w * (i + 1) + 20
                cv2.putText(comparison2, f"t={t:.2f}", (x_pos, h - 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.putText(comparison2, "F2", (w * (len(ts) + 1) + 20, h - 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

            cv2.imwrite("output_linear_interp_multi_t.png", comparison2)
            print("    已保存: output_linear_interp_multi_t.png")

        # 演示3: 生成多帧序列插值
        if len(frames) >= 4:
            print("\n  [演示3] 序列多帧插值")
            all_interpolated = []
            for i in range(len(frames) - 1):
                f1 = frames[i]
                f2 = frames[i + 1]
                t = 0.5
                interpolated = interpolator(f1, f2, t)
                all_interpolated.append(f1)
                all_interpolated.append(interpolated)
            all_interpolated.append(frames[-1])

            h, w = all_interpolated[0].shape[:2]

            # 转换成3通道
            for i in range(len(all_interpolated)):
                if len(all_interpolated[i].shape) == 2:
                    all_interpolated[i] = cv2.cvtColor(all_interpolated[i], cv2.COLOR_GRAY2BGR)

            # 排成网格 (3列)
            grid_rows = []
            for row in range(4):
                row_frames = []
                for col in range(3):
                    idx = row * 3 + col
                    if idx < len(all_interpolated):
                        frame = all_interpolated[idx].copy()
                        # 添加编号
                        label = f"F{idx//2 + 1}" if idx % 2 == 0 else "I"
                        cv2.putText(frame, label, (10, 30),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                        row_frames.append(frame)
                    else:
                        row_frames.append(np.zeros_like(all_interpolated[0]))
                grid_rows.append(np.hstack(row_frames))

            full_grid = np.vstack(grid_rows)
            cv2.imwrite("output_linear_interp_sequence_grid.png", full_grid)
            print("    已保存: output_linear_interp_sequence_grid.png")

        print("\n" + "=" * 70)
        print("  所有结果已保存! 请查看当前目录:")
        print("  - output_linear_interp_comparison1.png")
        print("  - output_linear_interp_multi_t.png")
        print("  - output_linear_interp_sequence_grid.png")
        print("=" * 70)


if __name__ == "__main__":
    try:
        save_results()
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()


"""
Stage 7: AER (地址事件表示) 演示 - 重构版

本模块演示AER编码/解码的详细过程，确保与Stage 8的AER编码模块
完全兼容。

核心功能：
- AER编码：将DVS事件编码为32位地址
- AER解码：将32位地址还原为DVS事件
- 不应期事件检测（与Stage 8一致）
- 对数空间处理（与Stage 8一致）
- H.264关键帧（内存级编码）

输出规范（与Stage 8兼容）：
- AER地址格式: 32位 (极性1bit + X坐标15bit + Y坐标16bit)
- 时间戳: 微秒级精度
- 事件数据: DVSCoordinate对象列表

使用示例：
    python examples/stage7_aer_demo.py video_test.mp4
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
from utils.video_reader import VideoReader, display_frame, put_text
from evs.event_detector import EventDetector
from evs.event_encoder import EventEncoder
from evs.event_decoder import EventFrameReconstructor
from evs.aer_encoder import AEREncoder, AERVisualizer
from h264.encoder import InMemoryH264Encoder


def demo_aer_encoding_decoding():
    """
    AER编码/解码演示 - 展示基础AER处理

    此演示验证Stage 7的AER编码与Stage 8完全一致。
    """
    print("=" * 60)
    print("  Stage 7: AER编码/解码演示")
    print("=" * 60)
    print("  AER地址格式:")
    print("    Bit 31: 极性 (0=OFF, 1=ON)")
    print("    Bit 30-16: X坐标 (0-32767)")
    print("    Bit 15-0: Y坐标 (0-65535)")

    width, height = 640, 480
    aer_encoder = AEREncoder(width, height)

    # 创建测试事件 (DVSCoordinate对象)
    from evs.event_detector import DVSCoordinate
    test_events = []
    for y in range(0, height, 20):
        for x in range(0, width, 20):
            polarity = 1 if (x + y) % 40 < 20 else 0
            event_type = "on" if polarity == 1 else "off"
            test_events.append(DVSCoordinate(x=x, y=y, event_type=event_type))

    print(f"\n  创建 {len(test_events)} 个测试事件")

    # 编码 (DVSCoordinate列表编码为AER二进制)
    aer_data = aer_encoder.encode_events(test_events, include_timestamp=True)
    print(f"  AER编码大小: {len(aer_data)} 字节")
    print(f"  每事件大小: {len(aer_data) / max(len(test_events), 1):.1f} 字节")

    # 解码 (AER二进制还原为DVSCoordinate列表)
    decoded_events = aer_encoder.decode_events(aer_data, has_timestamp=True)
    print(f"  解码事件数: {len(decoded_events)}")

    # 验证编码/解码一致性
    if len(decoded_events) == len(test_events):
        print("  验证: 编码/解码事件数一致")
    else:
        print("  警告: 编码/解码事件数不一致")

    # 可视化 - 使用正确的AER可视化方法 render_aer_events
    event_image = AERVisualizer.render_aer_events(
        decoded_events, width=width, height=height,
        on_color=(0, 0, 255), off_color=(0, 255, 0)
    )
    event_image = put_text(event_image, "AER Events (Red=ON, Green=OFF)", (10, 30),
                           color=(0, 255, 255))
    display_frame(event_image, "Stage 7: AER事件可视化")
    cv2.waitKey(2000)
    cv2.destroyAllWindows()


def demo_video_aer(source="0", max_frames=100):
    """
    视频AER实时演示 - 展示视频帧的AER编码

    参数:
        source: 视频源 ("0"为摄像头, 或文件路径)
        max_frames: 最大处理帧数
    """
    print("\n" + "=" * 60)
    print("  Stage 7: 视频AER实时演示")
    print("=" * 60)
    print(f"  视频源: {source}")
    print(f"  最大帧数: {max_frames}")
    print("\n  按 ESC 退出")

    with VideoReader(source=source, target_size=(640, 480)) as reader:
        if not reader.cap.isOpened():
            print(f"  错误: 无法打开视频源: {source}")
            return

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

        h264_encoder = InMemoryH264Encoder(width, height, fps=int(fps))
        event_encoder = EventEncoder(width, height)
        reconstructor = EventFrameReconstructor(
            width=width,
            height=height,
            log_threshold=20.0 / 255.0
        )

        # 统计信息
        total_events = 0
        frame_idx = 0
        keyframe_interval = 30

        for frame in reader.get_frames(max_frames=max_frames):
            frame_idx += 1
            current_time = frame_idx / fps

            is_keyframe = (frame_idx == 1) or (frame_idx % keyframe_interval == 0)

            if is_keyframe:
                # 关键帧: H.264内存级编码
                i_frame_data = h264_encoder.encode_i_frame(frame)
                print(f"  帧 {frame_idx}: 关键帧 ({len(i_frame_data)} 字节)")

                # 重置检测器参考帧
                detector.set_reference(frame)

                # 可视化关键帧
                info = put_text(frame.copy(), f"关键帧 #{frame_idx}", (10, 30),
                               color=(0, 255, 255))
                info = put_text(info, f"H.264: {len(i_frame_data)} bytes", (10, 60),
                               color=(0, 255, 255))
                display_frame(info, "Stage 7: 视频AER实时演示")

            else:
                # 事件检测（带不应期）
                events = detector.detect(frame, frame_idx=frame_idx,
                                        current_time=current_time)
                event_count = len(events.events)
                total_events += event_count

                # AER编码可视化 - 使用 render_aer_events
                if events.events:
                    aer_image = AERVisualizer.render_aer_events(
                        events.events, width=width, height=height,
                        on_color=(0, 0, 255), off_color=(0, 255, 0)
                    )
                else:
                    aer_image = np.ones((height, width, 3), dtype=np.uint8) * 255

                aer_image = put_text(aer_image, f"帧: {frame_idx}", (10, 30),
                                    color=(0, 255, 255))
                aer_image = put_text(aer_image, f"DVS事件: {event_count}", (10, 60),
                                    color=(0, 255, 255))
                aer_image = put_text(aer_image, f"总事件: {total_events}", (10, 90),
                                    color=(0, 255, 255))

                display_frame(aer_image, "Stage 7: 视频AER实时演示")

                if frame_idx % 10 == 0:
                    print(f"  帧 {frame_idx}: {event_count} DVS事件 (累计: {total_events})")

            key = cv2.waitKey(30) & 0xFF
            if key == 27:
                print("\n  用户退出")
                break

        cv2.destroyAllWindows()

        print(f"\n  统计:")
        print(f"    总帧数: {frame_idx}")
        print(f"    总DVS事件数: {total_events}")
        if frame_idx > 0:
            print(f"    平均每帧事件: {total_events / frame_idx:.0f}")


def demo_aer_raster_plot(source="0", max_frames=50):
    """
    AER时空栅格图演示 - 展示事件的时空分布

    参数:
        source: 视频源
        max_frames: 最大处理帧数
    """
    print("\n" + "=" * 60)
    print("  Stage 7: AER时空栅格图演示")
    print("=" * 60)
    print(f"  视频源: {source}")
    print(f"  最大帧数: {max_frames}")

    with VideoReader(source=source, target_size=(640, 480)) as reader:
        if not reader.cap.isOpened():
            print(f"  错误: 无法打开视频源: {source}")
            return

        width, height = reader.target_size
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

        # 收集所有事件 (DVSCoordinate列表)
        all_events = []
        frame_idx = 0

        for frame in reader.get_frames(max_frames=max_frames):
            frame_idx += 1
            current_time = frame_idx / reader.fps

            events = detector.detect(frame, frame_idx=frame_idx,
                                    current_time=current_time)

            # 收集DVS事件 (events.events 是 DVSCoordinate 列表)
            if events.events:
                all_events.extend(events.events)

            # 显示当前帧
            info_frame = put_text(frame.copy(), f"收集事件: {len(all_events)}",
                                 (10, 30), color=(0, 255, 255))
            info_frame = put_text(info_frame, f"帧: {frame_idx}", (10, 60),
                                 color=(0, 255, 255))
            display_frame(info_frame, "Stage 7: 收集事件")

            key = cv2.waitKey(30) & 0xFF
            if key == 27:
                break

        cv2.destroyAllWindows()

        if all_events:
            # 生成时空栅格图 (Raster Plot)
            raster = AERVisualizer.create_raster_plot(
                all_events, width=width, height=height, num_bins=100
            )
            raster = put_text(raster, f"时空栅格图 ({len(all_events)} DVS events)",
                             (10, 30), color=(0, 255, 255))
            display_frame(raster, "Stage 7: 时空栅格图")
            cv2.waitKey(3000)
            cv2.destroyAllWindows()

            print(f"\n  栅格图生成: {len(all_events)} DVS事件")
        else:
            print("\n  未检测到事件")


def main():
    """主函数 - 运行所有AER演示"""
    source = "0"
    if len(sys.argv) > 1:
        source = sys.argv[1]

    try:
        # 演示1: 基础AER编码/解码
        #demo_aer_encoding_decoding()

        # 演示2: 视频AER实时演示
        demo_video_aer(source, max_frames=60)

        # 演示3: 时空栅格图
        #demo_aer_raster_plot(source, max_frames=30)

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
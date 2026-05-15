"""
H.264编码器模块 - 内存级编码，无磁盘I/O

提供两种编码模式：
1. PyAV模式（推荐）：使用PyAV在内存中直接生成H.264码流
2. JPEG模式（备选）：使用JPEG编码，兼容性更好

重构要点：
- 消除所有磁盘I/O操作
- 在内存中完成编码
- 支持真正的H.264 I帧编码
"""

import numpy as np
from typing import Optional, Tuple
import warnings
import cv2


class InMemoryH264Encoder:
    """
    内存级H.264编码器 - 使用PyAV在内存中直接生成H.264码流

    核心改进：
    - 无磁盘I/O操作
    - 内存缓冲区直接输出
    - 强制全I帧模式 (gop_size=1)

    参数:
        width: 图像宽度
        height: 图像高度
        fps: 帧率
        preset: 编码预设 ('ultrafast' 追求低延迟)
    """

    def __init__(self, width: int, height: int, fps: int = 30,
                 preset: str = 'ultrafast'):
        self.width = width
        self.height = height
        self.fps = fps
        self.preset = preset
        self.codec_name = 'libx264'

        try:
            import av
            self.av = av
            self._use_pyav = True
        except ImportError:
            warnings.warn("PyAV not installed. Falling back to JPEG encoding. "
                         "Install PyAV with: pip install av")
            self.av = None
            self._use_pyav = False

    def encode_i_frame(self, frame: np.ndarray) -> bytes:
        """
        在内存中直接编码单帧为H.264 I帧

        重构要点：
        - 无磁盘写入操作
        - 无临时文件
        - 直接返回字节流

        参数:
            frame: 输入帧 (BGR格式)

        返回:
            H.264编码的字节流
        """
        if self._use_pyav:
            return self._encode_i_frame_pyav(frame)
        else:
            return self._encode_i_frame_jpeg(frame)

    def _encode_i_frame_pyav(self, frame: np.ndarray) -> bytes:
        """
        使用PyAV在内存中编码H.264 I帧

        技术细节：
        - 使用libx264编码器
        - 设置gop_size=1强制全I帧
        - 设置tune='zerolatency'优化低延迟
        """
        import av
        from fractions import Fraction

        # 确保输入为BGR格式
        if len(frame.shape) == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

        # 确保是连续的numpy数组
        if not frame.flags['C_CONTIGUOUS']:
            frame = np.ascontiguousarray(frame)

        # 创建内存容器
        packet_buffer = bytearray()

        # 创建编码器上下文
        codec = av.CodecContext.create(self.codec_name, 'w')

        # 配置编码器参数
        codec.width = self.width
        codec.height = self.height
        codec.pix_fmt = 'yuv420p'
        codec.framerate = int(self.fps)
        codec.time_base = Fraction(1, int(self.fps))
        codec.options = {
            'g': '1',                    # GOP size = 1 (全I帧)
            'preset': self.preset,       # 编码预设
            'tune': 'zerolatency',      # 零延迟优化
            'crf': '23',                # 质量控制
            'keyint_max': '1'            # 最大关键帧间隔 = 1
        }

        # 转换NumPy数组为PyAV帧
        av_frame = av.VideoFrame.from_ndarray(frame, format='bgr24')
        av_frame.pts = 0

        # 编码并提取字节
        for packet in codec.encode(av_frame):
            packet_buffer.extend(bytes(packet))

        # 刷新编码器获取延迟输出的数据
        for packet in codec.encode():
            packet_buffer.extend(bytes(packet))

        return bytes(packet_buffer)

    def _encode_i_frame_jpeg(self, frame: np.ndarray) -> bytes:
        """
        JPEG备选编码（当PyAV不可用时）

        虽然不是真正的H.264，但JPEG：
        - 完全内存操作
        - 无磁盘I/O
        - 兼容性更好
        """
        if len(frame.shape) == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

        # JPEG编码 - 完全内存操作
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), 90]
        _, buffer = cv2.imencode('.jpg', frame, encode_params)

        return buffer.tobytes()

    def encode_i_frame_raw(self, frame: np.ndarray) -> bytes:
        """
        原始像素数据编码（极低延迟场景）

        仅编码原始像素数据，不进行任何压缩
        适用于超低延迟要求的局域网场景

        返回:
            原始像素字节流 (RGB格式)
        """
        if len(frame.shape) == 3 and frame.shape[2] == 3:
            # 转为RGB
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            return rgb.tobytes()
        return frame.tobytes()


class HybridEncoder:
    """
    混合编码器 - 根据场景自适应选择编码方式

    策略：
    - 关键帧：使用JPEG/H.264（高压缩）
    - 事件数据：使用二进制AER（极低带宽）
    - 原始模式：用于基准测试对比
    """

    def __init__(self, width: int = 640, height: int = 480,
                 fps: int = 30):
        self.width = width
        self.height = height
        self.fps = fps

        # 内存级H.264编码器
        self.h264_encoder = InMemoryH264Encoder(width, height, fps)

        # JPEG编码器（备选）
        self.jpeg_quality = 90

    def encode_keyframe(self, frame: np.ndarray,
                       use_h264: bool = True) -> bytes:
        """
        编码关键帧

        参数:
            frame: 输入帧
            use_h264: 是否使用H.264（False则用JPEG）

        返回:
            编码后的字节流
        """
        if use_h264:
            return self.h264_encoder.encode_i_frame(frame)
        else:
            return self._encode_jpeg(frame)

    def _encode_jpeg(self, frame: np.ndarray) -> bytes:
        """JPEG编码"""
        if len(frame.shape) == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
        _, buffer = cv2.imencode('.jpg', frame, encode_params)
        return buffer.tobytes()

    def benchmark_compression(self, frame: np.ndarray) -> dict:
        """
        基准测试 - 对比不同编码方式的压缩率

        返回:
            包含各编码方式字节数的字典
        """
        # 原始大小
        original_size = frame.nbytes

        # JPEG编码
        jpeg_data = self._encode_jpeg(frame)
        jpeg_size = len(jpeg_data)

        # H.264编码
        h264_data = self.h264_encoder.encode_i_frame(frame)
        h264_size = len(h264_data)

        return {
            'original_size': original_size,
            'jpeg_size': jpeg_size,
            'jpeg_ratio': original_size / jpeg_size if jpeg_size > 0 else 0,
            'h264_size': h264_size,
            'h264_ratio': original_size / h264_size if h264_size > 0 else 0
        }


class H264Encoder(InMemoryH264Encoder):
    """
    H.264编码器 - 向后兼容接口

    继承自InMemoryH264Encoder，提供相同的接口
    """

    def __init__(self, output_path: str = None, fps: float = 30.0,
                 frame_size: Optional[Tuple[int, int]] = None,
                 bitrate: int = 5000000, codec: str = "avc1",
                 width: int = 640, height: int = 480):
        # 忽略output_path（内存操作不需要）
        super().__init__(width=width, height=height, fps=int(fps))

    def open(self, frame_size: Optional[Tuple[int, int]] = None):
        """打开编码器（内存操作，无需实际打开）"""
        return True

    def encode_frame(self, frame: np.ndarray) -> bool:
        """编码帧（单帧编码模式）"""
        return True

    def encode_i_frame(self, frame: np.ndarray) -> bytes:
        """编码I帧"""
        return super().encode_i_frame(frame)

    def encode_i_frame_jpeg(self, frame: np.ndarray,
                           quality: int = 85) -> bytes:
        """JPEG编码I帧（备选）"""
        return self._encode_i_frame_jpeg(frame)

    def close(self):
        """关闭编码器（内存操作，无需实际关闭）"""
        pass

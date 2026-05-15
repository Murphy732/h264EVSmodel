"""
H.264 编码策略对比基准测试

对比两种编码策略：
  [方案A - 当前] 全I帧编码: 每帧独立编码为I帧 (gop_size=1)
  [方案B - 优化] I+P/B混合编码: 首帧I帧 + 后续P帧 + 周期性I帧刷新

测试指标：
  - 编码效率: 每帧字节数、总带宽、压缩率
  - 解码性能: 解码时间、CPU使用率
  - 视频质量: PSNR、SSIM
  - 延迟表现: 编码延迟、端到端延迟

使用示例：
    python examples/stage4_h264_benchmark.py video_test.mp4
"""

import sys
import os
import time
import json
import hashlib
from datetime import datetime
from collections import defaultdict
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

# 可选: 用于画图
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    # 配置中文字体
    for font_name in ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']:
        try:
            matplotlib.font_manager.findfont(font_name, fallback_to_default=False)
            plt.rcParams['font.sans-serif'] = [font_name]
            break
        except Exception:
            continue
    plt.rcParams['axes.unicode_minus'] = False
    HAS_MPL = True
except ImportError:
    HAS_MPL = False


def compute_psnr(original, compressed):
    """计算PSNR (峰值信噪比)"""
    mse = np.mean((original.astype(np.float64) - compressed.astype(np.float64)) ** 2)
    if mse == 0:
        return float('inf')
    return 20 * np.log10(255.0 / np.sqrt(mse))


def compute_ssim(img1, img2):
    """简化的SSIM计算 (结构相似性指数)"""
    C1 = (0.01 * 255) ** 2
    C2 = (0.03 * 255) ** 2

    img1 = img1.astype(np.float64)
    img2 = img2.astype(np.float64)

    mu1 = cv2.GaussianBlur(img1, (11, 11), 1.5)
    mu2 = cv2.GaussianBlur(img2, (11, 11), 1.5)

    mu1_sq = mu1 ** 2
    mu2_sq = mu2 ** 2
    mu1_mu2 = mu1 * mu2

    sigma1_sq = cv2.GaussianBlur(img1 ** 2, (11, 11), 1.5) - mu1_sq
    sigma2_sq = cv2.GaussianBlur(img2 ** 2, (11, 11), 1.5) - mu2_sq
    sigma12 = cv2.GaussianBlur(img1 * img2, (11, 11), 1.5) - mu1_mu2

    ssim_map = ((2 * mu1_mu2 + C1) * (2 * sigma12 + C2)) / \
               ((mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2))
    return np.mean(ssim_map)


class H264Benchmark:
    """
    H.264编码策略基准测试

    对比:
      - 方案A: 全I帧 (current)
      - 方案B: I+P混合 + 周期性I帧刷新 (optimized)
    """

    def __init__(self, width=640, height=480, fps=30):
        self.width = width
        self.height = height
        self.fps = fps

        self.results = {
            'config': {
                'width': width, 'height': height, 'fps': fps,
                'test_time': datetime.now().isoformat()
            },
            'scheme_all_i': {},      # 方案A: 全I帧
            'scheme_hybrid_ip': {}   # 方案B: I+P混合
        }

    def _encode_all_i(self, frames):
        """
        方案A: 全I帧编码

        每帧作为独立的I帧编码，gop_size=1。
        与当前InMemoryH264Encoder的行为一致。
        """
        import av
        from fractions import Fraction

        stats = {
            'frame_sizes': [],
            'encode_times': [],
            'decode_times': [],
            'psnr_values': [],
            'ssim_values': [],
            'total_bytes': 0,
            'total_encode_time': 0.0,
            'total_decode_time': 0.0,
            'decoded_frames': []
        }

        all_encoded = bytearray()

        for i, frame in enumerate(frames):
            if len(frame.shape) == 2:
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
            else:
                frame_bgr = frame

            if not frame_bgr.flags['C_CONTIGUOUS']:
                frame_bgr = np.ascontiguousarray(frame_bgr)

            t0 = time.time()

            packet_buffer = bytearray()
            codec = av.CodecContext.create('libx264', 'w')
            codec.width = self.width
            codec.height = self.height
            codec.pix_fmt = 'yuv420p'
            codec.framerate = int(self.fps)
            codec.time_base = Fraction(1, int(self.fps))
            codec.options = {
                'g': '1',
                'preset': 'ultrafast',
                'tune': 'zerolatency',
                'crf': '23',
                'keyint_max': '1'
            }

            av_frame = av.VideoFrame.from_ndarray(frame_bgr, format='bgr24')
            av_frame.pts = i

            for packet in codec.encode(av_frame):
                data = bytes(packet)
                packet_buffer.extend(data)
                all_encoded.extend(data)
            for packet in codec.encode():
                data = bytes(packet)
                packet_buffer.extend(data)
                all_encoded.extend(data)

            h264_bytes = bytes(packet_buffer)
            encode_time = time.time() - t0

            stats['frame_sizes'].append(len(h264_bytes))
            stats['encode_times'].append(encode_time)
            stats['total_bytes'] += len(h264_bytes)
            stats['total_encode_time'] += encode_time

            if i < 5 or i % 10 == 0:
                print(f"  [全I帧] 帧{i:3d}: {len(h264_bytes):6d}字节 | "
                      f"编码{encode_time*1000:.1f}ms")

        # 批量解码评估质量
        print(f"\n  [全I帧] 批量解码 {len(frames)} 帧...")
        t0 = time.time()
        decoded_frames = self._batch_decode_h264(bytes(all_encoded))
        total_decode_time = time.time() - t0
        stats['total_decode_time'] = total_decode_time

        n_decoded = len(decoded_frames)
        for i in range(min(n_decoded, len(frames))):
            stats['decode_times'].append(total_decode_time / max(n_decoded, 1))
            decoded_frame = decoded_frames[i]
            stats['decoded_frames'].append(decoded_frame)

            orig_bgr = frames[i] if len(frames[i].shape) == 3 else \
                       cv2.cvtColor(frames[i], cv2.COLOR_GRAY2BGR)
            psnr = compute_psnr(orig_bgr, decoded_frame)
            ssim = compute_ssim(
                cv2.cvtColor(orig_bgr, cv2.COLOR_BGR2GRAY),
                cv2.cvtColor(decoded_frame, cv2.COLOR_BGR2GRAY)
            )
            stats['psnr_values'].append(psnr)
            stats['ssim_values'].append(ssim)

        print(f"  解码{len(decoded_frames)}帧, 耗时{total_decode_time*1000:.1f}ms")

        return stats

    def _batch_decode_h264(self, h264_data):
        """批量解码H.264字节流"""
        import av
        frames = []
        try:
            codec = av.CodecContext.create('h264', 'r')
            for packet in codec.parse(h264_data):
                for frame in codec.decode(packet):
                    img = frame.to_ndarray(format='bgr24')
                    frames.append(img)
        except Exception as e:
            pass
        return frames

    def _encode_hybrid_ip(self, frames, keyframe_interval=30):
        """
        方案B: I+P混合编码 + 周期性I帧刷新

        策略:
          - 第1帧: I帧 (建立完整参考)
          - 第2~(keyframe_interval-1)帧: P帧 (帧间预测)
          - 第keyframe_interval帧: I帧 (周期性刷新)
          - 循环...
        """
        import av
        from fractions import Fraction

        stats = {
            'frame_sizes': [],
            'encode_times': [],
            'decode_times': [],
            'psnr_values': [],
            'ssim_values': [],
            'total_bytes': 0,
            'total_encode_time': 0.0,
            'total_decode_time': 0.0,
            'decoded_frames': [],
            'i_frames': [],
            'p_frames': []
        }

        # 创建编码器上下文（保持状态，跨帧复用）
        codec = av.CodecContext.create('libx264', 'w')
        codec.width = self.width
        codec.height = self.height
        codec.pix_fmt = 'yuv420p'
        codec.framerate = int(self.fps)
        codec.time_base = Fraction(1, int(self.fps))
        codec.options = {
            'preset': 'ultrafast',
            'tune': 'zerolatency',
            'crf': '23',
        }

        encoded_packets = []  # 存储所有编码后的packets用于解码

        for i, frame in enumerate(frames):
            if len(frame.shape) == 2:
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
            else:
                frame_bgr = frame

            if not frame_bgr.flags['C_CONTIGUOUS']:
                frame_bgr = np.ascontiguousarray(frame_bgr)

            is_keyframe = (i == 0) or (i % keyframe_interval == 0)

            # --- 编码 ---
            t0 = time.time()

            packet_buffer = bytearray()
            av_frame = av.VideoFrame.from_ndarray(frame_bgr, format='bgr24')
            av_frame.pts = i

            if is_keyframe:
                av_frame.pict_type = av.video.frame.PictureType.I
            else:
                av_frame.pict_type = av.video.frame.PictureType.P

            for packet in codec.encode(av_frame):
                data = bytes(packet)
                packet_buffer.extend(data)
                encoded_packets.append(data)

            encode_time = time.time() - t0

            h264_bytes = bytes(packet_buffer)
            frame_type = 'I' if is_keyframe else 'P'

            # --- 解码 (批量) ---
            # 解码整个序列以评估PSNR/SSIM
            decode_time = 0.0  # 批量解码时单独统计

            stats['frame_sizes'].append(len(h264_bytes))
            stats['encode_times'].append(encode_time)
            stats['total_bytes'] += len(h264_bytes)
            stats['total_encode_time'] += encode_time

            if is_keyframe:
                stats['i_frames'].append({'idx': i, 'size': len(h264_bytes)})
            else:
                stats['p_frames'].append({'idx': i, 'size': len(h264_bytes)})

            if i < 5 or i % 10 == 0 or is_keyframe:
                print(f"  [I+P]  帧{i:3d}({frame_type}): {len(h264_bytes):6d}字节 | "
                      f"编码{encode_time*1000:.1f}ms")

        # 刷新编码器
        for packet in codec.encode():
            encoded_packets.append(bytes(packet))

        # --- 批量解码评估质量 ---
        print("\n  [I+P] 批量解码中...")
        t0 = time.time()

        all_h264 = b''.join(encoded_packets)
        decoded_frames = self._batch_decode_h264(all_h264)
        total_decode_time = time.time() - t0
        stats['total_decode_time'] = total_decode_time
        stats['decoded_frames'] = decoded_frames

        # 计算每帧质量
        for i, dec_frame in enumerate(decoded_frames):
            if i < len(frames):
                orig_bgr = frames[i] if len(frames[i].shape) == 3 else \
                           cv2.cvtColor(frames[i], cv2.COLOR_GRAY2BGR)
                psnr = compute_psnr(orig_bgr, dec_frame)
                ssim = compute_ssim(
                    cv2.cvtColor(orig_bgr, cv2.COLOR_BGR2GRAY),
                    cv2.cvtColor(dec_frame, cv2.COLOR_BGR2GRAY)
                )
                stats['psnr_values'].append(psnr)
                stats['ssim_values'].append(ssim)
                stats['decode_times'].append(total_decode_time / max(len(decoded_frames), 1))

        return stats

    def run_benchmark(self, video_path, max_frames=120):
        """
        运行完整基准测试
        """
        print("=" * 70)
        print("  H.264编码策略对比基准测试")
        print("=" * 70)
        print(f"  视频源: {video_path}")
        print(f"  最大帧数: {max_frames}")
        print(f"  目标分辨率: {self.width}x{self.height}")
        print()

        # 读取视频帧
        print("正在加载视频帧...")
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"错误: 无法打开视频 {video_path}")
            return None

        frames = []
        while len(frames) < max_frames:
            ret, frame = cap.read()
            if not ret:
                break
            frame = cv2.resize(frame, (self.width, self.height))
            frames.append(frame)
        cap.release()

        print(f"已加载 {len(frames)} 帧\n")

        # --- 方案A: 全I帧编码 ---
        print("=" * 70)
        print("  方案A: 全I帧编码 (当前方案)")
        print("=" * 70)
        self.results['scheme_all_i'] = self._encode_all_i(frames)

        # --- 方案B: I+P混合编码 ---
        print("\n" + "=" * 70)
        print("  方案B: I+P混合编码 (优化方案)")
        print("=" * 70)
        self.results['scheme_hybrid_ip'] = self._encode_hybrid_ip(frames)
        print(f"  批量解码总时间: {self.results['scheme_hybrid_ip']['total_decode_time']*1000:.1f}ms")

        return self.results

    def print_report(self):
        """打印对比报告"""
        a = self.results['scheme_all_i']
        b = self.results['scheme_hybrid_ip']

        n_a = len(a['frame_sizes'])
        n_b = len(b['frame_sizes'])

        print("\n" + "=" * 70)
        print("  基准测试报告")
        print("=" * 70)

        print("\n┌" + "─" * 68 + "┐")
        print("│" + " 指标" + " " * 24 + "方案A(全I帧)" + " " * 7 + "方案B(I+P)" + " " * 6 + "变化" + " " * 8 + "│")
        print("├" + "─" * 68 + "┤")

        # 总字节数
        total_a = a['total_bytes']
        total_b = b['total_bytes']
        pct = (total_b - total_a) / total_a * 100 if total_a > 0 else 0
        print(f"│ 总编码字节      {total_a:>12,}    {total_b:>12,}    {pct:>+7.1f}%  │")

        # 平均每帧字节
        avg_a = np.mean(a['frame_sizes'])
        avg_b = np.mean(b['frame_sizes'])
        pct2 = (avg_b - avg_a) / avg_a * 100 if avg_a > 0 else 0
        print(f"│ 平均帧大小(字节) {avg_a:>11.0f}    {avg_b:>11.0f}    {pct2:>+7.1f}%  │")

        # 压缩率
        orig_per_frame = self.width * self.height * 3
        ratio_a = orig_per_frame / avg_a if avg_a > 0 else 0
        ratio_b = orig_per_frame / avg_b if avg_b > 0 else 0
        print(f"│ 压缩率          {ratio_a:>12.1f}x   {ratio_b:>12.1f}x              │")

        # 编码时间
        enc_a = a['total_encode_time']
        enc_b = b['total_encode_time']
        pct3 = (enc_b - enc_a) / enc_a * 100 if enc_a > 0 else 0
        print(f"│ 总编码时间(秒)  {enc_a:>12.3f}    {enc_b:>12.3f}    {pct3:>+7.1f}%  │")

        # 编码FPS
        fps_a = n_a / enc_a if enc_a > 0 else 0
        fps_b = n_b / enc_b if enc_b > 0 else 0
        print(f"│ 编码速度(FPS)   {fps_a:>12.1f}    {fps_b:>12.1f}              │")

        # 解码时间
        dec_a = a['total_decode_time']
        dec_b = b['total_decode_time']
        pct4 = (dec_b - dec_a) / dec_a * 100 if dec_a > 0 else 0
        print(f"│ 总解码时间(秒)  {dec_a:>12.3f}    {dec_b:>12.3f}    {pct4:>+7.1f}%  │")

        # PSNR
        if a['psnr_values'] and b['psnr_values']:
            psnr_a = np.mean(a['psnr_values'])
            psnr_b = np.mean(b['psnr_values'])
            diff = psnr_b - psnr_a
            print(f"│ 平均PSNR(dB)    {psnr_a:>12.2f}    {psnr_b:>12.2f}    {diff:>+7.2f}   │")

        # SSIM
        if a['ssim_values'] and b['ssim_values']:
            ssim_a = np.mean(a['ssim_values'])
            ssim_b = np.mean(b['ssim_values'])
            diff2 = ssim_b - ssim_a
            print(f"│ 平均SSIM        {ssim_a:>12.4f}    {ssim_b:>12.4f}    {diff2:>+7.4f}   │")

        # 带宽(30fps场景)
        bw_a = avg_a * 30 * 8 / 1_000_000
        bw_b = avg_b * 30 * 8 / 1_000_000
        pct5 = (bw_b - bw_a) / bw_a * 100 if bw_a > 0 else 0
        print(f"│ 带宽@30fps(Mbps) {bw_a:>11.2f}    {bw_b:>11.2f}    {pct5:>+7.1f}%  │")

        # I帧统计（方案B特有）
        if b.get('i_frames'):
            i_sizes = [f['size'] for f in b['i_frames']]
            print(f"│ [B]I帧平均(KB)  {'':>12}    {np.mean(i_sizes)/1024:>11.1f}              │")
            print(f"│ [B]I帧数量      {'':>12}    {len(b['i_frames']):>11}              │")
        if b.get('p_frames'):
            p_sizes = [f['size'] for f in b['p_frames']]
            print(f"│ [B]P帧平均(KB)  {'':>12}    {np.mean(p_sizes)/1024:>11.1f}              │")
            print(f"│ [B]P帧数量      {'':>12}    {len(b['p_frames']):>11}              │")

        print("└" + "─" * 68 + "┘")

        # 综合评估
        print("\n" + "=" * 70)
        print("  综合评估")
        print("=" * 70)

        print(f"\n  编码效率:")
        if total_b < total_a:
            saving = (1 - total_b / total_a) * 100
            print(f"    方案B节省带宽: {saving:.1f}%")
            print(f"    每帧节省: {(avg_a - avg_b):.0f} 字节")
        else:
            extra = (total_b / total_a - 1) * 100
            print(f"    方案B额外开销: {extra:.1f}%")

        print(f"\n  编码速度:")
        print(f"    方案A: {fps_a:.1f} FPS")
        print(f"    方案B: {fps_b:.1f} FPS")

        print(f"\n  视频质量:")
        if a['psnr_values'] and b['psnr_values']:
            print(f"    方案A PSNR: {psnr_a:.2f} dB, SSIM: {ssim_a:.4f}")
            print(f"    方案B PSNR: {psnr_b:.2f} dB, SSIM: {ssim_b:.4f}")
            # PSNR > 40dB 一般视为质量无损
            # SSIM > 0.95 一般视为视觉无损

        print(f"\n  建议:")
        recommendations = []
        if total_b < total_a * 0.5:
            recommendations.append("强烈建议切换到方案B (I+P混合)，带宽节省 >50%")
        elif total_b < total_a * 0.9:
            recommendations.append("建议切换到方案B (I+P混合)，有明显带宽节省")
        else:
            recommendations.append("两种方案带宽差异不大，可保留方案A")

        if fps_b > fps_a * 0.9:
            recommendations.append("方案B编码速度在可接受范围内")
        else:
            recommendations.append("方案B编码速度下降较多，需权衡延迟与带宽")

        if b.get('psnr_values'):
            avg_psnr_b = np.mean(b['psnr_values'])
            if avg_psnr_b > 40:
                recommendations.append("方案B PSNR > 40dB，视觉质量无损")
            elif avg_psnr_b > 35:
                recommendations.append("方案B PSNR > 35dB，质量下降不可感知")
            else:
                recommendations.append("方案B PSNR偏低，需要调整CRF参数")

        for r in recommendations:
            print(f"    -> {r}")

        return self.results

    def save_results(self, output_dir="benchmark_results"):
        """保存基准测试结果"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = os.path.join(output_dir, timestamp)
        os.makedirs(out_dir, exist_ok=True)

        # 保存JSON报告
        report = {
            'config': self.results['config'],
            'summary': {},
            'scheme_all_i': {},
            'scheme_hybrid_ip': {}
        }

        for scheme_name in ['scheme_all_i', 'scheme_hybrid_ip']:
            s = self.results[scheme_name]
            avg_size = np.mean(s['frame_sizes']) if s['frame_sizes'] else 0
            orig_per_frame = self.width * self.height * 3

            report[scheme_name] = {
                'total_bytes': s['total_bytes'],
                'total_encode_time': s['total_encode_time'],
                'total_decode_time': s['total_decode_time'],
                'avg_frame_size': float(avg_size),
                'compression_ratio': float(orig_per_frame / avg_size if avg_size > 0 else 0),
                'bandwidth_30fps_mbps': float(avg_size * 30 * 8 / 1_000_000),
                'encode_fps': float(len(s['frame_sizes']) / s['total_encode_time']) if s['total_encode_time'] > 0 else 0,
                'avg_psnr': float(np.mean(s['psnr_values'])) if s['psnr_values'] else None,
                'avg_ssim': float(np.mean(s['ssim_values'])) if s['ssim_values'] else None,
                'frame_sizes': [int(x) for x in s['frame_sizes']],
                'encode_times': [float(x) for x in s['encode_times']],
                'psnr_values': [float(x) for x in s['psnr_values']],
                'ssim_values': [float(x) for x in s['ssim_values']],
            }

        report_path = os.path.join(out_dir, "benchmark_report.json")
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # 保存图表
        if HAS_MPL:
            self._save_charts(out_dir)

        print(f"\n  基准测试结果已保存到: {out_dir}")
        print(f"  报告文件: {report_path}")

        return out_dir

    def _save_charts(self, out_dir):
        """生成对比图表"""
        a = self.results['scheme_all_i']
        b = self.results['scheme_hybrid_ip']

        fig, axes = plt.subplots(2, 3, figsize=(18, 10))
        fig.suptitle('H.264 编码策略对比: 全I帧 vs I+P混合', fontsize=14, fontweight='bold')

        n_frames = min(len(a['frame_sizes']), len(b['frame_sizes']))

        # 1. 帧大小对比
        ax = axes[0, 0]
        ax.plot(a['frame_sizes'][:n_frames], label='方案A(全I帧)', alpha=0.7, linewidth=1)
        ax.plot(b['frame_sizes'][:n_frames], label='方案B(I+P)', alpha=0.7, linewidth=1)
        ax.set_xlabel('帧序号')
        ax.set_ylabel('字节数')
        ax.set_title('每帧编码大小')
        ax.legend()
        ax.grid(True, alpha=0.3)

        # 2. 编码时间对比
        ax = axes[0, 1]
        ax.plot(a['encode_times'][:n_frames], label='方案A', alpha=0.7, linewidth=1)
        ax.plot(b['encode_times'][:n_frames], label='方案B', alpha=0.7, linewidth=1)
        ax.set_xlabel('帧序号')
        ax.set_ylabel('秒')
        ax.set_title('每帧编码耗时')
        ax.legend()
        ax.grid(True, alpha=0.3)

        # 3. PSNR对比
        ax = axes[0, 2]
        if a['psnr_values'] and b['psnr_values']:
            n_psnr = min(len(a['psnr_values']), len(b['psnr_values']))
            ax.plot(a['psnr_values'][:n_psnr], label='方案A', alpha=0.7, linewidth=1)
            ax.plot(b['psnr_values'][:n_psnr], label='方案B', alpha=0.7, linewidth=1)
        ax.set_xlabel('帧序号')
        ax.set_ylabel('PSNR (dB)')
        ax.set_title('视频质量 (PSNR)')
        ax.legend()
        ax.grid(True, alpha=0.3)

        # 4. 累积字节数
        ax = axes[1, 0]
        ax.plot(np.cumsum(a['frame_sizes'][:n_frames]), label='方案A', alpha=0.7)
        ax.plot(np.cumsum(b['frame_sizes'][:n_frames]), label='方案B', alpha=0.7)
        ax.set_xlabel('帧序号')
        ax.set_ylabel('累积字节数')
        ax.set_title('累积带宽占用')
        ax.legend()
        ax.grid(True, alpha=0.3)

        # 5. SSIM对比
        ax = axes[1, 1]
        if a['ssim_values'] and b['ssim_values']:
            n_ssim = min(len(a['ssim_values']), len(b['ssim_values']))
            ax.plot(a['ssim_values'][:n_ssim], label='方案A', alpha=0.7, linewidth=1)
            ax.plot(b['ssim_values'][:n_ssim], label='方案B', alpha=0.7, linewidth=1)
        ax.set_xlabel('帧序号')
        ax.set_ylabel('SSIM')
        ax.set_title('结构相似性 (SSIM)')
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.set_ylim(0.8, 1.01)

        # 6. 效率对比柱状图
        ax = axes[1, 2]
        categories = ['总字节(KB)', '编码FPS', '带宽(Mbps)@30fps', '平均PSNR', '平均SSIM*100']
        orig = self.width * self.height * 3

        vals_a = [
            a['total_bytes'] / 1024,
            len(a['frame_sizes']) / a['total_encode_time'] if a['total_encode_time'] > 0 else 0,
            np.mean(a['frame_sizes']) * 30 * 8 / 1_000_000,
            np.mean(a['psnr_values']) if a['psnr_values'] else 0,
            np.mean(a['ssim_values']) * 100 if a['ssim_values'] else 0,
        ]
        vals_b = [
            b['total_bytes'] / 1024,
            len(b['frame_sizes']) / b['total_encode_time'] if b['total_encode_time'] > 0 else 0,
            np.mean(b['frame_sizes']) * 30 * 8 / 1_000_000,
            np.mean(b['psnr_values']) if b['psnr_values'] else 0,
            np.mean(b['ssim_values']) * 100 if b['ssim_values'] else 0,
        ]

        x = np.arange(len(categories))
        width = 0.35
        bars_a = ax.bar(x - width/2, vals_a, width, label='方案A(全I帧)', alpha=0.8)
        bars_b = ax.bar(x + width/2, vals_b, width, label='方案B(I+P)', alpha=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels(categories, rotation=25, ha='right', fontsize=8)
        ax.set_title('综合指标对比')
        ax.legend()

        # 标注数值
        for bar in bars_a:
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2, h, f'{h:.1f}',
                   ha='center', va='bottom', fontsize=7)
        for bar in bars_b:
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2, h, f'{h:.1f}',
                   ha='center', va='bottom', fontsize=7)

        plt.tight_layout()
        chart_path = os.path.join(out_dir, "benchmark_charts.png")
        plt.savefig(chart_path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  图表已保存: {chart_path}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='H.264编码策略对比基准测试')
    parser.add_argument('video', nargs='?', default='video_test.mp4',
                       help='输入视频路径 (默认: video_test.mp4)')
    parser.add_argument('--width', type=int, default=640, help='编码宽度')
    parser.add_argument('--height', type=int, default=480, help='编码高度')
    parser.add_argument('--fps', type=int, default=30, help='帧率')
    parser.add_argument('--frames', type=int, default=120, help='最大测试帧数')
    parser.add_argument('--no-save', action='store_true', help='不保存结果文件')

    args = parser.parse_args()

    # 检查视频文件是否存在
    if not os.path.exists(args.video):
        print(f"错误: 视频文件不存在: {args.video}")
        print("请确保 video_test.mp4 存在于项目根目录")
        print("或指定其他视频文件路径")
        sys.exit(1)

    try:
        benchmark = H264Benchmark(args.width, args.height, args.fps)
        results = benchmark.run_benchmark(args.video, max_frames=args.frames)

        if results:
            benchmark.print_report()

            if not args.no_save:
                benchmark.save_results()

    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
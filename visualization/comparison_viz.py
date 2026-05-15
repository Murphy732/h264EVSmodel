import cv2
import numpy as np
import time
from typing import List, Tuple, Dict
from interpolation.base import Interpolator


def calculate_psnr(img1: np.ndarray, img2: np.ndarray) -> float:
    mse = np.mean((img1.astype(np.float32) - img2.astype(np.float32)) ** 2)
    if mse == 0:
        return float('inf')
    max_pixel = 255.0
    return 20 * np.log10(max_pixel / np.sqrt(mse))


def calculate_ssim(img1: np.ndarray, img2: np.ndarray) -> float:
    if len(img1.shape) == 3:
        img1_gray = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
        img2_gray = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
    else:
        img1_gray = img1
        img2_gray = img2

    C1 = (0.01 * 255) ** 2
    C2 = (0.03 * 255) ** 2

    img1_gray = img1_gray.astype(np.float64)
    img2_gray = img2_gray.astype(np.float64)
    kernel = cv2.getGaussianKernel(11, 1.5)
    window = np.outer(kernel, kernel.transpose())

    mu1 = cv2.filter2D(img1_gray, -1, window)[5:-5, 5:-5]
    mu2 = cv2.filter2D(img2_gray, -1, window)[5:-5, 5:-5]
    mu1_sq = mu1 ** 2
    mu2_sq = mu2 ** 2
    mu1_mu2 = mu1 * mu2
    sigma1_sq = cv2.filter2D(img1_gray ** 2, -1, window)[5:-5, 5:-5] - mu1_sq
    sigma2_sq = cv2.filter2D(img2_gray ** 2, -1, window)[5:-5, 5:-5] - mu2_sq
    sigma12 = cv2.filter2D(img1_gray * img2_gray, -1, window)[5:-5, 5:-5] - mu1_mu2

    ssim_map = ((2 * mu1_mu2 + C1) * (2 * sigma12 + C2)) / (
        (mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2)
    )
    return ssim_map.mean()


class InterpolationComparison:
    def __init__(self, interpolators: List[Interpolator]):
        self.interpolators = interpolators

    def compare(
        self,
        frame1: np.ndarray,
        frame2: np.ndarray,
        ground_truth: np.ndarray,
        t: float = 0.5
    ) -> Dict:
        results = {}

        for interp in self.interpolators:
            start_time = time.time()
            interpolated = interp.interpolate(frame1, frame2, t)
            elapsed = time.time() - start_time

            psnr = calculate_psnr(interpolated, ground_truth)
            ssim = calculate_ssim(interpolated, ground_truth)

            results[interp.name] = {
                "image": interpolated,
                "psnr": psnr,
                "ssim": ssim,
                "time": elapsed,
                "fps": 1.0 / elapsed if elapsed > 0 else float('inf')
            }

        return results

    @staticmethod
    def create_comparison_grid(
        frame1: np.ndarray,
        frame2: np.ndarray,
        ground_truth: np.ndarray,
        results: Dict,
        t: float = 0.5
    ) -> np.ndarray:
        h, w = frame1.shape[:2]
        target_w = w // 2
        target_h = h // 2

        def resize_and_label(img, label, color=(255, 255, 255)):
            if len(img.shape) == 2:
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            resized = cv2.resize(img, (target_w, target_h))
            cv2.putText(
                resized, label, (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2
            )
            return resized

        views = [
            resize_and_label(frame1, f"Frame 1 (t=0)"),
            resize_and_label(frame2, f"Frame 2 (t=1)"),
            resize_and_label(ground_truth, "Ground Truth"),
        ]

        for name, data in results.items():
            label = f"{name}\nPSNR: {data['psnr']:.1f}dB\nFPS: {data['fps']:.1f}"
            labeled_img = resize_and_label(data['image'], label.split('\n')[0])
            y_offset = 60
            for line in label.split('\n')[1:]:
                cv2.putText(
                    labeled_img, line, (10, y_offset),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1
                )
                y_offset += 20
            views.append(labeled_img)

        num_views = len(views)
        cols = 3
        rows = (num_views + cols - 1) // cols

        while len(views) < rows * cols:
            views.append(np.zeros((target_h, target_w, 3), dtype=np.uint8))

        grid = []
        for i in range(rows):
            row = np.hstack(views[i*cols:(i+1)*cols])
            grid.append(row)

        return np.vstack(grid)


def print_comparison_report(results: Dict):
    print("\n" + "="*60)
    print("插值方案对比报告")
    print("="*60)
    print(f"{'方案':<25} {'PSNR(dB)':<12} {'SSIM':<10} {'FPS':<10}")
    print("-"*60)

    for name, data in results.items():
        print(f"{name:<25} {data['psnr']:<12.2f} {data['ssim']:<10.3f} {data['fps']:<10.1f}")

    print("="*60)
